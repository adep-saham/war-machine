import streamlit as st
import pandas as pd
import os

DATA_DIR = "data"

def safe_read_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        return pd.read_csv(path)
    return None


def render_war_room():
    st.subheader("⚔️ War Room")

    # === LOAD DATA HASIL UPLOAD ===
    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")

    # === VALIDASI DATA ===
    if master is None or price_company is None or price_comp is None:
        st.warning("Data belum lengkap. Silakan upload semua data di tab Upload Data.")
        return

    # === JOIN SEDERHANA (MVP) ===
    war = price_company.merge(
        master[["product_id", "product_name", "pecahan_gram"]],
        on="product_id",
        how="left"
    )

    # Harga competitor terendah per produk
    comp_min = (
        price_comp
        .groupby("product_id", as_index=False)["price_sell"]
        .min()
        .rename(columns={"price_sell": "min_comp_price"})
    )

    war = war.merge(comp_min, on="product_id", how="left")

    # Gap harga
    war["gap_price"] = war["price_sell"] - war["min_comp_price"]

    # Status sederhana
    war["status"] = war["gap_price"].apply(
        lambda x: "ATTACK" if x > 0 else "DEFENSIVE"
    )

    st.caption("Snapshot sederhana: company vs competitor termurah")

    st.dataframe(
        war[
            [
                "product_id",
                "product_name",
                "pecahan_gram",
                "price_sell",
                "min_comp_price",
                "gap_price",
                "status",
            ]
        ],
        use_container_width=True
    )
