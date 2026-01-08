import streamlit as st
import pandas as pd

from loaders.data_loader import safe_read_csv
from engines.pricing_engine import build_pricing_snapshot
from engines.guardrail_engine import apply_guardrail
from engines.market_share_engine import apply_market_share
from engines.intent_engine import detect_loss_intent
from utils.formatters import format_idr


# ======================
# STRATEGIC HELPERS
# ======================
def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def simulate_price_moves(war, drop_pcts=(0.005, 0.01, 0.02)):
    """
    Simulasi penurunan harga (what-if) dan apakah melanggar floor.
    Output:
      sim_price_5, sim_ok_5   (turun 0.5%)
      sim_price_10, sim_ok_10 (turun 1%)
      sim_price_20, sim_ok_20 (turun 2%)
    """
    out = war.copy()
    for p in drop_pcts:
        k = int(p * 1000)  # 0.5% -> 5
        out[f"sim_price_{k}"] = out["price_sell"] * (1 - p)
        out[f"sim_ok_{k}"] = out[f"sim_price_{k}"] >= out["floor_price"]
    return out


def recommend_action(row):
    if row["status"] == "ATTACK" and row["guardrail_status"] == "BLOCKED":
        return "PROMO / BUNDLING (harga tidak bisa diturunkan)"
    if row["status"] == "ATTACK":
        if row["gap_price"] is None or pd.isna(row["gap_price"]):
            return "TURUNKAN HARGA (cek data kompetitor)"
        if row["gap_price"] > 50_000:
            return "TURUNKAN HARGA BERTAHAP (ladder)"
        return "TURUNKAN HARGA TIPIS (match)"
    return "PERTAHANKAN (monitor)"


def classify_strategy(row):
    share = row["market_share_pct"] if ("market_share_pct" in row and not pd.isna(row["market_share_pct"])) else 0
    if row.get("impact_level") == "HIGH":
        return "DEFEND"
    if row.get("impact_level") == "LOW" and share < 5:
        return "SACRIFICE"
    return "OPPORTUNITY"


def priority_score(row):
    impact_w = {"HIGH": 3, "MED": 2, "LOW": 1}.get(row.get("impact_level", "NO DATA"), 0.5)
    risk = row["share_at_risk_pct"] if ("share_at_risk_pct" in row and not pd.isna(row["share_at_risk_pct"])) else 0
    bonus = 1 if (row.get("status") == "ATTACK" and row.get("guardrail_status") == "BLOCKED") else 0
    return impact_w * (1 + risk) + bonus


# ======================
# MAIN WAR ROOM
# ======================
def render_war_room():
    st.subheader("⚔️ War Room – Decision Engine")
    st.caption("Ringkasan keputusan harga, guardrail, market share, dan deteksi NIAT kompetitor (loss intent).")

    # ======================
    # LOAD DATA
    # ======================
    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")
    sales = safe_read_csv("sales_internal.csv")
    market = safe_read_csv("market_size.csv")

    if master is None or price_company is None or price_comp is None:
        st.warning("⚠️ Upload master_product.csv, price_company.csv, price_competitor.csv terlebih dahulu.")
        return

    # ======================
    # BUILD CORE TABLE
    # ======================
    war = build_pricing_snapshot(price_company, master, price_comp)
    war = apply_guardrail(war)
    war = apply_market_share(war, sales, market)

    # numeric safety
    for c in ["price_sell", "min_comp_price", "gap_price", "floor_price"]:
        if c in war.columns:
            war[c] = war[c].apply(_safe_float)

    # ======================
    # STRATEGIC LAYER
    # ======================
    war = simulate_price_moves(war)
    war["recommended_action"] = war.apply(recommend_action, axis=1)
    war["strategy"] = war.apply(classify_strategy, axis=1)
    war["priority_score"] = war.apply(priority_score, axis=1)

    # ======================
    # LOSS INTENT DETECTION (NEW)
    # ======================
    # extreme_gap bisa kamu sesuaikan di sini kalau perlu
    war = detect_loss_intent(war, extreme_gap=500_000)

    # ======================
    # KPI HEADER
    # ======================
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Produk Dipantau", len(war))
    c2.metric("ATTACK", int((war["status"] == "ATTACK").sum()) if "status" in war.columns else 0)
    c3.metric("BLOCKED", int((war["guardrail_status"] == "BLOCKED").sum()) if "guardrail_status" in war.columns else 0)
    c4.metric("HIGH Impact", int((war["impact_level"] == "HIGH").sum()) if "impact_level" in war.columns else 0)

    bait_cnt = int((war["competitor_intent"] == "BAIT / SIGNAL").sum()) if "competitor_intent" in war.columns else 0
    c5.metric("Bait/Signal", bait_cnt)

    st.divider()

    # ======================
    # DISPLAY COPY + FORMAT
    # ======================
    view = war.sort_values("priority_score", ascending=False, na_position="last").copy()

    for col in ["price_sell", "min_comp_price", "gap_price", "floor_price",
                "sim_price_5", "sim_price_10", "sim_price_20"]:
        if col in view.columns:
            view[col] = view[col].apply(format_idr)

    for col in ["sim_ok_5", "sim_ok_10", "sim_ok_20"]:
        if col in view.columns:
            view[col] = view[col].apply(lambda x: "✅" if x is True else "❌")

    # ======================
    # DECISION SUMMARY (RINGKAS)
    # ======================
    st.subheader("📊 Decision Summary (Ringkas)")

    summary_cols = [
        "product_id",
        "product_name",
        "price_sell",
        "min_comp_price",
        "gap_price",
        "guardrail_status",
        "impact_level",
        "competitor_intent",
        "strategy",
        "recommended_action",
    ]

    st.dataframe(
        view[summary_cols],
        use_container_width=True,
        hide_index=True
    )

    # ======================
    # PRIORITY ACTION BOARD
    # ======================
    st.subheader("🚨 Prioritas Aksi")

    critical = war[
        (war["status"] == "ATTACK") &
        (war["guardrail_status"] == "BLOCKED") &
        (war["impact_level"] == "HIGH")
    ]

    if critical.empty:
        st.success("✅ Tidak ada produk kritikal saat ini.")
    else:
        for _, r in critical.iterrows():
            st.error(
                f"🔴 **{r['product_name']} ({r['product_id']})** | "
                f"Intent: **{r.get('competitor_intent','-')}** | "
                f"Market Share {r.get('market_share_pct','-')}% | "
                f"Risiko hilang {r.get('share_at_risk_pct','-')}%\n\n"
                f"➡️ **Aksi**: {r.get('recommended_action','-')}"
            )

    # ======================
    # DETAIL & SIMULASI (EXPANDER)
    # ======================
    st.subheader("🔍 Detail & Simulasi per Produk")

    for _, r in view.iterrows():
        with st.expander(f"{r['product_name']} ({r['product_id']})"):
            st.markdown(f"""
**Harga Saat Ini**: {r.get('price_sell','-')}  
**Harga Kompetitor Termurah**: {r.get('min_comp_price','-')}  
**Gap Harga**: {r.get('gap_price','-')}  

**Market Share**: {r.get('market_share_pct','-')}%  
**Risiko Hilang**: {r.get('share_at_risk_pct','-')}%  
**Impact Level**: {r.get('impact_level','-')}  

**Intent Kompetitor**: **{r.get('competitor_intent','-')}**  
**Catatan Intent**: {r.get('intent_note','-')}  

**Strategy**: {r.get('strategy','-')}  
**Rekomendasi Aksi**: {r.get('recommended_action','-')}
""")

            st.markdown("**Simulasi Penurunan Harga**")
            st.write({
                "Turun 0.5%": f"{r.get('sim_price_5','-')} ({r.get('sim_ok_5','-')})",
                "Turun 1%": f"{r.get('sim_price_10','-')} ({r.get('sim_ok_10','-')})",
                "Turun 2%": f"{r.get('sim_price_20','-')} ({r.get('sim_ok_20','-')})",
            })

    st.caption("ATTACK = harga kalah | BLOCKED = tidak bisa turunkan harga | Intent = niat kompetitor (market grab vs bait) | Strategy = defend/opportunity/sacrifice")
