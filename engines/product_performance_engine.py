import pandas as pd


def compute_product_performance(war: pd.DataFrame, sales_internal: pd.DataFrame):
    df = war.copy()

    # === FORCE COLUMN NORMALIZATION ===
    df.columns = df.columns.astype(str)

    if "price_sell" not in df.columns:
        df["price_sell"] = 0

    # === SALES AGGREGATION ===
    if sales_internal is not None and len(sales_internal) > 0:
        sales_internal.columns = sales_internal.columns.astype(str)

        if "volume" not in sales_internal.columns:
            sales_internal["volume"] = 0

        sales_agg = (
            sales_internal
            .groupby("product_id", as_index=False)
            .agg(sales_volume=("volume", "sum"))
        )

        df = df.merge(sales_agg, on="product_id", how="left")
    else:
        df["sales_volume"] = 0

    df["sales_volume"] = df["sales_volume"].fillna(0)

    # === REVENUE ===
    df["revenue"] = df["sales_volume"] * df["price_sell"]

    # === MARKET SHARE ===
    if "estimated_market_volume" in df.columns:
        df["market_share_pct"] = df.apply(
            lambda r: r["sales_volume"] / r["estimated_market_volume"]
            if r["estimated_market_volume"] not in [0, None]
            else 0,
            axis=1,
        )
    else:
        df["market_share_pct"] = 0

    # === FLAG ===
    df["performance_flag"] = "NORMAL"
    df.loc[df["sales_volume"] == 0, "performance_flag"] = "NO_SALES"
    df.loc[df["market_share_pct"] < 0.05, "performance_flag"] = "LOW_SHARE"

    return df
