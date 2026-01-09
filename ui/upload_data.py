import streamlit as st
import pandas as pd

# =====================================================
# Helper: Load CSV + Validasi Kolom
# =====================================================
def load_csv(uploaded_file, required_cols=None):
    df = pd.read_csv(uploaded_file)
    if required_cols:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            st.error(f"Kolom kurang: {missing}")
            return None
    return df


# =====================================================
# MAIN UPLOAD UI
# =====================================================
def render_upload_data():

    st.markdown("## ☁️ Upload Data (Manual)")

    # -------------------------------------------------
    # 1. MASTER PRODUCT
    # -------------------------------------------------
    st.subheader("Master Product")
    f = st.file_uploader("Upload Master Product", type="csv", key="up_master_product")
    if f:
        df = load_csv(
            f,
            required_cols=["product_id", "product_name", "pecahan_gram"]
        )
        if df is not None:
            st.session_state["master_product"] = df
            st.success(f"master_product.csv tersimpan ({len(df)} baris)")

    # -------------------------------------------------
    # 2. PRICE COMPANY
    # -------------------------------------------------
    st.subheader("Harga Company")
    f = st.file_uploader("Upload Harga Company", type="csv", key="up_price_company")
    if f:
        df = load_csv(
            f,
            required_cols=["product_id", "price_sell", "cost_unit"]
        )
        if df is not None:
            st.session_state["price_company"] = df
            st.success(f"price_company.csv tersimpan ({len(df)} baris)")

    # -------------------------------------------------
    # 3. PRICE COMPETITOR
    # -------------------------------------------------
    st.subheader("Harga Competitor")
    f = st.file_uploader("Upload Harga Competitor", type="csv", key="up_price_competitor")
    if f:
        df = load_csv(
            f,
            required_cols=["product_id", "competitor_id", "price_sell"]
        )
        if df is not None:
            st.session_state["price_competitor"] = df
            st.success(f"price_competitor.csv tersimpan ({len(df)} baris)")

    # -------------------------------------------------
    # 4. SALES INTERNAL
    # -------------------------------------------------
    st.subheader("Sales Internal")
    f = st.file_uploader("Upload Sales Internal", type="csv", key="up_sales_internal")
    if f:
        df = load_csv(
            f,
            required_cols=["date", "product_id", "volume_gram"]
        )
        if df is not None:
            df["date"] = pd.to_datetime(df["date"])
            st.session_state["sales_internal"] = df
            st.success(f"sales_internal.csv tersimpan ({len(df)} baris)")

    # -------------------------------------------------
    # 5. MARKET SIZE
    # -------------------------------------------------
    st.subheader("Market Size")
    f = st.file_uploader("Upload Market Size", type="csv", key="up_market_size")
    if f:
        df = load_csv(
            f,
            required_cols=["date", "product_id", "estimated_market_volume"]
        )
        if df is not None:
            df["date"] = pd.to_datetime(df["date"])
            st.session_state["market_size"] = df
            st.success(f"market_size.csv tersimpan ({len(df)} baris)")

    # -------------------------------------------------
    # 6. ENGINE REGISTRATION (FUNCTION-BASED, AMAN)
    # -------------------------------------------------
    if "engines" not in st.session_state:
        try:
            import engines.pricing_engine as pricing_engine
            import engines.guardrail_engine as guardrail_engine
            import engines.product_performance_engine as product_performance_engine
            import engines.market_share_engine as market_share_engine
            import engines.dcz_engine as dcz_engine
            import engines.counter_move_engine as counter_move_engine

            st.session_state["engines"] = {
                "pricing_engine": pricing_engine,
                "guardrail_engine": guardrail_engine,
                "product_performance_engine": product_performance_engine,
                "market_share_engine": market_share_engine,
                "dcz_engine": dcz_engine,
                "counter_move_engine": counter_move_engine,
            }

            st.success("✅ Engines berhasil diregistrasi (function-based)")

        except Exception as e:
            st.error(f"❌ Gagal load engines: {e}")

    # -------------------------------------------------
    # DEBUG (boleh dihapus setelah stabil)
    # -------------------------------------------------
    st.divider()
    st.caption("DEBUG session_state keys:")
    st.write(list(st.session_state.keys()))
