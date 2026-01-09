import streamlit as st
import pandas as pd

# ===============================
# Helper
# ===============================
def load_csv(uploaded_file, required_cols=None):
    df = pd.read_csv(uploaded_file)
    if required_cols:
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            st.error(f"Kolom kurang: {missing}")
            return None
    return df


# ===============================
# MAIN UPLOAD UI
# ===============================
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
    # 6. ENGINE INITIALIZATION (KRITIS)
    # -------------------------------------------------
    if "engines" not in st.session_state:
        try:
            from engines.pricing_engine import PricingEngine
            from engines.guardrail_engine import GuardrailEngine
            from engines.product_performance_engine import ProductPerformanceEngine
            from engines.market_share_engine import MarketShareEngine
            from engines.dcz_engine import DCZEngine
            from engines.counter_move_engine import CounterMoveEngine

            st.session_state["engines"] = {
                "pricing_engine": PricingEngine(),
                "guardrail_engine": GuardrailEngine(),
                "product_performance_engine": ProductPerformanceEngine(),
                "market_share_engine": MarketShareEngine(),
                "dcz_engine": DCZEngine(),
                "counter_move_engine": CounterMoveEngine(),
            }

            st.success("✅ Engines siap digunakan")

        except Exception as e:
            st.error(f"Gagal load engines: {e}")

    # -------------------------------------------------
    # DEBUG (BOLEH DIHAPUS SETELAH OK)
    # -------------------------------------------------
    st.divider()
    st.caption("DEBUG session_state keys:")
    st.write(list(st.session_state.keys()))
