# ============================================================
# engines/market_share_engine.py
# Robust version (anti KeyError)
# ============================================================

import pandas as pd


def apply_market_share(war: pd.DataFrame, sales: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """
    Attach market share & impact signals.
    Robust against missing optional columns:
    - status
    - guardrail_status
    """

    if war is None or war.empty:
        return war

    df = war.copy()

    # =========================
    # SAFETY DEFAULTS (FIX UTAMA)
    # =========================
    if "status" not in df.columns:
        df["status"] = "NORMAL"

    if "guardrail_status" not in df.columns:
        df["guardrail_status"] = "OK"

    # =========================
    # BASIC SALES AGG
    # =========================
    if sales is not None and not sales.empty:
        vol = (
            sales.groupby("product_id", as_index=False)["sales_volume"]
            .sum()
            .rename(columns={"sales_volume": "company_volume"})
        )
        df = df.merge(vol, on="product_id", how="left")
    else:
        df["company_volume"] = 0

    df["company_volume"] = df["company_volume"].fillna(0)

    # =========================
    # MARKET SIZE
    # =========================
    if market is not None and not market.empty:
        # Ambil latest market size per produk
        market_latest = (
            market.sort_values("date")
            .groupby("product_id", as_index=False)
            .last()[["product_id", "estimated_market_volume"]]
        )

        df = df.merge(market_latest, on="product_id", how="left")
    else:
        df["estimated_market_volume"] = 0

    df["estimated_market_volume"] = df["estimated_market_volume"].fillna(0)

    # =========================
    # SHARE & RISK
    # =========================
    df["market_share_pct"] = df.apply(
        lambda r: r["company_volume"] / r["estimated_market_volume"]
        if r["estimated_market_volume"] > 0 else 0,
        axis=1
    )

    df["share_at_risk_pct"] = df["market_share_pct"].apply(
        lambda x: min(x * 1.5, 1.0)
    )

    # =========================
    # IMPACT LEVEL
    # =========================
    def impact_level(r):
        if r["share_at_risk_pct"] > 0.2:
            return "HIGH"
        if r["share_at_risk_pct"] > 0.1:
            return "MED"
        return "LOW"

    df["impact_level"] = df.apply(impact_level, axis=1)

    return df
