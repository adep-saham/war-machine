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
from engines.demand_forecast_engine import attach_demand_signals, ForecastConfig
from engines.product_performance_engine import compute_product_performance
from engines.dcz_decision_engine import decide_dcz


# Promo Simulator (interactive what-if)
# Pastikan file ini ada sesuai modul yang sudah dibuat sebelumnya:
# engines/promo_simulator.py
from engines.promo_simulator import run_promo_simulation, PromoInput


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


def _pick_cost_row(r: pd.Series) -> float:
    """
    Prioritas cost untuk simulator:
    1) cost_unit (kalau ada)
    2) floor_price (fallback)
    """
    c = r.get("cost_unit", None)
    if c is None or (isinstance(c, float) and pd.isna(c)):
        c = r.get("floor_price", None)
    return _safe_float(c) or 0.0


def _pick_volume_row(r: pd.Series) -> int:
    """
    Volume untuk simulator:
    - sales_volume kalau ada
    - fallback 100
    """
    v = r.get("sales_volume", None)
    try:
        v = int(v) if v is not None and not (isinstance(v, float) and pd.isna(v)) else 100
    except Exception:
        v = 100
    return max(v, 1)


# ======================
# WAR ROOM
# ======================
def render_war_room():
    st.subheader("⚔️ War Room – Command Center")
    st.caption("Pricing + Guardrail + Market Impact + Intent + DCZ + Counter-Move + Promo Simulator (What-if)")

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
    # TABS (A: panel terpisah)
    # ======================
    tab_cc, tab_promo = st.tabs(["🛰️ Command Center", "🎛️ Promo Simulator (What-if)"])

    # =========================================================
    # TAB 1 — COMMAND CENTER (war room utama)
    # =========================================================
    with tab_cc:
        # ----------------------
        # Controls (UX)
        # ----------------------
        with st.expander("⚙️ Pengaturan Counter-Move (opsional)", expanded=False):
            max_disc = st.slider("Batas diskon ladder (%)", 0.0, 5.0, 0.5, 0.5) / 100.0
            base_days = st.slider("Durasi default (hari)", 1, 14, 3, 1)
            extreme_gap = st.number_input("Extreme gap (Rp) untuk deteksi BAIT", value=500_000, step=50_000)

        # ======================
        # CORE ENGINE
        # ======================
        war = build_pricing_snapshot(price_company, master, price_comp)
        war = apply_guardrail(war)
        war = apply_market_share(war, sales, market)
        cfg = ForecastConfig(date_col="date", sku_col="product_id", qty_col="qty")
        war = attach_demand_signals(war, sales, cfg=cfg, inventory_col="stock_on_hand")

        
        # normalize numeric
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
        war = compute_product_performance(
        war,
        price_col="price_sell",
        cost_col="cost_unit",
        volume_col="sales_volume",
        min_comp_col="min_comp_price"
        )

        war[["dcz_decision", "dcz_reason"]] = war.apply(
            lambda r: decide_dcz(r),
            axis=1,
            result_type="expand"
        )
        
        # ======================
        # COUNTER MOVE
        # ======================
        war = generate_counter_moves(war, max_discount_pct=max_disc, base_duration_days=base_days)

        # ======================
        # KPI HEADER
        # ======================
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Produk", len(war))
        c2.metric("ATTACK", int((war["status"] == "ATTACK").sum()) if "status" in war.columns else 0)
        c3.metric("FIGHT", int((war["compete_decision"] == "FIGHT").sum()) if "compete_decision" in war.columns else 0)
        c4.metric("DCZ LET_GO", int((war["compete_decision"] == "LET_GO").sum()) if "compete_decision" in war.columns else 0)
        c5.metric("BLOCKED", int((war["guardrail_status"] == "BLOCKED").sum()) if "guardrail_status" in war.columns else 0)
        c6.metric("MARKET_GRAB", int((war["competitor_intent"] == "MARKET_GRAB").sum()) if "competitor_intent" in war.columns else 0)

        st.divider()

        # ======================
        # DISPLAY (format angka display only)
        # ======================
        view = war.sort_values("priority_score", ascending=False).copy()

        for col in ["price_sell", "min_comp_price", "gap_price", "floor_price",
                    "sim_price_5", "sim_price_10", "sim_price_20"]:
            if col in view.columns:
                view[col] = view[col].apply(format_idr)

        for col in ["sim_ok_5", "sim_ok_10", "sim_ok_20"]:
            if col in view.columns:
                view[col] = view[col].apply(lambda x: "✅" if x else "❌")

        # ======================
        # DECISION SUMMARY (Ringkas)
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
        summary_cols = [c for c in summary_cols if c in view.columns]
        st.dataframe(view[summary_cols], use_container_width=True, hide_index=True)

        # ======================
        # ACTION BOARD (Top 5)
        # ======================
        st.subheader("🚨 Action Board (Top 5)")

        top = war.sort_values("priority_score", ascending=False).head(5)
        if top.empty:
            st.success("✅ Tidak ada prioritas kritikal.")
        else:
            for _, r in top.iterrows():
                badge = "🔴" if (r.get("compete_decision") == "FIGHT" and r.get("impact_level") == "HIGH") else \
                        "🟠" if (r.get("compete_decision") == "FIGHT") else "🟢"

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
        # DETAIL (Drill-down)
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

    # =========================================================
    # TAB 2 — PROMO SIMULATOR (What-if) — PANEL TERPISAH
    # =========================================================
    with tab_promo:
        st.subheader("🎛️ Promo Simulator – What-if Engine")
        st.caption("Ini benar-benar simulator: Anda mainkan discount/cashback/bundle/fee → lihat effective price, margin, dan war risk.")

        # Rebuild minimal war snapshot (agar tab ini tetap bisa jalan walau user belum buka tab 1)
        # (tetap pakai engine yang sama, tapi tanpa format)
        war2 = build_pricing_snapshot(price_company, master, price_comp)
        war2 = apply_guardrail(war2)

        # normalize numeric
        for c in ["price_sell", "floor_price"]:
            if c in war2.columns:
                war2[c] = war2[c].apply(_safe_float)

        if war2.empty:
            st.warning("Data snapshot kosong. Cek file input.")
            return

        # ---- picker produk
        war2["__label__"] = war2.apply(
            lambda r: f"{r.get('product_name','-')} ({r.get('product_id','-')})", axis=1
        )
        selected = st.selectbox("Pilih produk", options=war2["__label__"].tolist(), index=0)
        row = war2.loc[war2["__label__"] == selected].iloc[0]

        base_price = _safe_float(row.get("price_sell", 0)) or 0.0
        base_cost = _pick_cost_row(row)
        default_volume = _pick_volume_row(row)

        st.divider()

        # ---- simulator controls (INI slider khusus simulator)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            discount = st.slider("Diskon (%)", 0.0, 5.0, 0.0, 0.5)
        with c2:
            cashback = st.slider("Cashback (%)", 0.0, 5.0, 0.0, 0.5)
        with c3:
            extra_fee = st.slider("Fee / Admin (%)", 0.0, 3.0, 0.0, 0.25)
        with c4:
            bundle_value = st.slider("Value Bundle (%)", 0.0, 10.0, 0.0, 1.0)

        volume = st.number_input("Volume simulasi (unit)", min_value=1, value=int(default_volume), step=10)

        # ---- run simulation
        promo_input = PromoInput(
            base_price=float(base_price),
            base_cost=float(base_cost),
            volume=int(volume),
            discount_pct=float(discount),
            cashback_pct=float(cashback),
            extra_fee_pct=float(extra_fee),
            bundle_value_pct=float(bundle_value),
        )
        result = run_promo_simulation("CUSTOM_SIMULATION", promo_input)

        st.divider()

        # ---- Results (terasa simulator)
        st.markdown("### 📊 Output Simulator (Real-time)")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Harga Awal", format_idr(base_price))
        m2.metric("Effective Price", format_idr(result.effective_price))
        m3.metric("Margin (%)", f"{result.margin_pct:.2f}")
        m4.metric("War Risk", str(result.war_risk))

        # Perceived price (kalau ada)
        if hasattr(result, "perceived_price"):
            st.write({"Perceived Price": format_idr(result.perceived_price)})

        st.write({
            "Revenue (simulasi)": format_idr(result.revenue) if hasattr(result, "revenue") else "-",
            "Margin Delta (%)": f"{result.margin_delta_pct:.2f}" if hasattr(result, "margin_delta_pct") else "-",
        })

        st.info(result.rationale)

        st.divider()

        # ---- Quick compare (baseline vs simulated)
        st.markdown("### 🆚 Baseline vs Simulasi")

        # Baseline: no promo
        baseline_input = PromoInput(
            base_price=float(base_price),
            base_cost=float(base_cost),
            volume=int(volume),
            discount_pct=0.0,
            cashback_pct=0.0,
            extra_fee_pct=0.0,
            bundle_value_pct=0.0,
        )
        baseline = run_promo_simulation("BASELINE", baseline_input)

        compare = pd.DataFrame([
            {
                "Scenario": "BASELINE",
                "Effective Price": baseline.effective_price,
                "Margin %": baseline.margin_pct,
                "War Risk": baseline.war_risk,
            },
            {
                "Scenario": "SIMULATION",
                "Effective Price": result.effective_price,
                "Margin %": result.margin_pct,
                "War Risk": result.war_risk,
            }
        ])

        compare["Effective Price"] = compare["Effective Price"].apply(format_idr)
        st.dataframe(compare, use_container_width=True, hide_index=True)

        st.caption("Promo Simulator adalah alat WHAT-IF. Keputusan eksekusi tetap di Command Center (DCZ + Counter-Move).")
