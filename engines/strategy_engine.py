def classify_strategy(row):
    if row["impact_level"] == "HIGH":
        return "DEFEND"
    if row["impact_level"] == "LOW" and row["market_share_pct"] < 5:
        return "SACRIFICE"
    return "OPPORTUNITY"
