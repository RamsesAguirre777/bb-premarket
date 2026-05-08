from __future__ import annotations
import os
import time
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

from dc.constants import TICKERS, TICKERS_MACRO, TIMEZONE, UTC, N_VELAS_BB
from dc.utils import (
    _bars_list_to_mi_dataframe,
    _filter_bars_before,
    _compute_bb_from_closes,
)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
_alpaca_historical_singleton: StockHistoricalDataClient | None = None

os.makedirs("outputs", exist_ok=True)
os.makedirs("logs", exist_ok=True)

logger = logging.getLogger(__name__)


def _alpaca_historical() -> StockHistoricalDataClient:
    global _alpaca_historical_singleton
    if _alpaca_historical_singleton is None:
        if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
            raise ValueError("ALPACA_API_KEY o ALPACA_SECRET_KEY no encontradas en .env")
        _alpaca_historical_singleton = StockHistoricalDataClient(
            ALPACA_API_KEY, ALPACA_SECRET_KEY
        )
    return _alpaca_historical_singleton


class AlpacaHistoricalClient:
    TF_MAP = {
        "1m": TimeFrame(1, TimeFrameUnit.Minute),
        "3m": TimeFrame(3, TimeFrameUnit.Minute),
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "30m": TimeFrame(30, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
        "1d": TimeFrame(1, TimeFrameUnit.Day),
    }

    @staticmethod
    def _to_utc(dt_val) -> datetime:
        if isinstance(dt_val, datetime):
            dt = dt_val
        else:
            dt = datetime.fromisoformat(str(dt_val))
        if dt.tzinfo is None:
            dt = TIMEZONE.localize(dt)
        return dt.astimezone(UTC)

    @staticmethod
    def fetch_bars(ticker: str, timeframe: str, start_date, end_date):
        if timeframe not in AlpacaHistoricalClient.TF_MAP:
            raise ValueError(f"Timeframe no soportado: {timeframe}")
        start_dt = AlpacaHistoricalClient._to_utc(start_date)
        end_dt = AlpacaHistoricalClient._to_utc(end_date)
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=AlpacaHistoricalClient.TF_MAP[timeframe],
            start=start_dt,
            end=end_dt,
            feed=DataFeed.IEX,
            adjustment="raw",
        )
        resp = _alpaca_historical().get_stock_bars(request)
        try:
            bars = resp[ticker]
        except (KeyError, TypeError):
            bars = []
        time.sleep(0.1)
        out = []
        for bar in bars:
            ts = bar.timestamp
            if ts is None:
                continue
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:
                ts = ts.tz_localize(UTC)
            ts_et = ts.tz_convert(TIMEZONE)
            out.append({
                "t": ts_et,
                "o": float(bar.open),
                "h": float(bar.high),
                "l": float(bar.low),
                "c": float(bar.close),
                "v": float(bar.volume),
            })
        return out

    @staticmethod
    def get_prev_day_change(ticker: str) -> float:
        end_date = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        start_date = (datetime.now(TIMEZONE) - timedelta(days=10)).strftime("%Y-%m-%d")
        bars_1d = AlpacaHistoricalClient.fetch_bars(ticker, "1d", start_date, end_date)
        if len(bars_1d) < 2:
            return 0.0
        c_last = bars_1d[-1]["c"]
        c_prev = bars_1d[-2]["c"]
        return float(((c_last - c_prev) / c_prev * 100.0) if c_prev else 0.0)

    @staticmethod
    def get_macro_prices() -> dict:
        out: dict = {}
        end_date = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        start_date = (datetime.now(TIMEZONE) - timedelta(days=10)).strftime("%Y-%m-%d")
        for sym in TICKERS_MACRO:
            try:
                bars = AlpacaHistoricalClient.fetch_bars(sym, "1d", start_date, end_date)
                if len(bars) >= 2:
                    c_last = float(bars[-1]["c"])
                    c_prev = float(bars[-2]["c"])
                    change = ((c_last - c_prev) / c_prev * 100.0) if c_prev else 0.0
                    out[sym] = {"price": round(c_last, 2), "change": round(change, 2)}
                elif len(bars) == 1:
                    out[sym] = {"price": round(float(bars[-1]["c"]), 2), "change": 0.0}
                else:
                    out[sym] = {"price": 0.0, "change": 0.0}
            except Exception as e:
                out[sym] = {"price": 0.0, "change": 0.0, "error": str(e)}
        return out


class BPCalculator:
    @staticmethod
    def calculate_bp(bars_dict, cutoff_time: pd.Timestamp | None = None):
        """BP = promedio EMA3/EMA9 por timeframe, barras estrictamente < cutoff_time."""
        ema3_list = []
        ema9_list = []
        for tf, bars in bars_dict.items():
            if not bars:
                continue
            if cutoff_time is not None:
                if isinstance(bars, pd.DataFrame):
                    cutoff = pd.Timestamp(cutoff_time)
                    if cutoff.tzinfo is None:
                        cutoff = cutoff.tz_localize(TIMEZONE)
                    else:
                        cutoff = cutoff.tz_convert(TIMEZONE)
                    df_slice = bars.loc[: cutoff - pd.Timedelta(nanoseconds=1)]
                    bars_filtered = df_slice.reset_index()[["t", "c"]].to_dict("records")
                else:
                    bars_filtered = []
                    for b in bars:
                        ts = b["t"]
                        if ts.tzinfo is None:
                            ts = pd.Timestamp(ts).tz_localize(TIMEZONE)
                        if ts < cutoff_time:
                            bars_filtered.append(b)
            else:
                if isinstance(bars, pd.DataFrame):
                    bars_filtered = bars.reset_index()[["t", "c"]].to_dict("records")
                else:
                    bars_filtered = bars
            if len(bars_filtered) < 3:
                continue
            closes = pd.Series([float(b["c"]) for b in bars_filtered], dtype=float)
            ema3 = closes.ewm(span=3, adjust=False).mean().iloc[-1]
            ema9 = closes.ewm(span=9, adjust=False).mean().iloc[-1]
            ema3_list.append(float(ema3))
            ema9_list.append(float(ema9))
        if not ema3_list:
            return None
        bp = (np.mean(ema3_list) + np.mean(ema9_list)) / 2
        return bp


class TargetsCalculator:
    @staticmethod
    def calculate_range_3d(
        ticker,
        daily_bars,
        pm_high=None,
        pm_low=None,
        bars_1h=None,
        cutoff_time=None,
    ):
        """range_3d = ancho BB(20,2) EWM en 1H pre-cutoff; fallback avg H-L 3d diarios."""
        if bars_1h and cutoff_time is not None:
            filtered = _filter_bars_before(bars_1h, cutoff_time)
            if len(filtered) >= N_VELAS_BB:
                closes = [float(b["c"]) for b in filtered[-N_VELAS_BB:]]
                bbt, bbb = _compute_bb_from_closes(closes)
                if bbt is not None and bbb is not None:
                    range_3d = float(bbt) - float(bbb)
                    if range_3d > 0:
                        return range_3d
        if not daily_bars:
            return 0.0
        last3 = daily_bars[-3:]
        ranges = [float(b["h"]) - float(b["l"]) for b in last3 if float(b["h"]) > float(b["l"])]
        return sum(ranges) / len(ranges) if ranges else 0.0

    @staticmethod
    def calculate_targets(bp, range_3d, signals=None, *, caution_note=None, gap_type=None):
        """Targets INT/MAX simétricos."""
        base_int = 0.33 * range_3d
        base_max = 0.66 * range_3d
        return {
            "int_pos": bp + base_int,
            "int_neg": bp - base_int,
            "max_pos": bp + base_max,
            "max_neg": bp - base_max,
            "int_dist": base_int,
            "max_dist": base_max,
        }


class AlpacaSnapshotClient:
    @staticmethod
    def get_open_price(ticker: str) -> float | None:
        start_et = datetime.now(TIMEZONE).replace(hour=9, minute=30, second=0, microsecond=0)
        end_et = start_et + timedelta(minutes=2)
        request = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            start=start_et.astimezone(UTC),
            end=end_et.astimezone(UTC),
            feed=DataFeed.IEX,
            adjustment="raw",
        )
        resp = _alpaca_historical().get_stock_bars(request)
        try:
            bars = resp[ticker]
        except (KeyError, TypeError):
            bars = []
        if not bars:
            return None
        return float(bars[0].open)


class SkipFilter:
    @staticmethod
    def apply_skip_filters(ticker, prev_day_change, gap_pct, signals):
        if prev_day_change > 9.5 and "GAP_DOWN" in signals:
            return True
        if gap_pct <= -5 and "GAP_DOWN" in signals:
            return True
        if ticker == "NVDA" and "BAJ" in signals and "BP" in signals:
            return True
        return False
