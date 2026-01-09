import pandas as pd

class DCZEngine:
    def decide_dcz(self, war: pd.DataFrame) -> pd.DataFrame:
        df = war.copy()

        df["dcz_decision"] = "HOLD"
        df["dcz_reason"] = "default_safe_mode"

        if "demand_trend" in df.columns:
            df.loc[df["demand_trend"] == "UP", "dcz_decision"] = "FIGHT"
            df.loc[df["demand_trend"] == "DOWN", "dcz_decision"] = "PROMO_ZONE"

        if "guardrail_status" in df.columns:
            df.loc[df["guardrail_status"] == "BLOCKED", "dcz_decision"] = "NO_FIGHT"

        if "inventory_cover_days" in df.columns:
            df.loc[df["inventory_cover_days"] > 60, "dcz_decision"] = "LET_GO"

        return df
