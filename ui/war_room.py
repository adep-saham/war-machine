import streamlit as st
import pandas as pd

from loaders.data_loader import safe_read_csv
from engines.pricing_engine import build_pricing_snapshot
from engines.guardrail_engine import apply_guardrail
from engines.market_share_engine import apply_market_share
from engines.intent_engine import detect_loss_intent
from engines.dcz_engine import apply_dont_compete_zone
from engines.counter_move_engine import generate_counter_moves
from utils.formatters import format_idr


# ======================
# HELPERS
# ======================
def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def simulate_price_moves(war, drop_pcts=(0.005, 0.01, 0.02)):
    out = war.copy()
    for p in drop_pcts:
        k = int(p * 1000)  # 0.5% -> 5
        out[f"sim_price_{k}"] = out["price_sell"] * (1 - p)
        out[f"sim_ok_{k}"] = out[f"sim_price_{k}"] >= out["floor_price"]
    return out


def priority_score(row):
    impact_w = {"HIGH": 3, "MED": 2, "LOW": 1}.get(row.get("impact_level"), 0.5)
    risk = row.get("share_at_risk_pct", 0) or 0
    bonus = 1 if row.get("compete_decision") == "FIGHT" else 0
    # intent bias: market grab lebih prioritas, bait lebih rendah
    intent = row.get("competitor_intent")
    intent_bonus = 0.5 if intent == "MARKET_GRAB" else (-0.3 if intent == "BAIT / SIGNAL" else 0)
    return impact_w * (1 + risk) + bonus + intent_bonus


# ======================
# WAR ROOM
# ======================
def render_war_room():
    st.subheader("⚔️ War Room – Command Center")
    st.caption("Pricing + Guardrail + Market Impact + Intent + DCZ + Counter-Move (aksi konkret)")

    # ----------------------
    # Small controls (UX)
    # ----------------------
    with st.expander("⚙️ Pengaturan Counter-Move (opsional)", expanded=False):
        max_disc = st.slider("Batas rekomendasi diskon (untuk ladder)", 0.0, 5.0, 2.0, 0.5) / 100.0
        base_days = st.slider("Durasi default (hari)", 1, 14, 5, 1)
        extreme_gap = st.number_input("Extreme gap untuk deteksi BAIT (Rp)", value=500_000, step=50_000)

    # ======================
    # LOAD DATA
    # ======================
    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")
    sales = safe_read_csv("sales_internal.csv")
    market = safe_read_csv("market_size.csv")

    if master is None or price_company is None or price_comp is None:
        st.warning("⚠️ Upload: master_product.csv, price_company.csv, price_competitor.csv terlebih dahulu.")
        return

    # ======================
    # CORE ENGINE
    # ======================
    war = build_pricing_snapshot(price_company, master, price_comp)
    war = apply_guardrail(war)
    war = apply_market_share(war, sales, market)

    for c in ["price_sell", "min_comp_price", "gap_price", "floor_price"]:
        if c in war.columns:
            war[c] = war[c].apply(_safe_float)

    # ======================
    # STRATEGIC ENGINE
    # ======================
    war = simulate_price_moves(war)
    war = detect_loss_intent(war, extreme_gap=float(extreme_gap))
    war = apply_dont_compete_zone(war)
    war["priority_score"] = war.apply(priority_score, axis=1)

    # ======================
    # COUNTER MOVE GENERATOR (NEW)
    # ======================
    war = generate_counter_moves(war, max_discount_pct=max_disc, base_duration_days=base_days)

    # ======================
    # KPI HEADER
    # ======================
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Produk", len(war))
    c2.metric("ATTACK", int((war["status"] == "ATTACK").sum()) if "status" in war.columns else 0)
    c3.metric("FIGHT", int((war["compete_decision"] == "FIGHT").sum()))
    c4.metric("DCZ LET_GO", int((war["compete_decision"] == "LET_GO").sum()))
    c5.metric("BLOCKED", int((war["guardrail_status"] == "BLOCKED").sum()))
    c6.metric("MARKET_GRAB", int((war["competitor_intent"] == "MARKET_GRAB").sum()))

    st.divider()

    # ======================
    # DISPLAY COPY
    # ======================
    view = war.sort_values("priority_score", ascending=False).copy()

    # format angka display only
    for col in ["price_sell", "min_comp_price", "gap_price", "floor_price",
                "sim_price_5", "sim_price_10", "sim_price_20"]:
        if col in view.columns:
            view[col] = view[col].apply(format_idr)

    for col in ["sim_ok_5", "sim_ok_10", "sim_ok_20"]:
        if col in view.columns:
            view[col] = view[col].apply(lambda x: "✅" if x else "❌")

    # ======================
    # DECISION SUMMARY (RINGKAS, TIDAK PANJANG)
    # ======================
    st.subheader("📊 Decision Summary (Ringkas)")

    summary_cols = [
        "product_id",
        "product_name",
        "price_sell",
        "min_comp_price",
        "gap_price",
        "impact_level",
        "competitor_intent",
        "compete_decision",
        "counter_move_short",
        "counter_channel",
        "counter_duration_days",
    ]

    st.dataframe(view[summary_cols], use_container_width=True, hide_index=True)

    # ======================
    # PRIORITY ACTION BOARD (TOP 5)
    # ======================
    st.subheader("🚨 Action Board (Top 5)")

    top = war.sort_values("priority_score", ascending=False).head(5)
    if top.empty:
        st.success("✅ Tidak ada prioritas kritikal.")
    else:
        for _, r in top.iterrows():
            badge = "🔴" if (r.get("compete_decision") == "FIGHT" and r.get("impact_level") == "HIGH") else "🟠" if r.get("compete_decision") == "FIGHT" else "🟢"
            share = r.get("market_share_pct", None)
            risk = r.get("share_at_risk_pct", None)
            share_txt = "-" if share is None or (isinstance(share, float) and pd.isna(share)) else f"{share:.2f}%"
            risk_txt = "-" if risk is None or (isinstance(risk, float) and pd.isna(risk)) else f"{risk:.2f}%"

            st.info(
                f"{badge} **{r.get('product_name')} ({r.get('product_id')})**  \n"
                f"Intent: **{r.get('competitor_intent')}** | DCZ: **{r.get('compete_decision')}** | Impact: **{r.get('impact_level')}** | Share: {share_txt} | Risk: {risk_txt}  \n\n"
                f"➡️ **Counter-Move**: **{r.get('counter_move')}**  \n"
                f"📍 Channel: **{r.get('counter_channel')}** | ⏱️ Durasi: **{r.get('counter_duration_days')} hari**"
            )

    # ======================
    # DETAIL (EXPANDER) — lengkap tapi tidak mengganggu
    # ======================
    st.subheader("🔍 Detail per Produk (Drill-down)")

    for _, r in view.iterrows():
        with st.expander(f"{r['product_name']} ({r['product_id']})"):
            st.markdown(f"""
**Harga Saat Ini**: {r.get('price_sell','-')}  
**Harga Kompetitor Termurah**: {r.get('min_comp_price','-')}  
**Gap**: {r.get('gap_price','-')}  

**Impact Level**: {r.get('impact_level','-')}  
**Intent Kompetitor**: **{r.get('competitor_intent','-')}**  
**DCZ Decision**: **{r.get('compete_decision','-')}**  
**Alasan DCZ**: {r.get('dcz_reason','-')}  

**Counter-Move (aksi konkret)**: **{r.get('counter_move','-')}**  
**Channel**: {r.get('counter_channel','-')} | **Durasi**: {r.get('counter_duration_days','-')} hari  
**Rationale**: {r.get('counter_rationale','-')}
""")

            st.markdown("**Simulasi Penurunan Harga (What-if)**")
            st.write({
                "Turun 0.5%": f"{r.get('sim_price_5','-')} ({r.get('sim_ok_5','-')})",
                "Turun 1%": f"{r.get('sim_price_10','-')} ({r.get('sim_ok_10','-')})",
                "Turun 2%": f"{r.get('sim_price_20','-')} ({r.get('sim_ok_20','-')})",
            })

    st.caption("Counter-Move Generator menghasilkan aksi yang bisa dieksekusi (channel + durasi + alasan), bukan sekadar label.")
