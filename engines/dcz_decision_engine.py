# ============================================================
# engines/dcz_decision_engine.py
# DCZ Decision Engine (Demand + Product Role Driven)
# ============================================================

from typing import Tuple


def decide_dcz(row) -> Tuple[str, str]:
    """
    Return:
    - dcz_decision: NO_FIGHT / FIGHT / LET_GO / PROMO_ZONE / HOLD
    - dcz_reason: human-readable rationale
    """

    # -----------------------------
    # Extract signals (safe)
    # -----------------------------
    inv_days = row.get("inventory_cover_days")
    demand_trend = row.get("demand_trend")
    conf = row.get("forecast_confidence")
    role = row.get("product_role")

    # -----------------------------
    # LEVEL 1 — INVENTORY GATE
    # -----------------------------
    if inv_days is not None and inv_days < 15:
        return "NO_FIGHT", "inventory_too_low"

    # -----------------------------
    # LEVEL 2 — FORECAST CONFIDENCE
    # -----------------------------
    if conf is not None and conf < 0.6:
        return "HOLD", "low_forecast_confidence"

    # -----------------------------
    # LEVEL 3 — PRODUCT ROLE
    # -----------------------------
    if role == "DEFENDER":
        return "NO_FIGHT", "defender_product_protect_margin"

    if role == "SACRIFICIAL":
        return "LET_GO", "sacrificial_product_price_sensitive"

    # -----------------------------
    # LEVEL 4 — DEMAND TREND ADJUSTMENT
    # -----------------------------
    if demand_trend == "DOWN" and inv_days is not None and inv_days > 60:
        return "PROMO_ZONE", "oversupply_clearance"

    if role == "ATTACKER" and demand_trend in ("UP", "FLAT"):
        return "FIGHT", "attacker_with_demand_support"

    if role == "TRAFFIC":
        if demand_trend == "UP":
            return "HOLD", "traffic_product_high_demand"
        return "PROMO_ZONE", "traffic_product_controlled_promo"

    # -----------------------------
    # FALLBACK
    # -----------------------------
    return "HOLD", "default_hold_uncertainty"
