# ============================================================
# engines/pricing_engine.py
# Pricing Snapshot Engine (FINAL v2 – AUTO COMP PRICE)
# ============================================================

import pandas as pd


def _detect_comp_price_col(df: pd.DataFrame) -> str:
    """
    Auto-detect competitor price column.
    Priority order from most common to generic.
    """
    candidates = [
        "price_competitor",
        "comp_price",
        "price",
        "price_sell",
        "harga",
        "harga_jual",
        "price_comp",
    ]
    for c in candidates:
        if c in df.columns:
            return c
    raise ValueError(
        f"price_competitor CSV must have ONE of these columns: {candidates}"
    )


def build_pricing_snapshot(
    price_company: pd.DataFrame,
    master_product: pd.DataFrame,
    price_competitor: pd.DataFrame
) -> pd.DataFrame:
    """
    Build pricing snapshot that becomes the BASE of War Room.
    FINAL CONTRACT:
    - cost_unit WAJIB ada
    - competitor price AUTO-detect
    """

    # -----------------------------
    # VALIDATION — MASTER
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

    # -----------------------------
    # VALIDATION — COMPANY PRICE
    # -----------------------------
    if not {"product_id", "price_sell"}.issubset(price_company.columns):
        raise ValueError("price_company must have columns: product_id, price_sell")

    # -----------------------------
    # BASE SNAPSHOT
    # -----------------------------
    snap = price_company.merge(
        master_product[
            ["product_id", "product_name", "pecahan_gram", "cost_unit"]
        ],
        on="product_id",
        how="left"
    )

    # -----------------------------
    # COMPETITOR PRICE (AUTO)
    # -----------------------------
    if price_competitor is not None and not price_competitor.empty:
        if "product_id" not in price_competitor.columns:
            raise ValueError("price_competitor must have column: product_id")

        comp_price_col = _detect_comp_price_col(price_competitor)

        comp_min = (
            price_competitor
            .groupby("product_id", as_index=False)[comp_price_col]
            .min()
            .rename(columns={comp_price_col: "min_comp_price"})
        )

        snap = snap.merge(comp_min, on="product_id", how="left")
    else:
        snap["min_comp_price"] = None

    # -----------------------------
    # PRICE GAP & FLOOR
    # -----------------------------
    snap["gap_price"] = snap["price_sell"] - snap["min_comp_price"]
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
            raise RuntimeError(f"CRITICAL COLUMN MISSING: {c}")

    return snap
