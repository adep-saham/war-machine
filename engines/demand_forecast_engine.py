# ============================================================
# engines/demand_forecast_engine.py
# Demand Forecasting & Inventory Signals for War Room
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd


# -----------------------------
# Data Classes
# -----------------------------

@dataclass
class ForecastConfig:
    date_col: str = "date"
    sku_col: str = "product_id"
    qty_col: str = "qty"

    # optional columns (if exist)
    channel_col: Optional[str] = None
    segment_col: Optional[str] = None

    # horizon defaults
    horizon_30: int = 30
    horizon_60: int = 60
    horizon_90: int = 90

    # smoothing / robustness
    short_window: int = 7
    long_window: int = 28
    outlier_clip_z: float = 3.5

    # confidence heuristics
    min_history_days: int = 35
    max_missing_ratio: float = 0.25

    # seasonality calendar (edit to your business)
    # Format: (month, day_start, day_end, label)
    season_calendar: Tuple[Tuple[int, int, int, str], ...] = (
        (12, 1, 31, "PEAK"),  # year-end
    )


@dataclass
class DemandSignals:
    product_id: str
    scope_key: str

    forecast_30d: float
    forecast_60d: float
    forecast_90d: float

    demand_trend: str           # UP / FLAT / DOWN
    seasonality_flag: str       # PEAK / LOW / NORMAL
    forecast_confidence: float  # 0..1

    avg_daily_demand: float
    volatility: float           # coefficient of variation (CV)
    history_days: int
    missing_ratio: float

    inventory_on_hand: Optional[float] = None
    inventory_cover_days: Optional[float] = None

    notes: str = ""


# -----------------------------
# Utilities
# -----------------------------

def _to_datetime(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _clip_outliers_z(x: pd.Series, z: float = 3.5) -> pd.Series:
    """Robust outlier clipping using median and MAD-based z-score."""
    arr = x.astype(float).values
    med = np.nanmedian(arr)
    mad = np.nanmedian(np.abs(arr - med))
    if mad == 0 or np.isnan(mad):
        return x

    # modified z-score
    mz = 0.6745 * (arr - med) / mad
    clipped = np.clip(arr, np.nanpercentile(arr, 5), np.nanpercentile(arr, 95))
    # only clip extreme mz
    arr2 = np.where(np.abs(mz) > z, clipped, arr)
    return pd.Series(arr2, index=x.index)


def _safe_div(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return float(a) / float(b)


def _seasonality_flag(today: pd.Timestamp, cfg: ForecastConfig) -> str:
    if pd.isna(today):
        return "NORMAL"
    m = int(today.month)
    d = int(today.day)
    for mm, d1, d2, label in cfg.season_calendar:
        if m == mm and d1 <= d <= d2:
            return label
    return "NORMAL"


def _trend_label(short_ma: float, long_ma: float, eps: float = 0.03) -> str:
    """
    Trend based on relative change between short and long moving averages.
    eps = 3% default threshold for UP/DOWN; otherwise FLAT.
    """
    if long_ma <= 0:
        return "FLAT"
    rel = (short_ma - long_ma) / long_ma
    if rel > eps:
        return "UP"
    if rel < -eps:
        return "DOWN"
    return "FLAT"


def _confidence_score(
    history_days: int,
    missing_ratio: float,
    volatility_cv: float,
    cfg: ForecastConfig
) -> float:
    """
    0..1 heuristic:
    - more history => higher
    - less missing => higher
    - lower volatility => higher (but don't punish too hard)
    """
    # history component
    h = min(history_days / max(cfg.min_history_days, 1), 1.0)

    # missing component
    m = 1.0 - min(missing_ratio / max(cfg.max_missing_ratio, 1e-6), 1.0)

    # volatility component (CV)
    # CV 0.0 => 1.0, CV 1.0 => 0.5, CV 2.0 => 0.25
    v = 1.0 / (1.0 + max(volatility_cv, 0.0))

    score = 0.45 * h + 0.35 * m + 0.20 * v
    return float(np.clip(score, 0.0, 1.0))


# -----------------------------
# Core Forecasting
# -----------------------------

def prepare_daily_series(
    df: pd.DataFrame,
    product_id: str,
    cfg: ForecastConfig,
    channel: Optional[str] = None,
    segment: Optional[str] = None
) -> Tuple[pd.DataFrame, str]:
    """
    Returns daily time series for one product (and optional channel/segment).
    Output columns: date, qty
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=[cfg.date_col, cfg.qty_col]), "EMPTY"

    d = df.copy()

    # Filter product
    d = d[d[cfg.sku_col].astype(str) == str(product_id)]

    scope_key_parts = [str(product_id)]
    if cfg.channel_col and channel is not None and cfg.channel_col in d.columns:
        d = d[d[cfg.channel_col].astype(str) == str(channel)]
        scope_key_parts.append(f"ch={channel}")

    if cfg.segment_col and segment is not None and cfg.segment_col in d.columns:
        d = d[d[cfg.segment_col].astype(str) == str(segment)]
        scope_key_parts.append(f"seg={segment}")

    scope_key = "|".join(scope_key_parts)

    if d.empty:
        return pd.DataFrame(columns=[cfg.date_col, cfg.qty_col]), scope_key

    d[cfg.date_col] = _to_datetime(d[cfg.date_col])
    d = d.dropna(subset=[cfg.date_col])

    # aggregate to daily
    g = (
        d.groupby(cfg.date_col, as_index=False)[cfg.qty_col]
        .sum()
        .sort_values(cfg.date_col)
    )

    # fill missing days
    if g.empty:
        return pd.DataFrame(columns=[cfg.date_col, cfg.qty_col]), scope_key

    start, end = g[cfg.date_col].min(), g[cfg.date_col].max()
    all_days = pd.date_range(start=start, end=end, freq="D")
    out = g.set_index(cfg.date_col).reindex(all_days).rename_axis(cfg.date_col).reset_index()

    # missing as 0 demand (common retail interpretation)
    out[cfg.qty_col] = out[cfg.qty_col].fillna(0.0)

    # outlier clip
    out[cfg.qty_col] = _clip_outliers_z(out[cfg.qty_col], z=cfg.outlier_clip_z)

    return out, scope_key


def forecast_from_series(
    s: pd.DataFrame,
    cfg: ForecastConfig
) -> Tuple[float, float, float, Dict[str, float]]:
    """
    Simple robust baseline forecast:
    - Use weighted average of short MA and long MA as expected daily demand
    - Multiply by horizon days
    """
    if s is None or s.empty:
        return 0.0, 0.0, 0.0, {"expected_daily": 0.0, "short_ma": 0.0, "long_ma": 0.0}

    y = s[cfg.qty_col].astype(float)

    # moving averages
    short_ma = float(y.tail(cfg.short_window).mean()) if len(y) >= cfg.short_window else float(y.mean())
    long_ma = float(y.tail(cfg.long_window).mean()) if len(y) >= cfg.long_window else float(y.mean())

    # Weighted expected daily demand
    expected_daily = 0.6 * short_ma + 0.4 * long_ma

    f30 = float(max(expected_daily, 0.0) * cfg.horizon_30)
    f60 = float(max(expected_daily, 0.0) * cfg.horizon_60)
    f90 = float(max(expected_daily, 0.0) * cfg.horizon_90)

    return f30, f60, f90, {"expected_daily": expected_daily, "short_ma": short_ma, "long_ma": long_ma}


def compute_signals(
    df_sales: pd.DataFrame,
    product_id: str,
    cfg: ForecastConfig,
    inventory_on_hand: Optional[float] = None,
    channel: Optional[str] = None,
    segment: Optional[str] = None
) -> DemandSignals:
    """
    Main public function:
    returns DemandSignals for one product (and optional channel/segment).
    """
    series, scope_key = prepare_daily_series(df_sales, product_id, cfg, channel=channel, segment=segment)

    if series.empty:
        return DemandSignals(
            product_id=str(product_id),
            scope_key=scope_key,
            forecast_30d=0.0,
            forecast_60d=0.0,
            forecast_90d=0.0,
            demand_trend="FLAT",
            seasonality_flag="NORMAL",
            forecast_confidence=0.0,
            avg_daily_demand=0.0,
            volatility=0.0,
            history_days=0,
            missing_ratio=1.0,
            inventory_on_hand=inventory_on_hand,
            inventory_cover_days=None,
            notes="No history"
        )

    # stats
    y = series[cfg.qty_col].astype(float)

    history_days = int(len(y))
    missing_days = int((y == 0).sum())  # if 0 treated as missing demand
    missing_ratio = float(missing_days / max(history_days, 1))

    avg_daily = float(y.mean())
    std_daily = float(y.std(ddof=0))
    volatility_cv = float(_safe_div(std_daily, avg_daily)) if avg_daily > 0 else 0.0

    # forecast
    f30, f60, f90, comps = forecast_from_series(series, cfg)
    expected_daily = float(comps["expected_daily"])
    short_ma = float(comps["short_ma"])
    long_ma = float(comps["long_ma"])

    trend = _trend_label(short_ma, long_ma, eps=0.03)

    # seasonality: based on last date in series (proxy for "today")
    today = series[cfg.date_col].max()
    sflag = _seasonality_flag(today, cfg)

    conf = _confidence_score(history_days, missing_ratio, volatility_cv, cfg)

    # inventory cover
    cover_days = None
    if inventory_on_hand is not None:
        inv = float(inventory_on_hand)
        cover_days = float(inv / expected_daily) if expected_daily > 0 else None

    notes = []
    if history_days < cfg.min_history_days:
        notes.append("short_history")
    if missing_ratio > cfg.max_missing_ratio:
        notes.append("high_missing_ratio")
    if volatility_cv > 1.0:
        notes.append("high_volatility")

    return DemandSignals(
        product_id=str(product_id),
        scope_key=scope_key,
        forecast_30d=round(f30, 2),
        forecast_60d=round(f60, 2),
        forecast_90d=round(f90, 2),
        demand_trend=trend,
        seasonality_flag=sflag,
        forecast_confidence=round(conf, 3),
        avg_daily_demand=round(expected_daily, 4),
        volatility=round(volatility_cv, 3),
        history_days=history_days,
        missing_ratio=round(missing_ratio, 3),
        inventory_on_hand=inventory_on_hand,
        inventory_cover_days=round(cover_days, 2) if cover_days is not None else None,
        notes=",".join(notes) if notes else ""
    )


# -----------------------------
# Batch Runner (War Room Integration)
# -----------------------------

def attach_demand_signals(
    war_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    cfg: Optional[ForecastConfig] = None,
    inventory_col: Optional[str] = None,
    channel: Optional[str] = None,
    segment: Optional[str] = None
) -> pd.DataFrame:
    """
    Attach signals to war_df per product_id.
    - war_df must have cfg.sku_col (default product_id)
    - sales_df must have date_col, sku_col, qty_col

    inventory_col: column in war_df for on_hand inventory (optional)
    """
    cfg = cfg or ForecastConfig()

    if war_df is None or war_df.empty:
        return war_df

    out = war_df.copy()
    pids = out[cfg.sku_col].astype(str).unique().tolist()

    rows: List[Dict[str, object]] = []
    for pid in pids:
        inv = None
        if inventory_col and inventory_col in out.columns:
            # take first non-null inventory for this pid
            sub = out[out[cfg.sku_col].astype(str) == str(pid)]
            val = sub[inventory_col].dropna()
            inv = float(val.iloc[0]) if not val.empty else None

        sig = compute_signals(
            df_sales=sales_df,
            product_id=pid,
            cfg=cfg,
            inventory_on_hand=inv,
            channel=channel,
            segment=segment
        )

        rows.append({
            cfg.sku_col: str(pid),
            "forecast_30d": sig.forecast_30d,
            "forecast_60d": sig.forecast_60d,
            "forecast_90d": sig.forecast_90d,
            "demand_trend": sig.demand_trend,
            "seasonality_flag": sig.seasonality_flag,
            "forecast_confidence": sig.forecast_confidence,
            "avg_daily_demand": sig.avg_daily_demand,
            "demand_volatility": sig.volatility,
            "history_days": sig.history_days,
            "missing_ratio": sig.missing_ratio,
            "inventory_cover_days": sig.inventory_cover_days,
            "demand_notes": sig.notes,
        })

    sig_df = pd.DataFrame(rows)
    out = out.merge(sig_df, on=cfg.sku_col, how="left")
    return out
