def apply_market_share(war, sales, market):
    war["market_share_pct"] = None
    war["share_at_risk_pct"] = None
    war["impact_level"] = "NO DATA"

    if sales is None or market is None:
        return war

    last_date = sales["date"].max()

    sales_latest = (
        sales[sales["date"] == last_date]
        .groupby("product_id")["volume_gram"]
        .sum()
    )

    market_latest = (
        market[market["date"] == last_date]
        .groupby("product_id")["estimated_market_volume"]
        .sum()
    )

    for i, r in war.iterrows():
        pid = r["product_id"]
        if pid in sales_latest and pid in market_latest:
            share = sales_latest[pid] / market_latest[pid] * 100
            war.at[i, "market_share_pct"] = round(share, 2)

            if r["status"] == "ATTACK" and r["guardrail_status"] == "BLOCKED":
                risk = share * 0.5
            elif r["status"] == "ATTACK":
                risk = share * 0.2
            else:
                risk = share * 0.05

            war.at[i, "share_at_risk_pct"] = round(risk, 2)

            war.at[i, "impact_level"] = (
                "HIGH" if risk > 5 else "MED" if risk > 2 else "LOW"
            )

    return war
