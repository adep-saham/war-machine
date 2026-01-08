import pandas as pd

def apply_guardrail(war):
    war["floor_price"] = war["price_sell"] * 0.98  # placeholder kebijakan

    def guard(row):
        if pd.isna(row["min_comp_price"]):
            return "ALLOWED"
        if row["min_comp_price"] < row["floor_price"]:
            return "BLOCKED"
        return "ALLOWED"

    war["guardrail_status"] = war.apply(guard, axis=1)
    return war
