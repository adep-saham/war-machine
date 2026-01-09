# ============================================================
# engines/product_performance_engine.py
# Product Performance & Strategic Role Classification
# ============================================================

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# -----------------------------
# Data Classes
# -----------------------------

@dataclass
class ProductPerformanceSignals:
    product_id: str

    revenue: float
    volume: float
    margin_pct: float

    revenue_share: float
    volume_share: float

    price_gap_pct: float
    price_sensitivity: str  # LOW / MED / HIGH

    product_role: str       # DEFENDER / ATTACKER / SACRIFICIAL / TRAFFIC
    strategic_score: float  # 0–100

    notes: str = ""


# -----------------------------
# Utilities
# -----------------------------

def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return 0.0


def _pct(a: float, b: float) -> float:
    return 0.0 if b == 0 else a / b


def _quantile_label(x: float, q_low: float, q_high: float) -> str:
    if x >= q_high:
        return "HIGH"
    if x <= q_low:
        return "LOW"
    return "MED"


# -----------------------------
# Core Logic
# -----------------------------

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
    """

    df = war_df.copy()

    # -----------------------------
    # Basic Metrics
    # -----------------------------
    df["price_sell"] = df[price_col].apply(_safe_float)
    df["cost_unit"] = df[cost_col].apply(_safe_float)
    df["sales_volume"] = df[volume_col].apply(_safe_float)
    df["min_comp_price"] = df[min_comp_col].apply(_safe_float)

    df["revenue"] = df["price_sell"] * df["sales_volume"]
    df["margin_pct"] = _pct(
        (df["price_sell"] - df["cost_unit"]),
        df["price_sell"]
    )

    # -----------------------------
    # Share Metrics
    # -----------------------------
    total_rev = df["revenue"].sum()
    total_vol = df["sales_volume"].sum()

    df["revenue_share"] = df["revenue"].apply(lambda x: _pct(x, total_rev))
    df["volume_share"] = df["sales_volume"].apply(lambda x: _pct(x, total_vol))

    # -----------------------------
    # Price Gap & Sensitivity
    # -----------------------------
    df["price_gap_pct"] = df.apply(
        lambda r: _pct(
            r["price_sell"] - r["min_comp_price"],
            r["min_comp_price"]
        ),
        axis=1
    )

    # sensitivity heuristic:
    # makin negatif gap → makin sensitif
    gap_q_low = df["price_gap_pct"].quantile(0.25)
    gap_q_high = df["price_gap_pct"].quantile(0.75)

    df["price_sensitivity"] = df["price_gap_pct"].apply(
        lambda x: _quantile_label(x, gap_q_low, gap_q_high)
    )

    # -----------------------------
    # Strategic Score (0–100)
    # -----------------------------
    # Weighting: revenue > margin > volume > gap
    df["strategic_score"] = (
        40 * df["revenue_share"] +
        30 * df["margin_pct"] +
        20 * df["volume_share"] -
        10 * abs(df["price_gap_pct"])
    )

    # normalize
    min_s, max_s = df["strategic_score"].min(), df["strategic_score"].max()
    if max_s > min_s:
        df["strategic_score"] = 100 * (df["strategic_score"] - min_s) / (max_s - min_s)
    else:
        df["strategic_score"] = 50.0

    # -----------------------------
    # Product Role Classification
    # -----------------------------
    rev_q = df["revenue_share"].quantile([0.33, 0.66]).values
    mar_q = df["margin_pct"].quantile([0.33, 0.66]).values
    vol_q = df["volume_share"].quantile([0.33, 0.66]).values

    roles: List[str] = []
    notes: List[str] = []

    for _, r in df.iterrows():
        role = "TRAFFIC"
        note = []

        high_rev = r["revenue_share"] >= rev_q[1]
        high_margin = r["margin_pct"] >= mar_q[1]
        high_vol = r["volume_share"] >= vol_q[1]
        neg_gap = r["price_gap_pct"] < 0

        # DEFENDER: margin & revenue tinggi
        if high_margin and high_rev:
            role = "DEFENDER"
            note.append("protect_margin")

        # ATTACKER: volume tinggi, gap negati
