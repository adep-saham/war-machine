# ============================================================
# engines/pricing_engine.py
# Pricing Snapshot Engine (FINAL – cost_unit FIXED)
# ============================================================

import pandas as pd


def build_pricing_snapshot(
    price_company: pd.DataFrame,
    master_product: pd.DataFrame,
    price_competitor: pd.DataFrame
) -> pd.DataFrame:
    """
    Build pricing snapshot that becomes the BASE of War Room.
    WAJIB membawa atribut produk inti:
    - product_name
    - pecahan_gram
    - cost_unit   <-- FIX UTAMA
    """

    # -----------------------------
    # VALIDATION (FAIL FAST)
    # -----------------------------
    required_master_cols = {
        "product_id",
        "product_name",
        "pecahan_gram",
        "cost_unit",
    }
    missing_master = required_master_cols - set(master_product.columns)
    if missing_master:
        raise ValueError(f"Master Product missing columns: {missing_master}")

    required_price_cols = {"product_id", "price_sell"}
    missing_price = required_price_cols - set(price_company.columns)
    if missing_price:
        raise ValueError(f"Price Company missing columns: {missing_price}")

    # -----------------------------
    # BASE SNAPSHOT (COMPANY PRICE + MASTER)
    # -----------------------------
    snap = price_company.merge(
        master_product[
            [
                "product_id",
                "product_name",
                "pecahan_gram",
                "cost_unit",   # ✅ FIX: cost_unit ikut dari awal
            ]
        ],
        on="product_id",
        how="left"
    )

    # -----------------------------
    # COMPETITOR PRICE (MIN)
    # -----------------------------
    if price_competitor is not None and not price_competitor.empty:
        if not {"product_id", "price_competitor"}.issubset(price_competitor.columns):
            raise ValueError("price_competitor must have columns: product_id, price_competitor")

        comp_min = (
            price_competitor
            .groupby("product_id", as_index=False)["price_competitor"]
            .min()
            .rename(columns={"price_competitor": "min_comp_price"})
        )

        snap = snap.merge(comp_min, on="product_id", how="left")
    else:
        snap["min_comp_price"] = None

    # -----------------------------
    # PRICE GAP & FLOOR
    # -----------------------------
    snap["gap_price"] = snap["price_sell"] - snap["min_comp_price"]

    # Floor price = cost + safety margin (example 2%)
    snap["floor_price"] = snap["cost_unit"] * 1.02

    # -----------------------------
    # SANITY CHECK (ANTI SILENT BUG)
    # -----------------------------
    critical_cols = [
        "product_id",
        "price_sell",
        "cost_unit",
        "min_comp_price",
        "floor_price",
    ]
    for c in critical_cols:
        if c not in snap.columns:
            raise RuntimeError(f"CRITICAL COLUMN MISSING AFTER SNAPSHOT: {c}")

    return snap
