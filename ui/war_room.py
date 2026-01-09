import streamlit as st
import pandas as pd


# =====================================================
# UI Helpers
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


def get_state_df(keys):
    for k in keys:
        if k in st.session_state and st.session_state[k] is not None:
            return st.session_state[k]
    return None


# =====================================================
# Engine Call Wrappers (ANTI ERROR LOOP)
# =====================================================
def call_engine(engine, fn_name: str, *args):
    """
    Universal caller:
    - if engine has attribute fn_name -> call it
    - elif engine itself callable -> call engine(*args)
    - else -> raise
    """
    if engine is None:
        raise AttributeError("engine is None")

    # Object/class method OR module function named fn_name
    if hasattr(engine, fn_name):
        fn = getattr(engine, fn_name)
        if callable(fn):
            return fn(*args)

    # Engine itself is callable (function)
    if callable(engine):
        return engine(*args)

    raise AttributeError(f"engine has no callable '{fn_name}' and is not callable")


def ensure_columns(df: pd.DataFrame, defaults: dict):
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
    return df


# =====================================================
# MAIN WAR ROOM
# =====================================================
def render_war_room():
    st.markdown("## ⚔️ War Room — Command Center")
    st.caption("Demand + Product Role → DCZ → Counter-Move (Single Source of Truth)")

    # -------------------------------------------------
    # DATA CHECK
    # -------------------------------------------------
    master_product = get_state_df(["master_product", "master_product_df"])
    price_company = get_state_df(["price_company", "price_company_df"])
    price_competitor = get_state_df(["price_competitor", "price_competitor_df"])
    sales_internal = get_state_df(["sales_internal", "sales_internal_df"])
    market_size = get_state_df(["market_size", "market_size_df"])
    engines = st.session_state.get("engines", None)

    missing = []
    if master_product is None: missing.append("master_product")
    if price_company is None: missing.append("price_company")
    if price_competitor is None: missing.append("price_competitor")
    if sales_internal is None: missing.append("sales_internal")
    if market_size is None: missing.append("market_size")
    if engines is None: missing.append("engines")

    if missing:
        st.warning(f"⚠️ Data belum lengkap: {missing}")
        st.stop()

    # -------------------------------------------------
    # SETTINGS
    # -------------------------------------------------
    with st.expander("⚙️ Pengaturan Counter-Move", expanded=False):
        ladder_cap = st.slider("Batas diskon ladder (%)", 0.0, 10.0, 0.5, 0.1)
        default_days = st.slider("Durasi default (hari)", 1, 14, 3, 1)
        bait_gap = st.number_input("Extreme gap (Rp) untuk deteksi BAIT", value=500000, step=50000)

    st.divider()

    # -------------------------------------------------
    # PIPELINE (HARDENED)
    # -------------------------------------------------
    try:
        war = call_engine(
            engines.get("pricing_engine"),
            "build_pricing_snapshot",
            price_company, master_product, price_competitor
        )
    except Exception as e:
        st.error(f"Pricing snapshot gagal: {e}")
        # fallback minimal agar UI tetap bisa tampil
        war = master_product[["product_id", "product_name", "pecahan_gram"]].copy()
        war["price_sell"] = 0
        war["min_comp_price"] = None
        war["gap_price"] = None
        war["floor_price"] = 0
        war["guardrail_status"] = "ALLOWED"

    # Guardrail
    try:
        war = call_engine(engines.get("guardrail_engine"), "apply_guardrail", war)
    except Exception:
        # fallback: kalau floor_price ada, BLOCKED bila price_sell < floor_price
        if "floor_price" in war.columns and "price_sell" in war.columns:
            war["guardrail_status"] = "ALLOWED"
            war.loc[war["price_sell"] < war["floor_price"], "guardrail_status"] = "BLOCKED"
        else:
            war["guardrail_status"] = war.get("guardrail_status", "ALLOWED")

    # Product performance
    try:
        war = call_engine(engines.get("product_performance_engine"), "compute_product_performance", war, sales_internal)
    except Exception as e:
        st.warning(f"Product performance gagal (fallback): {e}")
        war["sales_volume"] = 0
        war["revenue"] = 0
        war["market_share_pct"] = 0
        war["performance_flag"] = "NORMAL"

    # Market share
    try:
        war = call_engine(engines.get("market_share_engine"), "apply_market_share", war, sales_internal, market_size)
    except Exception as e:
        # fallback ringan, tidak matikan war room
        st.info(f"Market share engine skip (fallback): {e}")
        if "estimated_market_volume" not in war.columns:
            war["estimated_market_volume"] = None
        war["share_at_risk_pct"] = war.get("share_at_risk_pct", 0.0)
        war["impact_level"] = war.get("impact_level", "LOW")

    # DCZ decision (INI YANG KRUSIAL)
    try:
        dcz = engines.get("dcz_engine")
        war = call_engine(dcz, "decide_dcz", war)
    except Exception as e:
        st.warning(f"DCZ engine gagal (fallback HOLD): {e}")
        war["dcz_decision"] = "HOLD"
        war["dcz_reason"] = "dcz_engine_not_loaded"

    # Counter move
    try:
        cm = engines.get("counter_move_engine")
        # kalau engine mendukung parameter, tetap aman (kita set session_state)
        st.session_state["counter_move_cfg"] = {
            "ladder_cap_pct": ladder_cap,
            "default_duration_days": default_days,
            "bait_gap_rp": bait_gap,
        }
        war = call_engine(cm, "generate_counter_move", war)
    except Exception as e:
        st.info(f"Counter-move engine skip (fallback HOLD): {e}")
        war["counter_move"] = "HOLD - Monitor (no action)"
        war["counter_channel"] = "All"
        war["counter_duration_days"] = default_days

    # -------------------------------------------------
    # DEFAULTS (ANTI KOSONG)
    # -------------------------------------------------
    war = ensure_columns(
        war,
        {
            "product_id": "-",
            "product_name": "-",
            "pecahan_gram": 0,
            "product_role": "UNKNOWN",
            "demand_trend": "FLAT",
            "forecast_confidence": 0.0,
            "inventory_cover_days": None,
            "min_comp_price": None,
            "gap_price": None,
            "impact_level": "LOW",
            "market_share_pct": 0.0,
            "share_at_risk_pct": 0.0,
            "dcz_decision": "HOLD",
            "dcz_reason": "-",
            "counter_move": "HOLD - Monitor (no action)",
            "counter_channel": "All",
            "counter_duration_days": default_days,
        },
    )

    # -------------------------------------------------
    # PRIORITY SORT
    # -------------------------------------------------
    priority_map = {"FIGHT": 4, "PROMO_ZONE": 3, "NO_FIGHT": 2, "HOLD": 1, "LET_GO": 0}
    war["priority_score"] = war["dcz_decision"].map(priority_map).fillna(1).astype(int)
    view = war.sort_values(["priority_score", "forecast_confidence"], ascending=[False, False]).copy()

    # -------------------------------------------------
    # KPI STRIP
    # -------------------------------------------------
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Produk", len(view))
    k2.metric("🔴 FIGHT", int((view["dcz_decision"] == "FIGHT").sum()))
    k3.metric("🟠 PROMO", int((view["dcz_decision"] == "PROMO_ZONE").sum()))
    k4.metric("🟢 NO FIGHT", int((view["dcz_decision"] == "NO_FIGHT").sum()))
    k5.metric("⚪ LET GO", int((view["dcz_decision"] == "LET_GO").sum()))
    k6.metric("🟡 HOLD", int((view["dcz_decision"] == "HOLD").sum()))

    st.divider()

    # -------------------------------------------------
    # VIEW MODE
    # -------------------------------------------------
    st.markdown("### 🧭 View Mode")
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
        top = view.head(5)

        for _, r in top.iterrows():
            title = f"{dcz_badge(r['dcz_decision'])} — {r['product_name']}"

            st.markdown(
                f"""
                <div style="
                    padding:14px;
                    margin-bottom:10px;
                    border-radius:12px;
                    background:#f5f8ff;
                    border:1px solid rgba(0,0,0,0.06);
                ">
                  <div style="font-size:16px;font-weight:700;">{title}</div>
                  <div style="margin-top:6px;font-size:13px;">
                    Role: <b>{r['product_role']}</b> |
                    Demand: <b>{r['demand_trend']}</b> |
                    Conf: <b>{safe_float(r['forecast_confidence']):.3f}</b>
                  </div>
                  <div style="margin-top:6px;font-size:13px;">
                    Counter-Move: <b>{r['counter_move']}</b><br/>
                    Channel: {r['counter_channel']} | Durasi: {int(safe_float(r['counter_duration_days'], default_days))} hari
                  </div>
                  <div style="margin-top:6px;font-size:12px;opacity:0.75;">
                    Reason: {r.get("dcz_reason","-")}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("## 📌 Ringkasan Keputusan")
        cols = [
            "product_id",
            "product_role",
            "dcz_decision",
            "demand_trend",
            "forecast_confidence",
            "counter_move",
            "counter_channel",
            "counter_duration_days",
        ]
        st.dataframe(view[cols], use_container_width=True)

    # =================================================
    # ANALYST VIEW
    # =================================================
    else:
        st.markdown("## 🔍 Analyst View — Detail Lengkap")
        st.dataframe(view, use_container_width=True)

    st.caption("War Room FINAL — engine boleh gagal, command center tidak boleh jatuh.")
