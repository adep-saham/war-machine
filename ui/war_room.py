import streamlit as st

from loaders.data_loader import safe_read_csv
from engines.pricing_engine import build_pricing_snapshot
from engines.guardrail_engine import apply_guardrail
from engines.market_share_engine import apply_market_share
from utils.formatters import format_idr


def render_war_room():
    st.subheader("⚔️ War Room – Decision Engine")

    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")
    sales = safe_read_csv("sales_internal.csv")
    market = safe_read_csv("market_size.csv")

    if master is None or price_company is None or price_comp is None:
        st.warning("Upload data wajib terlebih dahulu.")
        return

    war = build_pricing_snapshot(price_company, master, price_comp)
    war = apply_guardrail(war)
    war = apply_market_share(war, sales, market)

    for col in ["price_sell", "min_comp_price", "gap_price", "floor_price"]:
        war[col] = war[col].apply(format_idr)

    st.dataframe(
        war[
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
