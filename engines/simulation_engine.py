def simulate_price(war, drop_pct=0.01):
    war[f"sim_price_{int(drop_pct*100)}"] = war["price_sell"] * (1 - drop_pct)
    war[f"sim_allowed_{int(drop_pct*100)}"] = (
        war[f"sim_price_{int(drop_pct*100)}"] >= war["floor_price"]
    )
    return war
