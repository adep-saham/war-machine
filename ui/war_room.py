import streamlit as st
import pandas as pd

# ======================
# CORE IMPORTS
# ======================
from loaders.data_loader import safe_read_csv
from engines.pricing_engine import build_pricing_snapshot
from engines.guardrail_engine import apply_guardrail
from engines.market_share_engine import apply_market_share
from engines.intent_engine import detect_loss_intent
from engines.counter_move_engine import generate_counter_moves

# FASE 1 ENGINES
from engines.demand_forecast_engine import attach_demand_signals, ForecastConfig
from engines.product_performance_engine import compute_product_performance
from engines.dcz_decision_engine import decide_dcz

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
        k = int(p * 1000)
        out[f"sim_price_{k}"] = out["price_sell"] * (1 - p)
        out[f"sim_ok_{k}"] = out[f"sim_price_{k}"] >= out["floor_price"]
    return out


def priority_score(row):
    """
    PRIORITY SCORE FINAL
    - Pakai DCZ FINAL (bukan DCZ lama)
    """
    impact_w = {"HIGH": 3, "MED": 2, "LOW": 1}.get(row.get("impact_level"), 0.5)
    risk = row.get("share_at_risk_pct", 0) or 0

    dcz = row.get("dcz_decision")
    bonus = 1 if dcz == "FIGHT" else 0
    penalty = -2 if dcz == "NO_FIGHT" else 0

    return impact_w * (1 + risk) + bonus + penalty


# ======================
# WAR ROOM
# ======================
def render_war_room():
    st.subheader("⚔️ War Room – Command Center")
    st.caption("Demand + Product Role → DCZ → Counter-Move (Single Source of Truth)")

    # ======================
    # LOAD DATA
    # ======================
    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")
    sales = safe_read_csv("sales_internal.csv")
    market = safe_read_csv("market_size.csv")

    if master is None or price_company is None or price_comp is None:
        st.warning("⚠️ Upload: master_product.csv, price_company.csv, price_competitor.csv")
        return

    # ======================
    # CONTROLS (COUNTER MOVE)
    # ======================
    with st.expander("⚙️ Pengaturan Counter-Move", expanded=False):
        max_disc = st.slider("Batas diskon ladder (%)", 0.0, 5.0, 0.5, 0.5) / 100
        base_days = st.slider("Durasi default (hari)", 1, 14, 3)
        extreme_gap = st.number_input(
            "Extreme gap (Rp) untuk deteksi BAIT",
            value=500_000,
            step=50_000
        )

    # ======================
    # 1️⃣ SNAPSHOT & GUARDRAIL
    # ======================
    war = build_pricing_snapshot(price_company, master, price_comp)
    war = apply_guardrail(war)
    war = apply_market_share(war, sales, market)

    for c in ["price_sell", "min_comp_price", "gap_price", "floor_price"]:
        if c in war.columns:
            war[c] = war[c].apply(_safe_float)

    # ======================
    # 2️⃣ DEMAND FORECAST (STATE)
    # ======================
    cfg = ForecastConfig(date_col="date", sku_col="product_id", qty_col="qty")
    war = attach_demand_signals(
        war,
        sales,
        cfg=cfg,
        inventory_col="stock_on_hand"
    )

    # ======================
    # 3️⃣ PRODUCT PERFORMANCE (IDENTITY)
    # ======================
    war = compute_product_performance(
        war,
        price_col="price_sell",
        cost_col="cost_unit",
        volume_col="sales_volume",
        min_comp_col="min_comp_price"
    )

    # ======================
    # 4️⃣ DCZ FINAL (SINGLE SOURCE)
    # ======================
    war[["dcz_decision", "dcz_reason"]] = war.apply(
        lambda r: decide_dcz(r),
        axis=1,
        result_type="expand"
    )

    # ======================
    # 5️⃣ PRIORITY SCORE
    # ======================
    war["priority_score"] = war.apply(priority_score, axis=1)

    # ======================
    # 6️⃣ LOSS INTENT (OPSIONAL, AFTER DCZ)
    # ======================
    war = detect_loss_intent(war, extreme_gap=float(extreme_gap))

    # ======================
    # 7️⃣ COUNTER MOVE (READ DCZ FINAL)
    # ======================
    war = generate_counter_moves(
        war,
        max_discount_pct=max_disc,
        base_duration_days=base_days
    )

    # ======================
    # KPI HEADER
    # ======================
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Produk", len(war))
    c2.metric("FIGHT", (war["dcz_decision"] == "FIGHT").sum())
    c3.metric("NO_FIGHT", (war["dcz_decision"] == "NO_FIGHT").sum())
    c4.metric("PROMO_ZONE", (war["dcz_decision"] == "PROMO_ZONE").sum())
    c5.metric("LET_GO", (war["dcz_decision"] == "LET_GO").sum())
    c6.metric("HOLD", (war["dcz_decision"] == "HOLD").sum())

    st.divider()

    # ======================
    # DISPLAY FORMAT
    # ======================
    view = war.sort_values("priority_score", ascending=False).copy()

    for col in [
        "price_sell", "min_comp_price", "gap_price", "floor_price",
        "sim_price_5", "sim_price_10", "sim_price_20"
    ]:
        if col in view.columns:
            view[col] = view[col].apply(format_idr)

    for col in ["sim_ok_5", "sim_ok_10", "sim_ok_20"]:
        if col in view.columns:
            view[col] = view[col].apply(lambda x: "✅" if x else "❌")

    # ======================
    # DECISION SUMMARY
    # ======================
    st.subheader("📊 Decision Summary")

    summary_cols = [
        "product_id",
        "product_name",
        "product_role",
        "dcz_decision",
        "price_sell",
        "min_comp_price",
        "gap_price",
        "demand_trend",
        "inventory_cover_days",
        "forecast_confidence",
        "counter_move_short",
        "counter_channel",
        "counter_duration_days",
    ]
    summary_cols = [c for c in summary_cols if c in view.columns]

    st.dataframe(view[summary_cols], use_container_width=True, hide_index=True)

    # ======================
    # ACTION BOARD (TOP 5)
    # ======================
    st.subheader("🚨 Action Board (Top 5)")

    for _, r in view.head(5).iterrows():
        badge = (
            "🔴" if r["dcz_decision"] == "FIGHT"
            else "🟠" if r["dcz_decision"] == "PROMO_ZONE"
            else "🟡" if r["dcz_decision"] == "HOLD"
            else "🟢"
        )

        st.info(
            f"{badge} **{r.get('product_name')} ({r.get('product_id')})**  \n"
            f"Role: **{r.get('product_role')}** | DCZ: **{r.get('dcz_decision')}**  \n"
            f"Demand: {r.get('demand_trend')} | Inventory: {r.get('inventory_cover_days')} hari | Conf: {r.get('forecast_confidence')}  \n\n"
            f"➡️ **Counter-Move**: **{r.get('counter_move')}**  \n"
            f"📍 Channel: **{r.get('counter_channel')}** | ⏱️ **{r.get('counter_duration_days')} hari**"
        )

    # ======================
    # DETAIL DRILL-DOWN
    # ======================
    st.subheader("🔍 Detail per Produk")

    for _, r in view.iterrows():
        with st.expander(f"{r['product_name']} ({r['product_id']})"):
            st.markdown(f"""
**Product Role**: **{r.get('product_role')}**  
**DCZ Decision**: **{r.get('dcz_decision')}**  
**DCZ Reason**: {r.get('dcz_reason')}  

**Demand Trend**: {r.get('demand_trend')}  
**Inventory Cover**: {r.get('inventory_cover_days')} hari  
**Forecast Confidence**: {r.get('forecast_confidence')}  

**Counter-Move**: **{r.get('counter_move')}**  
Channel: {r.get('counter_channel')} | Durasi: {r.get('counter_duration_days')} hari
""")

    st.caption("War Room FINAL — DCZ tunggal, keputusan konsisten, tidak reaktif.")


