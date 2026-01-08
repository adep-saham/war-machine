import streamlit as st
import pandas as pd

from loaders.data_loader import safe_read_csv
from engines.pricing_engine import build_pricing_snapshot
from engines.guardrail_engine import apply_guardrail
from engines.market_share_engine import apply_market_share
from engines.intent_engine import detect_loss_intent
from engines.dcz_engine import apply_dont_compete_zone
from engines.counter_move_engine import generate_counter_moves
from engines.promo_simulator import simulate_promo_portfolio

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
    intent = row.get("competitor_intent")
    intent_bonus = 0.5 if intent == "MARKET_GRAB" else (-0.3 if intent == "BAIT / SIGNAL" else 0)
    return impact_w * (1 + risk) + bonus + intent_bonus


# ======================
# WAR ROOM
# ======================
def render_war_room():
    st.subheader("⚔️ War Room – Command Center")
    st.caption("Pricing + Guardrail + Market Impact + Intent + DCZ + Counter-Move + Promo Simulator")

    # ----------------------
    # Controls
    # ----------------------
    with st.expander("⚙️ Pengaturan Counter-Move", expanded=False):
        max_disc = st.slider("Batas diskon ladder (%)", 0.0, 5.0, 2.0, 0.5) / 100
        base_days = st.slider("Durasi default (hari)", 1, 14, 5)
        extreme_gap = st.number_input("Extreme gap (Rp) untuk BAIT", value=500_000, step=50_000)

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
    # COUNTER MOVE
    # ======================
    war = generate_counter_moves(
        war,
        max_discount_pct=max_disc,
        base_duration_days=base_days
    )

    # ======================
    # PROMO SIMULATOR (ANTI PRICE WAR)
    # ======================
    promo_rows = []

    for _, r in war.iterrows():
        try:
            base_price = r.get("price_sell")
            base_cost = r.get("cost_unit") or r.get("floor_price")
            volume = r.get("sales_volume", 1)

            if base_price and base_cost:
                promos = simulate_promo_portfolio(
                    base_price=float(base_price),
                    base_cost=float(base_cost),
                    volume=int(volume)
                )
                best = promos[0] if promos else None
            else:
                best = None
        except Exception:
            best = None

        promo_rows.append({
            "promo_best": getattr(best, "promo_type", None),
            "promo_effective_price": getattr(best, "effective_price", None),
            "promo_margin_pct": getattr(best, "margin_pct", None),
            "promo_war_risk": getattr(best, "war_risk", None),
            "promo_rationale": getattr(best, "rationale", None),
        })

    war = pd.concat([war.reset_index(drop=True), pd.DataFrame(promo_rows)], axis=1)

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
    # DISPLAY
    # ======================
    view = war.sort_values("priority_score", ascending=False).copy()

    for col in [
        "price_sell", "min_comp_price", "gap_price", "floor_price",
        "sim_price_5", "sim_price_10", "sim_price_20",
        "promo_effective_price"
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
        "price_sell",
        "min_comp_price",
        "gap_price",
        "impact_level",
        "competitor_intent",
        "compete_decision",
        "counter_move_short",
        "counter_channel",
        "counter_duration_days",
        "promo_best",
        "promo_war_risk",
    ]

    st.dataframe(view[summary_cols], use_container_width=True, hide_index=True)

    # ======================
    # ACTION BOARD
    # ======================
    st.subheader("🚨 Action Board (Top 5)")

    top = view.head(5)
    if top.empty:
        st.success("✅ Tidak ada prioritas kritikal.")
    else:
        for _, r in top.iterrows():
            st.info(
                f"**{r.get('product_name')} ({r.get('product_id')})**  \n"
                f"Intent: **{r.get('competitor_intent')}** | DCZ: **{r.get('compete_decision')}** | Impact: **{r.get('impact_level')}**  \n\n"
                f"➡️ **Counter-Move**: **{r.get('counter_move')}**  \n"
                f"🎁 **Promo Alternatif**: **{r.get('promo_best','-')}** (Risk: {r.get('promo_war_risk','-')})  \n"
                f"📍 Channel: **{r.get('counter_channel')}** | ⏱️ **{r.get('counter_duration_days')} hari**"
            )

    # ======================
    # DETAIL DRILL DOWN
    # ======================
    st.subheader("🔍 Detail per Produk")

    for _, r in view.iterrows():
        with st.expander(f"{r['product_name']} ({r['product_id']})"):
            st.markdown(f"""
**Harga Saat Ini**: {r.get('price_sell','-')}  
**Harga Kompetitor**: {r.get('min_comp_price','-')}  
**Gap Harga**: {r.get('gap_price','-')}  

**Intent Kompetitor**: **{r.get('competitor_intent','-')}**  
**DCZ Decision**: **{r.get('compete_decision','-')}**  
**Counter-Move**: **{r.get('counter_move','-')}**  
Channel: {r.get('counter_channel','-')} | Durasi: {r.get('counter_duration_days','-')} hari  
""")

            st.markdown("**Promo Simulator (Anti Price War)**")
            st.write({
                "Promo": r.get("promo_best"),
                "Effective Price": format_idr(r.get("promo_effective_price")) if r.get("promo_effective_price") else "-",
                "Margin (%)": r.get("promo_margin_pct"),
                "War Risk": r.get("promo_war_risk"),
            })
            st.caption(r.get("promo_rationale", ""))

            st.markdown("**Simulasi Penurunan Harga**")
            st.write({
                "Turun 0.5%": f"{r.get('sim_price_5')} ({r.get('sim_ok_5')})",
                "Turun 1%": f"{r.get('sim_price_10')} ({r.get('sim_ok_10')})",
                "Turun 2%": f"{r.get('sim_price_20')} ({r.get('sim_ok_20')})",
            })

    st.caption("War Room ini menghasilkan keputusan yang bisa dieksekusi — bukan sekadar analisa.")


