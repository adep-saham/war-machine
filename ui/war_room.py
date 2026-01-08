import streamlit as st
import pandas as pd

from loaders.data_loader import safe_read_csv
from engines.pricing_engine import build_pricing_snapshot
from engines.guardrail_engine import apply_guardrail
from engines.market_share_engine import apply_market_share
from utils.formatters import format_idr


def render_war_room():
    st.subheader("⚔️ War Room – Decision Engine")
    st.caption("Ringkasan keputusan harga, guardrail, dan dampak market share")

    # ======================
    # LOAD DATA
    # ======================
    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")
    sales = safe_read_csv("sales_internal.csv")
    market = safe_read_csv("market_size.csv")

    if master is None or price_company is None or price_comp is None:
        st.warning("⚠️ Upload data wajib terlebih dahulu.")
        return

    # ======================
    # BUILD WAR TABLE
    # ======================
    war = build_pricing_snapshot(price_company, master, price_comp)
    war = apply_guardrail(war)
    war = apply_market_share(war, sales, market)

    # ======================
    # KPI HEADER (EXECUTIVE VIEW)
    # ======================
    col1, col2, col3, col4 = st.columns(4)

    total_product = len(war)
    attack_cnt = (war["status"] == "ATTACK").sum()
    blocked_cnt = (war["guardrail_status"] == "BLOCKED").sum()
    high_impact = (war["impact_level"] == "HIGH").sum()

    col1.metric("Produk Dipantau", total_product)
    col2.metric("ATTACK", attack_cnt)
    col3.metric("BLOCKED", blocked_cnt)
    col4.metric("HIGH Impact", high_impact)

    st.divider()

    # ======================
    # FILTER FOKUS
    # ======================
    focus = st.selectbox(
        "🎯 Fokus Tampilan",
        ["Semua Produk", "ATTACK saja", "ATTACK + BLOCKED", "HIGH Impact"]
    )

    view = war.copy()

    if focus == "ATTACK saja":
        view = view[view["status"] == "ATTACK"]
    elif focus == "ATTACK + BLOCKED":
        view = view[
            (view["status"] == "ATTACK") &
            (view["guardrail_status"] == "BLOCKED")
        ]
    elif focus == "HIGH Impact":
        view = view[view["impact_level"] == "HIGH"]

    # ======================
    # FORMAT DISPLAY
    # ======================
    for col in ["price_sell", "min_comp_price", "gap_price", "floor_price"]:
        if col in view.columns:
            view[col] = view[col].apply(format_idr)

    # Urutkan dari yang paling berbahaya
    view = view.sort_values(
        ["impact_level", "gap_price"],
        ascending=[False, False],
        na_position="last"
    )

    # ======================
    # DECISION TABLE
    # ======================
    st.subheader("📊 Decision Table")

    st.dataframe(
        view[
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
                "status",
            ]
        ],
        use_container_width=True
    )

    # ======================
    # PRIORITY ACTION LIST
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
                f"Market Share {r['market_share_pct']}% | "
                f"Risiko hilang {r['share_at_risk_pct']}%"
            )

    st.caption("ATTACK = harga kalah | BLOCKED = tidak bisa turunkan harga | Impact = risiko market share")
