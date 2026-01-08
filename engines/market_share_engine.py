def compute_market_share_impact(war, sales, market):

    if sales.empty or market.empty:
        war["market_share_pct"] = None
        war["share_at_risk_pct"] = None
        war["impact_level"] = "NO DATA"
        return war

    latest = sales["date"].max()

    s = sales[sales["date"] == latest].groupby("product_id")["volume_gram"].sum()
    m = market[market["date"] == latest].groupby("product_id")["estimated_market_volume"].sum()

    war["market_share_pct"] = war["product_id"].map(s / m * 100)

    def risk(row):
        if row["status"] == "ATTACK" and row["policy_status"] == "BLOCKED":
            return row["market_share_pct"] * 0.5
        return row["market_share_pct"] * 0.1

    war["share_at_risk_pct"] = war.apply(risk, axis=1)
    war["impact_level"] = war["share_at_risk_pct"].apply(
        lambda x: "HIGH" if x > 5 else "MED" if x > 2 else "LOW"
    )

    return war
