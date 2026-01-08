import pandas as pd

def build_pricing_snapshot(price_company, master, price_comp):
    war = price_company.merge(
        master[["product_id", "product_name", "pecahan_gram"]],
        on="product_id",
        how="left"
    )

    comp_min = (
        price_comp
        .groupby("product_id", as_index=False)["price_sell"]
        .min()
        .rename(columns={"price_sell": "min_comp_price"})
    )

    war = war.merge(comp_min, on="product_id", how="left")
    war["gap_price"] = war["price_sell"] - war["min_comp_price"]

    war["status"] = war["gap_price"].apply(
        lambda x: "ATTACK" if pd.notna(x) and x > 0 else "DEFENSIVE"
    )

    return war
