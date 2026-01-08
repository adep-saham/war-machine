def effective_price(row):
    return (
        row["price_sell"]
        - row["promo_cashback"]
        - row["promo_discount"]
        + row["shipping_fee"]
        + row["admin_fee"]
    )

def apply_guardrail(market_price, floor_price):
    if market_price is None:
        return None, "NO DATA"
    if market_price < floor_price:
        return floor_price, "BLOCKED"
    return market_price, "ALLOWED"
