# ============================================
# PROMO SIMULATOR ENGINE
# Strategic Pricing – Anti Price War
# ============================================

from dataclasses import dataclass
from typing import Dict, List


# -----------------------------
# DATA STRUCTURES
# -----------------------------

@dataclass
class PromoInput:
    base_price: float
    base_cost: float
    volume: int

    discount_pct: float = 0.0     # %
    cashback_pct: float = 0.0     # %
    extra_fee_pct: float = 0.0    # % (admin / service)
    bundle_value_pct: float = 0.0 # % perceived value (non-cash)


@dataclass
class PromoResult:
    promo_type: str
    effective_price: float
    perceived_price: float
    margin_pct: float
    margin_delta_pct: float
    revenue: float
    war_risk: str
    recommendation_score: float
    rationale: str


# -----------------------------
# CORE CALCULATIONS
# -----------------------------

def calculate_effective_price(p: PromoInput) -> float:
    price_after_discount = p.base_price * (1 - p.discount_pct / 100)
    cashback_value = p.base_price * (p.cashback_pct / 100)
    fee_value = price_after_discount * (p.extra_fee_pct / 100)

    effective_price = price_after_discount - cashback_value + fee_value
    return round(effective_price, 2)


def calculate_perceived_price(p: PromoInput) -> float:
    # Persepsi harga = effective price + nilai non-cash
    effective_price = calculate_effective_price(p)
    perceived_discount = p.base_price * (p.bundle_value_pct / 100)
    perceived_price = effective_price - perceived_discount
    return round(perceived_price, 2)


def calculate_margin(p: PromoInput, effective_price: float) -> float:
    margin = (effective_price - p.base_cost) / effective_price * 100
    return round(margin, 2)


# -----------------------------
# WAR RISK CLASSIFIER
# -----------------------------

def classify_war_risk(discount_pct: float, cashback_pct: float) -> str:
    total_cut = discount_pct + cashback_pct

    if total_cut >= 5:
        return "HIGH"
    elif total_cut >= 2:
        return "MEDIUM"
    return "LOW"


# -----------------------------
# RECOMMENDATION SCORING
# -----------------------------

def recommendation_score(
    margin_pct: float,
    war_risk: str,
    perceived_advantage: float
) -> float:
    risk_penalty = {"LOW": 0, "MEDIUM": 0.2, "HIGH": 0.5}
    score = (
        margin_pct * 0.5
        + perceived_advantage * 0.3
        - risk_penalty[war_risk] * 10
    )
    return round(score, 2)


# -----------------------------
# MAIN SIMULATOR
# -----------------------------

def run_promo_simulation(
    promo_name: str,
    promo_input: PromoInput
) -> PromoResult:

    effective_price = calculate_effective_price(promo_input)
    perceived_price = calculate_perceived_price(promo_input)

    base_margin = (promo_input.base_price - promo_input.base_cost) / promo_input.base_price * 100
    new_margin = calculate_margin(promo_input, effective_price)
    margin_delta = round(new_margin - base_margin, 2)

    revenue = round(effective_price * promo_input.volume, 2)
    war_risk = classify_war_risk(
        promo_input.discount_pct,
        promo_input.cashback_pct
    )

    perceived_adv = promo_input.bundle_value_pct
    score = recommendation_score(new_margin, war_risk, perceived_adv)

    rationale = (
        f"Effective price {effective_price}, "
        f"margin {new_margin}%, "
        f"war risk {war_risk}. "
        f"Perceived value boost {promo_input.bundle_value_pct}%."
    )

    return PromoResult(
        promo_type=promo_name,
        effective_price=effective_price,
        perceived_price=perceived_price,
        margin_pct=new_margin,
        margin_delta_pct=margin_delta,
        revenue=revenue,
        war_risk=war_risk,
        recommendation_score=score,
        rationale=rationale
    )


# -----------------------------
# PROMO PORTFOLIO RUNNER
# -----------------------------

def simulate_promo_portfolio(
    base_price: float,
    base_cost: float,
    volume: int
) -> List[PromoResult]:

    scenarios = {
        "DISCOUNT_1%": PromoInput(
            base_price, base_cost, volume,
            discount_pct=1
        ),
        "CASHBACK_1%": PromoInput(
            base_price, base_cost, volume,
            cashback_pct=1
        ),
        "BUNDLE_3%": PromoInput(
            base_price, base_cost, volume,
            bundle_value_pct=3
        ),
        "ANTI_BAIT_FEE": PromoInput(
            base_price, base_cost, volume,
            extra_fee_pct=1
        ),
        "MIXED_SMART": PromoInput(
            base_price, base_cost, volume,
            discount_pct=0.5,
            cashback_pct=0.5,
            bundle_value_pct=2
        )
    }

    results = []
    for name, promo in scenarios.items():
        results.append(run_promo_simulation(name, promo))

    # Sort by recommendation score (highest first)
    return sorted(results, key=lambda x: x.recommendation_score, reverse=True)


# -----------------------------
# QUICK TEST (OPTIONAL)
# -----------------------------
if __name__ == "__main__":
    output = simulate_promo_portfolio(
        base_price=100_000,
        base_cost=85_000,
        volume=1_000
    )

    for o in output:
        print(o)
