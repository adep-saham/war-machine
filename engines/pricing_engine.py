import pandas as pd


def build_pricing_snapshot(price_company, master, price_competitor):
    """
    Build pricing snapshot:
    - Merge master + price_company + competitor
    - Compute floor_price, gap_price
    - Defensive against missing columns (cost_unit, competitor price)
    """

    # =====================================================
    # 1. BASIC MERGE (MASTER + COMPANY PRICE)
    # =====================================================
    snap = master.merge(
        price_company,
        on="product_id",
        how="left",
        suffixes=("", "_company"),
    )

    # =====================================================
    # 2. COMPETITOR MIN PRICE
    # =====================================================
    if price_competitor is not None and len(price_competitor) > 0:
        comp_min = (
            price_competitor
            .groupby("product_id", as_index=False)["price_sell"]
            .min()
            .rename(columns={"price_sell": "min_comp_price"})
        )
        snap = snap.merge(comp_min, on="product_id", how="left")
    else:
        snap["min_comp_price"] = None

    # =====================================================
    # 3. FLOOR PRICE (DEFENSIVE)
    # =====================================================
    if "cost_unit" in snap.columns:
        snap["floor_price"] = snap["cost_unit"] * 1.02
        snap["floor_reason"] = "cost_plus_2pct"
    else:
        # Fallback: protect margin minimally
        snap["floor_price"] = snap["price_sell"] * 0.98
        snap["floor_reason"] = "fallback_98pct_price"

    # =====================================================
    # 4. GAP PRICE VS COMPETITOR
    # =====================================================
    if "min_comp_price" in snap.columns:
        snap["gap_price"] = snap["price_sell"] - snap["min_comp_price"]
    else:
        snap["gap_price"] = None

    # =====================================================
    # 5. GUARDRAIL STATUS
    # =====================================================
    snap["guardrail_status"] = "ALLOWED"
    snap.loc[snap["price_sell"] < snap["floor_price"], "guardrail_status"] = "BLOCKED"

    # =====================================================
    # 6. CLEANUP & DEFAULTS
    # =====================================================
    defaults = {
        "min_comp_price": None,
        "gap_price": None,
        "cost_unit": None,
    }
    for col, val in defaults.items():
        if col not in snap.columns:
            snap[col] = val

    return snap
