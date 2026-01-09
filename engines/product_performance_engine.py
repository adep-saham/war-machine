import pandas as pd


def compute_product_performance(
    war: pd.DataFrame,
    sales_internal: pd.DataFrame,
    price_col: str = "price_sell",
    volume_col: str = "volume",
):
    """
    Compute product performance metrics:
    - sales_volume
    - revenue
    - market_share (if market size available)
    Defensive against missing columns.
    """

    df = war.copy()

    # =====================================================
    # 1. VALIDASI & NORMALISASI KOLOM INPUT
    # =====================================================
    if price_col is None or price_col not in df.columns:
        df["price_sell"] = df.get("price_sell", 0)
        price_col = "price_sell"

    if volume_col is None:
        volume_col = "volume"

    # =====================================================
    # 2. AGREGASI SALES INTERNAL
    # =====================================================
    if sales_internal is not None and len(sales_internal) > 0:
        sales_agg = (
            sales_internal
            .groupby("product_id", as_index=False)
            .agg(
                sales_volume=(volume_col, "sum"),
            )
        )
        df = df.merge(sales_agg, on="product_id", how="left")
    else:
        df["sales_volume"] = 0

    df["sales_volume"] = df["sales_volume"].fillna(0)

    # =====================================================
    # 3. HITUNG REVENUE
    # =====================================================
    df["revenue"] = df["sales_volume"] * df[price_col]

    # =====================================================
    # 4. MARKET SHARE (JIKA ADA)
    # =====================================================
    if "estimated_market_volume" in df.columns:
        df["market_share_pct"] = df.apply(
            lambda r: (
                r["sales_volume"] / r["estimated_market_volume"]
                if r["estimated_market_volume"] not in [0, None]
                else 0
            ),
            axis=1,
        )
    else:
        df["market_share_pct"] = 0

    # =====================================================
    # 5. PERFORMANCE FLAG (UNTUK DCZ / UI)
    # =====================================================
    df["performance_flag"] = "NORMAL"
    df.loc[df["sales_volume"] == 0, "performance_flag"] = "NO_SALES"
    df.loc[df["market_share_pct"] < 0.05, "performance_flag"] = "LOW_SHARE"

    return df
