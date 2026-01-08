import streamlit as st
import pandas as pd
import os

# ======================
# CONFIG
# ======================
DATA_DIR = "data"


# ======================
# HELPER
# ======================
def safe_read_csv(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        return pd.read_csv(path)
    return None


def format_idr(x):
    if pd.isna(x):
        return "-"
    try:
        return f"{int(x):,}".replace(",", ".")
    except:
        return "-"


# ======================
# MAIN WAR ROOM
# ======================
def render_war_room():
    st.subheader("⚔️ War Room")
    st.caption("Snapshot sederhana: company vs competitor termurah")

    # ===== LOAD DATA HASIL UPLOAD =====
    master = safe_read_csv("master_product.csv")
    price_company = safe_read_csv("price_company.csv")
    price_comp = safe_read_csv("price_competitor.csv")

    # ===== VALIDASI DATA =====
    if master is None or price_company is None or price_comp is None:
        st.warning("⚠️ Data belum lengkap. Silakan upload semua data di tab Upload Data.")
        return

    # ===== JOIN MASTER + HARGA COMPANY =====
    war = price_company.merge(
        master[["product_id", "product_name", "pecahan_gram"]],
        on="product_id",
        how="left"
    )

    # ===== HARGA COMPETITOR TERENDAH =====
    comp_min = (
        price_comp
        .groupby("product_id", as_index=False)["price_sell"]
        .min()
        .rename(columns={"price_sell": "min_comp_price"})
    )

    war = war.merge(comp_min, on="product_id", how="left")

    # ===== HITUNG GAP =====
    war["gap_price"] = war["price_sell"] - war["min_comp_price"]

    # ===== STATUS WAR =====
    def war_status(row):
        if pd.isna(row["min_comp_price"]):
            return "🟢 DEFENSIVE"
        if row["gap_price"] > 0:
            return "🔴 ATTACK"
        return "🟢 DEFENSIVE"

    war["status"] = war.apply(war_status, axis=1)

    # ===== FORMAT ANGKA UNTUK DISPLAY =====
    for col in ["price_sell", "min_comp_price", "gap_price"]:
        war[col] = war[col].apply(format_idr)

    # ===== SORT: PALING BERBAHAYA DI ATAS =====
    war = war.sort_values("status", ascending=False)

    # ===== TAMPILKAN TABEL =====
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

    st.caption("🔴 ATTACK = harga company lebih mahal dari competitor termurah")
