import streamlit as st
import pandas as pd
import os

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def upload_csv(label, filename, required_cols=None):
    file = st.file_uploader(label, type="csv", key=filename)
    if file:
        df = pd.read_csv(file)
        if required_cols:
            missing = set(required_cols) - set(df.columns)
            if missing:
                st.error(f"Kolom kurang: {missing}")
                return None
        path = os.path.join(DATA_DIR, filename)
        df.to_csv(path, index=False)
        st.success(f"✅ {filename} tersimpan ({len(df)} baris)")
        return df
    return None


def render_upload_data():
    st.subheader("📤 Upload Data (Manual)")

    upload_csv(
        "Master Product",
        "master_product.csv",
        ["product_id","product_name","pecahan_gram"]
    )

    upload_csv(
        "Harga Company",
        "price_company.csv",
        ["product_id","price_sell"]
    )

    upload_csv(
        "Harga Competitor",
        "price_competitor.csv",
        ["competitor_name","product_id","price_sell"]
    )

    upload_csv(
        "Sales Internal",
        "sales_internal.csv",
        ["date","product_id","volume_gram"]
    )

    upload_csv(
        "Market Size",
        "market_size.csv",
        ["date","product_id","estimated_market_volume"]
    )
