import streamlit as st
import pandas as pd

# =====================================================
# HELPERS
# =====================================================
def dcz_badge(dcz: str) -> str:
    return {
        "FIGHT": "🔴 FIGHT",
        "PROMO_ZONE": "🟠 PROMO",
        "NO_FIGHT": "🟢 NO FIGHT",
        "LET_GO": "⚪ LET GO",
        "HOLD": "🟡 HOLD",
    }.get(str(dcz), "🟡 HOLD")


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def ensure_columns(df: pd.DataFrame, defaults: dict):
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
    return df


# =====================================================
# PRODUCT ROLE — FINAL (NO MORE UNKNOWN)
# =====================================================
def assign_product_role(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["product_role"] = "DEFENDER"  # default aman

    if "demand_trend" not in df.columns:
        df["demand_trend"] = "FLAT"

    if "market_share_pct" not in df.columns:
        df["market_share_pct"] = 0.0

    # ATTACKER: demand naik + share kuat
    df.loc[
        (df["demand_trend"] == "UP") & (df["market_share_pct"] >= 0.30),
        "product_role"
    ] = "ATTACKER"

    # TRAFFIC: demand naik + share kecil
    df.loc[
        (df["demand_trend"] == "UP") & (df["market_share_pct"] < 0.30),
        "product_role"
    ] = "TRAFFIC"

    # DEFENDER: share besar tapi demand tidak naik
    df.loc[
        (df["demand_trend"].isin(["FLAT", "DOWN"])) & (df["market_share_pct"] >= 0.30),
        "product_role"
    ] = "DEFENDER"

    # TRAFFIC fallback
    df.loc[
        (df["demand_trend"] == "FLAT") & (df["market_share_pct"] < 0.15),
        "product_role"
    ] = "TRAFFIC"

    return df


# =====================================================
# MAIN WAR ROOM
# =====================================================
def render_war_room():
    st.markdown("## ⚔️ War Room — Command Center")
    st.caption("Demand + Product Role → DCZ → Counter-Move (Single Source of Truth)")

    # =================================================
    # LOAD DATA FROM SESSION
    # =================================================
    master_product = st.session_state.get("master_product")
    price_company = st.session_state.get("price_company")
    price_competitor = st.session_state.get("price_competitor")
    sales_internal = st.session_state.get("sales_internal")
    market_size = st.session_state.get("market_size")
    engines = st.session_state.get("engines", {})

    missing = []
    for k, v in {
        "master_product": master_product,
        "price_company": price_company,
        "price_competitor": price_competitor,
        "sales_internal": sales_internal,
        "market_size": market_size,
    }.items():
        if v is None:
            missing.append(k)

    if missing:
        st.warning(f"⚠️ Data belum lengkap: {missing}")
        st.stop()

    # =================================================
    # SETTINGS
    # =================================================
    with st.expander("⚙️ Pengaturan Counter-Move", expanded=False):
        ladder_cap = st.slider("Batas diskon ladder (%)", 0.0, 10.0, 0.5, 0.1)
        default_days = st.slider("Durasi default (hari)", 1, 14, 3, 1)
        bait_gap = st.number_input("Extreme gap (Rp) untuk BAIT", value=500000, step=50000)

    st.divider()

    # =================================================
    # PRICING SNAPSHOT (FIXED)
    # =================================================
    try:
        pricing_engine = engines["pricing_engine"]
    
        # pastikan fungsi ada
        if hasattr(pricing_engine, "build_pricing_snapshot"):
            war = pricing_engine.build_pricing_snapshot(
                price_company=price_company,
                master=master_product,
                price_competitor=price_competitor,
            )
        else:
            raise RuntimeError("build_pricing_snapshot not found")
    
    except Exception as e:
        st.error(f"Pricing engine gagal (fallback): {e}")
        war = master_product.copy()
        war["price_sell"] = 0
        war["min_comp_price"] = None
        war["gap_price"] = None
        war["floor_price"] = 0
        war["guardrail_status"] = "ALLOWED"


    # Product performance
    try:
        war = engines["product_performance_engine"](war, sales_internal)
    except Exception:
        war["sales_volume"] = 0
        war["revenue"] = 0
        war["market_share_pct"] = 0.0
        war["performance_flag"] = "NORMAL"

    # Market size / share
    try:
        war = engines["market_share_engine"](war, sales_internal, market_size)
    except Exception:
        if "estimated_market_volume" not in war.columns:
            war["estimated_market_volume"] = None
        war["market_share_pct"] = war.get("market_share_pct", 0.0)

    # =================================================
    # PRODUCT ROLE (FINAL)
    # =================================================
    war = assign_product_role(war)

    # =================================================
    # DCZ — HARD OVERRIDE (ANTI REGISTRY ERROR)
    # =================================================
    from engines.dcz_engine import DCZEngine
    try:
        war = DCZEngine().decide_dcz(war)
    except Exception:
        war["dcz_decision"] = "HOLD"
        war["dcz_reason"] = "default_safe_mode"

    # =================================================
    # COUNTER MOVE
    # =================================================
    try:
        st.session_state["counter_move_cfg"] = {
            "ladder_cap_pct": ladder_cap,
            "default_duration_days": default_days,
            "bait_gap_rp": bait_gap,
        }
        war = engines["counter_move_engine"](war)
    except Exception:
        war["counter_move"] = "HOLD - Monitor (no action)"
        war["counter_channel"] = "All"
        war["counter_duration_days"] = default_days

    # =================================================
    # DEFAULT COLUMNS (ANTI KOSONG)
    # =================================================
    war = ensure_columns(
        war,
        {
            "product_name": "-",
            "demand_trend": "FLAT",
            "forecast_confidence": 0.0,
            "inventory_cover_days": None,
            "counter_move": "HOLD - Monitor (no action)",
            "counter_channel": "All",
            "counter_duration_days": default_days,
            "dcz_decision": "HOLD",
            "dcz_reason": "-",
        }
    )

    # =================================================
    # PRIORITY SORT
    # =================================================
    priority = {"FIGHT": 4, "PROMO_ZONE": 3, "NO_FIGHT": 2, "HOLD": 1, "LET_GO": 0}
    war["priority_score"] = war["dcz_decision"].map(priority).fillna(1)
    view = war.sort_values("priority_score", ascending=False).copy()

    # =================================================
    # KPI STRIP
    # =================================================
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Produk", len(view))
    k2.metric("🔴 FIGHT", int((view["dcz_decision"] == "FIGHT").sum()))
    k3.metric("🟠 PROMO", int((view["dcz_decision"] == "PROMO_ZONE").sum()))
    k4.metric("🟢 NO FIGHT", int((view["dcz_decision"] == "NO_FIGHT").sum()))
    k5.metric("🟡 HOLD", int((view["dcz_decision"] == "HOLD").sum()))

    st.divider()

    # =================================================
    # VIEW MODE
    # =================================================
    mode = st.radio(
        "Pilih mode tampilan:",
        ["Executive View (Manajemen)", "Analyst View (Detail)"],
        horizontal=True,
    )

    # =================================================
    # EXECUTIVE VIEW
    # =================================================
    if mode == "Executive View (Manajemen)":
        st.markdown("## 🧠 Action Board (Top 5)")
        for _, r in view.head(5).iterrows():
            st.markdown(
                f"""
                <div style="padding:14px;margin-bottom:10px;border-radius:12px;background:#f5f8ff;">
                    <b>{dcz_badge(r['dcz_decision'])} — {r['product_name']}</b><br/>
                    Role: <b>{r['product_role']}</b> |
                    Demand: <b>{r['demand_trend']}</b> |
                    Conf: <b>{safe_float(r['forecast_confidence']):.3f}</b><br/>
                    Counter-Move: <b>{r['counter_move']}</b><br/>
                    Channel: {r['counter_channel']} | Durasi: {int(r['counter_duration_days'])} hari<br/>
                    <i>Reason: {r['dcz_reason']}</i>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("## 📌 Ringkasan Keputusan")
        st.dataframe(
            view[
                [
                    "product_id",
                    "product_role",
                    "dcz_decision",
                    "demand_trend",
                    "forecast_confidence",
                    "counter_move",
                    "counter_channel",
                    "counter_duration_days",
                ]
            ],
            use_container_width=True,
        )

    # =================================================
    # ANALYST VIEW
    # =================================================
    else:
        st.markdown("## 🔍 Analyst View — Detail Lengkap")
        st.dataframe(view, use_container_width=True)

    st.caption("War Room FINAL — keputusan konsisten, sistem tidak reaktif.")
