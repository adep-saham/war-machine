# ============================================================
# engines/product_performance_engine.py
# Product Performance & Strategic Role Classification (ROBUST)
# - Auto-detect volume column if missing
# - Always outputs: sales_volume, revenue, margin_pct, product_role, strategic_score
# ============================================================

from __future__ import annotations
from typing import List
import numpy as np
import pandas as pd


def _safe_float(x):
    try:
        if x is None:
            return 0.0
        if isinstance(x, str) and x.strip() == "":
            return 0.0
        return float(x)
    except Exception:
        return 0.0


def _pct(a: float, b: float) -> float:
    return 0.0 if b == 0 else float(a) / float(b)


def _detect_first_existing_col(df: pd.DataFrame, candidates: List[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def compute_product_performance(
    war_df: pd.DataFrame,
    price_col: str = "price_sell",
    cost_col: str = "cost_unit",
    volume_col: str = "sales_volume",
    min_comp_col: str = "min_comp_price",
) -> pd.DataFrame:
    """
    Menghitung kinerja & peran strategis produk berbasis:
    - revenue
    - volume
    - margin
    - price gap vs kompetitor

    ROBUST:
    - Jika volume_col tidak ada, auto-detect dari kandidat: qty, volume_gram, volume, units, dll.
    - Jika tetap tidak ada, set sales_volume = 0 (dan beri catatan)
    """

    if war_df is None or war_df.empty:
        return war_df

    df = war_df.copy()

    # -----------------------------
    # Ensure base numeric columns exist
    # -----------------------------
    if price_col not in df.columns:
        raise ValueError(f"Missing required column for price: {price_col}")
    if cost_col not in df.columns:
        # cost_unit wajib untuk margin; fail fast biar jelas
        raise ValueError(f"Missing required column for cost: {cost_col}")

    # min competitor price optional (can be all NaN)
    if min_comp_col not in df.columns:
        df[min_comp_col] = np.nan

    # -----------------------------
    # Volume column robustness
    # -----------------------------
    notes = []
    vol_source = None

    if volume_col in df.columns:
        vol_source = volume_col
    else:
        # auto-detect common alternatives
        candidates = [
            "sales_volume",
            "qty",
            "volume",
            "units",
            "unit_sold",
            "sales_qty",
            "volume_gram",   # kalau yang tersedia gram, tetap kita pakai sebagai proxy volume
        ]
        vol_source = _detect_first_existing_col(df, candidates)

        if vol_source is None:
            # fallback: create volume column as 0
            df["sales_volume"] = 0.0
            vol_source = "sales_volume"
            notes.append("missing_volume_col_fallback_zero")
        else:
            notes.append(f"volume_col_autodetected:{vol_source}")

    # unify to sales_volume column
    df["sales_volume"] = df[vol_source].apply(_safe_float)

    # -----------------------------
    # Numeric conversions
    # -----------------------------
    df["price_sell"] = df[price_col].apply(_safe_float)
    df["cost_unit"] = df[cost_col].apply(_safe_float)
    df["min_comp_price"] = df[min_comp_col].apply(_safe_float)

    # -----------------------------
    # Metrics
    # -----------------------------
    df["revenue"] = df["price_sell"] * df["sales_volume"]
    df["margin_pct"] = df.apply(
        lambda r: _pct((r["price_sell"] - r["cost_unit"]), r["price_sell"]),
        axis=1
    )

    total_rev = float(df["revenue"].sum())
    total_vol = float(df["sales_volume"].sum())

    df["revenue_share"] = df["revenue"].apply(lambda x: _pct(x, total_rev))
    df["volume_share"] = df["sales_volume"].apply(lambda x: _pct(x, total_vol))

    # price gap pct (if competitor exists)
    df["price_gap_pct"] = df.apply(
        lambda r: _pct((r["price_sell"] - r["min_comp_price"]), r["min_comp_price"])
        if r["min_comp_price"] > 0 else 0.0,
        axis=1
    )

    # sensitivity heuristic
    gap_q_low = float(df["price_gap_pct"].quantile(0.25))
    gap_q_high = float(df["price_gap_pct"].quantile(0.75))

    def _sens(x):
        if x >= gap_q_high:
            return "LOW"
        if x <= gap_q_low:
            return "HIGH"
        return "MED"

    df["price_sensitivity"] = df["price_gap_pct"].apply(_sens)

    # -----------------------------
    # Strategic score (0–100)
    # -----------------------------
    raw_score = (
        40 * df["revenue_share"] +
        30 * df["margin_pct"] +
        20 * df["volume_share"] -
        10 * df["price_gap_pct"].abs()
    )

    min_s, max_s = float(raw_score.min()), float(raw_score.max())
    if max_s > min_s:
        df["strategic_score"] = 100 * (raw_score - min_s) / (max_s - min_s)
    else:
        df["strategic_score"] = 50.0

    # -----------------------------
    # Product Role Classification
    # DEFENDER / ATTACKER / SACRIFICIAL / TRAFFIC
    # -----------------------------
    rev_q = df["revenue_share"].quantile([0.33, 0.66]).values
    mar_q = df["margin_pct"].quantile([0.33, 0.66]).values
    vol_q = df["volume_share"].quantile([0.33, 0.66]).values

    roles = []
    role_notes = []

    for _, r in df.iterrows():
        high_rev = r["revenue_share"] >= rev_q[1]
        high_margin = r["margin_pct"] >= mar_q[1]
        high_vol = r["volume_share"] >= vol_q[1]
        neg_gap = r["price_gap_pct"] < 0  # cheaper than competitor

        if high_margin and high_rev:
            role = "DEFENDER"
            rn = "protect_margin"
        elif high_vol and neg_gap:
            role = "ATTACKER"
            rn = "can_gain_share"
        elif (not high_margin) and neg_gap:
            role = "SACRIFICIAL"
            rn = "price_sensitive"
        else:
            role = "TRAFFIC"
            rn = "traffic_driver"

        roles.append(role)
        role_notes.append(rn)

    df["product_role"] = roles
    df["product_notes"] = role_notes

    # attach global notes (same for all rows, helpful for debugging)
    if notes:
        df["perf_engine_notes"] = ";".join(notes)
    else:
        df["perf_engine_notes"] = ""

    return df
