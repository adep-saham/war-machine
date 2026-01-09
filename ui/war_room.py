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


def priority_score(row):
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
    # CONTROLS
    # ======================
    with st.expander("⚙️ Pengaturan Counter-Move", expanded=False):
        max_disc = st.slider("Batas diskon ladder (%)", 0.0, 5.0, 0.5, 0.5) / 100
        base_days = st.slider("Durasi default (hari)", 1, 14, 3)
        extreme_gap = st.number_input("Extreme gap (Rp) untuk deteksi BAIT", value=500_000, step=50_000)

    # ======================
    # PIPELINE
    # ======================
    war = build_pricing_snapshot(price_company, master, price_comp)
    war = apply_guardrail(war)
    war = apply_market_share(war, sales, market)

    cfg = ForecastConfig(date_col="date", sku_col="product_id", qty_col="qty")
    war = attach_demand_signals(war, sales, cfg=cfg, inventory_col="stock_on_hand")

    war = compute_product_performance(
        war,
        price_col="price_sell",
        cost_col="cost_unit",
        volume_col="sales_volume",
        min_comp_col="min_comp_price"
    )

    war[["dcz_decision", "dcz_reason"]] = war.apply(
        lambda r: decide_dcz(r), axis=1, result_type="expand"
    )

    war["priority_score"] = war.apply(priority_score, axis=1)
    war = detect_loss_intent(war, extreme_gap=float(extreme_gap))

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
    # SORTED VIEW
    # ======================
    view = war.sort_values("priority_score", ascending=False).copy()

    # ======================
    # 🔀 VIEW MODE TOGGLE
    # ======================
    st.markdown("### 🧭 View Mode")
    mode = st.radio(
        "Pilih mode tampilan:",
        ["Executive View (Manajemen)", "Analyst View (Detail)"],
        horizontal=True
    )

    def safe_name(r):
        return r.get("product_name") or r.get("product_id")

    def dcz_badge(dcz):
        return {
            "FIGHT": "🔴 FIGHT",
            "PROMO_ZONE": "🟠 PROMO",
            "NO_FIGHT": "🟢 NO FIGHT",
            "LET_GO": "⚪ LET GO",
            "HOLD": "🟡 HOLD"
        }.get(dcz, "🟡 HOLD")

    # ======================
    # EXECUTIVE VIEW
    # ======================
    if mode.startswith("Executive"):
        fight = (view["dcz_decision"] == "FIGHT").sum()
        promo = (view["dcz_decision"] == "PROMO_ZONE").sum()

        if fight or promo:
            st.success("✅ STATUS HARI INI: ACTION MODE — ada produk perlu tindakan")
        else:
            st.warning("🟡 STATUS HARI INI: MONITORING MODE — tidak ada aksi harga")

        st.subheader("🚨 Action Board (Top 5)")
        for _, r in view.head(5).iterrows():
            st.info(
                f"**{dcz_badge(r['dcz_decision'])} — {safe_name(r)}**\n\n"
                f"Role: {r.get('product_role')} | Demand: {r.get('demand_trend')}\n\n"
                f"➡️ Counter-Move: **{r.get('counter_move')}** "
                f"(Channel: {r.get('counter_channel')}, {r.get('counter_duration_days')} hari)"
            )

        st.subheader("📎 Ringkasan Keputusan")
        st.dataframe(
            view[[
                "product_id", "product_role", "dcz_decision",
                "demand_trend", "forecast_confidence",
                "counter_move", "counter_channel", "counter_duration_days"
            ]],
            use_container_width=True,
            hide_index=True
        )

    # ======================
    # ANALYST VIEW
    # ======================
    else:
        st.subheader("🧪 Analyst View — Detail Lengkap")
        st.dataframe(view, use_container_width=True, hide_index=True)

    st.caption("War Room FINAL — DCZ tunggal, keputusan konsisten, tidak reaktif.")
