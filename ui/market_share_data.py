import streamlit as st
import pandas as pd

def render_market_share_upload():

    st.subheader("📊 Market Share Data")

    sales = st.file_uploader("Upload sales_internal.csv", type="csv")
    if sales:
        df = pd.read_csv(sales, parse_dates=["date"])
        df.to_csv("data/sales_internal.csv", index=False)
        st.success(f"Sales internal tersimpan ({len(df)} baris)")

    market = st.file_uploader("Upload market_size.csv", type="csv")
    if market:
        df = pd.read_csv(market, parse_dates=["date"])
        df.to_csv("data/market_size.csv", index=False)
        st.success(f"Market size tersimpan ({len(df)} baris)")
