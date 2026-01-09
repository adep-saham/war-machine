import streamlit as st
import pandas as pd

# ===============================
# Helper: DCZ Badge
# ===============================
def dcz_badge(dcz: str) -> str:
    return {
        "FIGHT": "🔴 FIGHT",
        "PROMO_ZONE": "🟠 PROMO",
        "NO_FIGHT": "🟢 NO FIGHT",
        "LET_GO": "⚪ LET GO",
        "HOLD": "🟡 HOLD"
    }.get(dcz, "HOLD")


# ===============================
# MAIN UI
# ===============================
def render_war_room():

    st.markdown("## ⚔️ War Room — Command Center")
    st.caption("Demand + Product Role → DCZ → Counter-Move (Single Source of Truth)")

    # ===============================
    # 0. Ambil data dari session_state
    # ===============================
    required_keys = [
        "master_product",
        "price_company",
        "price_competitor",
        "sales_internal",
        "market_size",
        "engines"
    ]

    missing = [k for k in required_keys if k not in st.session_state]
    if missing:
        st.warning(f"⚠️ Data belum lengkap: {missing}")
        st.stop()

    master_product   = st.session_state["master_product"]
    price_company    = st.session_state["price_company"]
    price_competitor = st.session_state["price_competitor"]
    sales_internal   = st.session_state["sales_internal"]
    market_size      = st.session_state["market_size"]
    engines          = st.session_state["engines"]

    # ===============================
    # 1. PIPELINE ANALISIS
    # ===============================
    war = engines["pricing_engine"].build_pricing_snapshot(
        price_company=price_company,
        master=master_product,
        price_competitor=price_competitor,
    )

    war = engines["guardrail_engine"].apply_guardrail(war)

    war = engines["product_performance_engine"].compute_product_performance(
        war, sales_internal
    )

    war = engines["market_share_engine"].apply_market_share(
        war, sales_internal, market_size
    )

    war = engines["dcz_engine"].decide_dcz(war)

    war = engines["counter_move_engine"].generate_counter_move(war)

    # ===============================
    # 2. SAFETY DEFAULTS
    # ===============================
    defaults = {
        "product_role": "UNKNOWN",
        "dcz_decision": "HOLD",
        "demand_trend": "FLAT",
        "forecast_confidence": 0.0,
        "counter_move": "HOLD - Monitor (no action)",
        "counter_channel": "All",
        "counter_duration_days": 3,
        "impact_level": "LOW",
        "market_share_pct": 0.0,
        "share_at_risk_pct": 0.0,
    }

    for col, val in defaults.items():
        if col not in war.columns:
            war[col] = val

    # ===============================
    # 3. PRIORITY & SORTING
    # ===============================
    priority_map = {
        "FIGHT": 4,
        "PROMO_ZONE": 3,
        "NO_FIGHT": 2,
        "HOLD": 1,
        "LET_GO": 0,
    }
    war["priority_score"] = war["dcz_decision"].map(priority_map).fillna(1)

    view = war.sort_values("priority_score", ascending=False).copy()

    # ===============================
    # 4. VIEW MODE TOGGLE
    # ===============================
    st.markdown("### 🧭 View Mode")
    view_mode = st.radio(
        "Pilih mode tampilan:",
        ["Executive View (Manajemen)", "Analyst View (Detail)"],
        horizontal=True
    )

    # ==================================================
    # EXECUTIVE VIEW
    # ==================================================
    if view_mode == "Executive View (Manajemen)":

        st.markdown("## 📊 Ringkasan Eksekutif")

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("🔴 FIGHT", (view["dcz_decision"] == "FIGHT").sum())
        c2.metric("🟠 PROMO", (view["dcz_decision"] == "PROMO_ZONE").sum())
        c3.metric("🟢 NO FIGHT", (view["dcz_decision"] == "NO_FIGHT").sum())
        c4.metric("🟡 HOLD", (view["dcz_decision"] == "HOLD").sum())
        c5.metric("📦 PRODUK", len(view))

        st.markdown("### 🚨 Action Board")

        for _, r in view.iterrows():
            bg = {
                "FIGHT": "#ffe5e5",
                "PROMO_ZONE": "#fff4e5",
                "NO_FIGHT": "#e9f7ef",
                "HOLD": "#f2f2f2",
                "LET_GO": "#eeeeee",
            }.get(r["dcz_decision"], "#ffffff")

            st.markdown(
                f"""
                <div style="
                    background:{bg};
                    padding:14px;
                    border-radius:10px;
                    margin-bottom:10px;
                ">
                <b>{dcz_badge(r['dcz_decision'])} — {r['product_id']}</b><br>
                Role: <b>{r['product_role']}</b> |
                Demand: <b>{r['demand_trend']}</b><br>
                🧭 Aksi: <b>{r['counter_move']}</b>
                ({r['counter_channel']}, {r['counter_duration_days']} hari)
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ==================================================
    # ANALYST VIEW
    # ==================================================
    else:
        st.markdown("## 🔍 Analyst View — Detail")

        def dcz_color(val):
            return {
                "FIGHT": "background-color:#ffdddd;font-weight:bold",
                "PROMO_ZONE": "background-color:#fff0cc;font-weight:bold",
                "NO_FIGHT": "background-color:#ddffdd;font-weight:bold",
                "HOLD": "background-color:#eeeeee;font-weight:bold",
                "LET_GO": "background-color:#e6e6e6;font-weight:bold",
            }.get(val, "")

        styled = (
            view
            .style
            .applymap(dcz_color, subset=["dcz_decision"])
            .format({
                "forecast_confidence": "{:.0%}",
                "market_share_pct": "{:.1%}",
                "share_at_risk_pct": "{:.1%}",
            })
        )

        st.dataframe(styled, use_container_width=True)

    st.caption("War Room FINAL — DCZ tunggal, keputusan konsisten, tidak reaktif.")
