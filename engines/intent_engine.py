import pandas as pd


def detect_loss_intent(war: pd.DataFrame, extreme_gap=500_000):
    """
    Detect competitor pricing intent based on pattern, not absolute price.
    Returns war with new column: competitor_intent
    """

    out = war.copy()

    # berapa SKU yang ATTACK (indikasi skala serangan)
    attack_skus = out[out["status"] == "ATTACK"]["product_id"].nunique()

    intents = []

    for _, r in out.iterrows():
        gap = r.get("gap_price")
        impact = r.get("impact_level")
        status = r.get("status")

        # default
        intent = "NOISE"

        if status != "ATTACK" or gap is None or pd.isna(gap):
            intent = "NOISE"

        elif gap >= extreme_gap and attack_skus == 1:
            # harga super jauh, tapi hanya 1 SKU → pancingan
            intent = "BAIT / SIGNAL"

        elif gap < extreme_gap and attack_skus >= 2:
            # gap masih masuk akal dan banyak SKU → niat ambil market
            intent = "MARKET_GRAB"

        elif gap < extreme_gap and impact in ["LOW", "MED"]:
            intent = "DEFENSIVE_PRICE"

        intents.append(intent)

    out["competitor_intent"] = intents
    return out
