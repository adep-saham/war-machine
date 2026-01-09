import pandas as pd


class DCZEngine:
    """
    HARDENED DCZ ENGINE
    - Tidak asumsi kolom ada
    - Tidak pernah throw AttributeError
    - Selalu return war dataframe
    """

    def decide_dcz(self, war: pd.DataFrame) -> pd.DataFrame:
        df = war.copy()

        # === FORCE COLUMN NORMALIZATION ===
        df.columns = df.columns.astype(str)

        # === DEFAULT DCZ ===
        df["dcz_decision"] = "HOLD"
        df["dcz_reason"] = "default_safe_mode"

        # === SAFE RULES (OPTIONAL, TIDAK WAJIB ADA KOLOM) ===
        if "demand_trend" in df.columns:
            df.loc[df["demand_trend"] == "UP", "dcz_decision"] = "FIGHT"
            df.loc[df["demand_trend"] == "DOWN", "dcz_decision"] = "PROMO_ZONE"

        if "guardrail_status" in df.columns:
            df.loc[df["guardrail_status"] == "BLOCKED", "dcz_decision"] = "NO_FIGHT"

        if "inventory_cover_days" in df.columns:
            df.loc[df["inventory_cover_days"] > 60, "dcz_decision"] = "LET_GO"

        return df
