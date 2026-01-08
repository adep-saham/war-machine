import streamlit as st
import pandas as pd

from loaders.data_loader import safe_read_csv
from engines.pricing_engine import build_pricing_snapshot
from engines.guardrail_engine import apply_guardrail
from engines.market_share_engine import apply_market_share
from utils.formatters import format_idr


# ======================
# STRATEGIC HELPERS
# ======================
def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def simulate_price_moves(war: pd.DataFrame, drop_pcts=(0.005, 0.01, 0.02)) -> pd.DataFrame:
    """
    Simulasi penurunan harga (what-if) dan apakah masih melanggar floor.
    Asumsi: war punya kolom numeric 'price_sell' dan 'floor_price'.
    """
    out = war.copy()

    for p in drop_pcts:
        col_price = f"sim_price_{int(p*1000)}"  # 0.5% -> 5, 1% -> 10, 2% -> 20 (x10)
        col_ok = f"sim_ok_{int(p*1000)}"
        col_gap = f"sim_gap_{int(p*1000)}"

        out[col_price] = out["price_sell"] * (1 - p)
        out[col_ok] = out[col_price] >= out["floor_price"]

        # kalau ada min_comp_price, hitung gap setelah simulasi
        out[col_gap] = out[col_price] - out["min_comp_price"]

    return out


def recommend_action(row) -> str:
    """
    Rekomendasi aksi berbasis status + guardrail + gap.
    Ini rule-based MVP, bisa di-upgrade jadi model.
    """
    status = row.get("status")
    guard = row.get("guardrail_status")
    gap = row.get("gap_price")

    if status == "ATTACK" and guard == "BLOCKED":
        # tidak bisa turunkan harga → cari alternatif
        return "PROMO / BUNDLING (harga tidak bisa diturunkan)"
    if status == "ATTACK":
        # bisa turunkan
        if gap is None or pd.isna(gap):
            return "TURUNKAN HARGA (cek data kompetitor)"
        if gap > 50000:
            return "TURUNKAN HARGA BERTAHAP (ladder)"
        return "TURUNKAN HARGA TIPIS (match)"
    return "PERTAHANKAN (monitor)"


def classify_strategy(row) -> str:
    """
    Portofolio strategy:
    - DEFEND: HIGH impact (harus dipertahankan)
    - SACRIFICE: LOW impact & share kecil
    - OPPORTUNITY: sisanya (bisa diserang balik / optimasi)
    """
    impact = row.get("impact_level")
    share = row.get("market_share_pct")

    # fallback
    share = share if share is not None and not pd.isna(share) else 0

    if impact == "HIGH":
        return "DEFEND"
    if impact == "LOW" and share < 5:
        return "SACRIFICE"
    return "OPPORTUNITY"


def predict_competitor_response(row) -> str:
    """
    Prediksi sederhana: jika gap kecil, kompetitor kemungkinan respons cepat.
    """
    gap = row.get("gap_price")
    if gap is None or pd.isna(gap):
        return "UNKNOWN (no competitor data)"
    if gap <= 25000:
        return "LIKELY RETALIATE (gap tipis, kompetitor agresif)"
    if gap <= 75000:
        return "POSSIBLE RESPONSE (monitor 1–2 hari)"
    return "LESS LIKELY (gap besar, kompetitor cenderung pasif)"


def compute_priority_score(row) -> float:
    """
    Skor prioritas (semakin tinggi semakin bahaya).
    Menggabungkan:
    - impact (LOW/MED/HIGH)
    - share_at_risk_pct
    - ATTACK + BLOCKED bonus
    """
    impact = row.get("impact_level", "NO DATA")
    risk = row.get("share_at_risk_pct")
    status = row.get("status")
    guard = row.get("guardrail_status")

    impact_w = {"HIGH": 3.0, "MED": 2.0, "LOW": 1.0, "NO DATA": 0.5}.get(impact, 0.5)
    risk_v = 0.0 if risk is None or pd.isna(risk) else float(risk)

    bonus = 0.0
    if status == "ATTACK":
        bonus += 0.5
    if guard == "BLOCKED":
        bonus += 0.8
    if status == "ATTACK" and guard == "BLOCKED":
        bonus += 0.7

    return impact_w * (1 + risk_v) + bonus


# ======================
# MAIN
# ======================
def render_war_room():
    st.subheader("⚔️ War Room – Decision Engine (Strategic)")
    st.caption("Bukan hanya lihat kondisi hari ini, tapi siap menang beberapa langkah ke depan.")

    # ======================
    # LOAD DATA
    # ======================
    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")
    sales = safe_read_csv("sales_internal.csv")
    market = safe_read_csv("market_size.csv")

    if master is None or price_company is None or price_comp is None:
        st.warning("⚠️ Data belum lengkap. Upload: master_product.csv, price_company.csv, price_competitor.csv")
        return

    # ======================
    # BUILD CORE WAR TABLE
    # ======================
    war = build_pricing_snapshot(price_company, master, price_comp)
    war = apply_guardrail(war)
    war = apply_market_share(war, sales, market)

    # Pastikan numeric untuk simulasi & scoring
    war["price_sell"] = war["price_sell"].apply(_safe_float)
    war["min_comp_price"] = war["min_comp_price"].apply(_safe_float)
    war["gap_price"] = war["gap_price"].apply(_safe_float)
    if "floor_price" in war.columns:
        war["floor_price"] = war["floor_price"].apply(_safe_float)

    # ======================
    # STRATEGIC ENRICHMENT
    # ======================
    war = simulate_price_moves(war, drop_pcts=(0.005, 0.01, 0.02))
    war["recommended_action"] = war.apply(recommend_action, axis=1)
    war["strategy"] = war.apply(classify_strategy, axis=1)
    war["competitor_response"] = war.apply(predict_competitor_response, axis=1)
    war["priority_score"] = war.apply(compute_priority_score, axis=1)

    # ======================
    # KPI HEADER
    # ======================
    col1, col2, col3, col4, col5 = st.columns(5)

    total_product = len(war)
    attack_cnt = int((war["status"] == "ATTACK").sum())
    blocked_cnt = int((war["guardrail_status"] == "BLOCKED").sum())
    high_impact = int((war["impact_level"] == "HIGH").sum())

    # total share at risk (approx)
    total_risk = war["share_at_risk_pct"].dropna().sum() if "share_at_risk_pct" in war.columns else 0
    total_risk = float(total_risk) if total_risk is not None else 0

    col1.metric("Produk Dipantau", total_product)
    col2.metric("ATTACK", attack_cnt)
    col3.metric("BLOCKED", blocked_cnt)
    col4.metric("HIGH Impact", high_impact)
    col5.metric("Total Share at Risk", f"{total_risk:.2f}%")

    st.divider()

    # ======================
    # FILTER / FOCUS
    # ======================
    focus = st.selectbox(
        "🎯 Fokus Tampilan",
        ["Semua Produk", "ATTACK saja", "ATTACK + BLOCKED", "HIGH Impact", "DEFEND saja", "SACRIFICE saja"]
    )

    view = war.copy()
    if focus == "ATTACK saja":
        view = view[view["status"] == "ATTACK"]
    elif focus == "ATTACK + BLOCKED":
        view = view[(view["status"] == "ATTACK") & (view["guardrail_status"] == "BLOCKED")]
    elif focus == "HIGH Impact":
        view = view[view["impact_level"] == "HIGH"]
    elif focus == "DEFEND saja":
        view = view[view["strategy"] == "DEFEND"]
    elif focus == "SACRIFICE saja":
        view = view[view["strategy"] == "SACRIFICE"]

    # Urutkan yang paling bahaya di atas
    view = view.sort_values("priority_score", ascending=False, na_position="last")

    # ======================
    # DISPLAY FORMATTING (copy only)
    # ======================
    view_disp = view.copy()

    # format IDR (display only)
    for col in ["price_sell", "min_comp_price", "gap_price", "floor_price",
                "sim_price_5", "sim_price_10", "sim_price_20"]:
        if col in view_disp.columns:
            view_disp[col] = view_disp[col].apply(format_idr)

    # sim ok -> icon
    for col in ["sim_ok_5", "sim_ok_10", "sim_ok_20"]:
        if col in view_disp.columns:
            view_disp[col] = view_disp[col].apply(lambda x: "✅" if x is True else "❌" if x is False else "-")

    # ======================
    # DECISION TABLE
    # ======================
    st.subheader("📊 Decision Table (Strategic)")

    st.dataframe(
        view_disp[
            [
                "product_id",
                "product_name",
                "pecahan_gram",
                "price_sell",
                "min_comp_price",
                "gap_price",
                "guardrail_status",
                "market_share_pct",
                "share_at_risk_pct",
                "impact_level",
                "strategy",
                "recommended_action",
                "competitor_response",
                "sim_price_5", "sim_ok_5",
                "sim_price_10", "sim_ok_10",
                "sim_price_20", "sim_ok_20",
                "priority_score",
                "status",
            ]
        ],
        use_container_width=True
    )

    st.caption("Simulasi: sim_price_5=turun 0.5%, sim_price_10=turun 1%, sim_price_20=turun 2% | ✅ berarti masih >= floor (boleh), ❌ melanggar (blocked).")

    # ======================
    # PRIORITAS AKSI (TOP)
    # ======================
    st.subheader("🚨 Prioritas Aksi (Top 5)")

    top = war.sort_values("priority_score", ascending=False).head(5)

    if top.empty:
        st.success("✅ Tidak ada prioritas kritikal saat ini.")
    else:
        for _, r in top.iterrows():
            badge = "🔴" if (r["status"] == "ATTACK" and r["guardrail_status"] == "BLOCKED") else "🟠" if r["status"] == "ATTACK" else "🟢"
            share = "-" if pd.isna(r.get("market_share_pct")) else f"{r.get('market_share_pct'):.2f}%"
            risk = "-" if pd.isna(r.get("share_at_risk_pct")) else f"{r.get('share_at_risk_pct'):.2f}%"
            st.info(
                f"{badge} **{r.get('product_name')} ({r.get('product_id')})** | "
                f"Strategy: **{r.get('strategy')}** | "
                f"Impact: **{r.get('impact_level')}** | "
                f"Share: {share} | Risk: {risk}\n\n"
                f"➡️ Rekomendasi: **{r.get('recommended_action')}**\n\n"
                f"🔎 Prediksi kompetitor: {r.get('competitor_response')}"
            )

    st.caption("ATTACK = harga kalah | BLOCKED = tidak bisa turunkan harga | Strategy = defend/opp/sacrifice | Priority score = urutan penanganan")
