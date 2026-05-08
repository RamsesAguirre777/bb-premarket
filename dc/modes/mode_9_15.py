from __future__ import annotations
import logging
from datetime import datetime, timedelta

import pandas as pd

from dc.constants import TICKERS, TIMEZONE, TF_LIST
from dc.utils import _filter_bars_before
from dc.indicators import (
    compute_badge_long,
    compute_bb_flags,
    compute_signals_3_9,
    precio_en_rango,
    direction_from_dist,
    _get_prev_day_hint,
    finalize_dashboard_output,
)
from dc.data_clients import (
    AlpacaHistoricalClient,
    BPCalculator,
    TargetsCalculator,
    SkipFilter,
)
from dc.outputs import write_json, write_context_compressed, write_ai_dashboard

logger = logging.getLogger(__name__)


async def run_mode_9_15(tickers_to_run: list, date_str: str, output_data: dict) -> None:
    logger.info(f"=== MODO: premarket_9_15 | tickers: {len(tickers_to_run)} ===")
    for ticker in tickers_to_run:
        try:
            bars_dict = {}
            _end_hist = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            for tf in TF_LIST:
                days_back = 365 if tf == "1h" else 2
                bars = AlpacaHistoricalClient.fetch_bars(
                    ticker,
                    tf,
                    (datetime.now(TIMEZONE) - timedelta(days=days_back)).strftime("%Y-%m-%d"),
                    _end_hist,
                )
                bars_dict[tf] = bars

            for tf, bars in bars_dict.items():
                n = len(bars)
                first_ts = str(bars[0]["t"])[:16] if n > 0 else "sin datos"
                last_ts = str(bars[-1]["t"])[:16] if n > 0 else "sin datos"
                logger.debug(f"[{ticker}] {tf}: {n} velas | {first_ts} → {last_ts}")

            daily_bars = AlpacaHistoricalClient.fetch_bars(
                ticker,
                "1d",
                (datetime.now(TIMEZONE) - timedelta(days=10)).strftime("%Y-%m-%d"),
                datetime.now(TIMEZONE).strftime("%Y-%m-%d"),
            )

            cutoff_et = datetime.now(TIMEZONE).replace(hour=9, minute=0, second=0, microsecond=0)
            bp = BPCalculator.calculate_bp(bars_dict, cutoff_time=pd.Timestamp(cutoff_et))
            if bp is not None:
                logger.info("[%s] BP=%.4f | cutoff=%s", ticker, float(bp), cutoff_et.strftime("%H:%M:%S"))
            else:
                logger.warning("[%s] BP=None — verificar barras disponibles", ticker)
                continue

            bars_dict["1d"] = _filter_bars_before(daily_bars, cutoff_et)

            today_date_et = datetime.now(TIMEZONE).date()
            prev_date_et = today_date_et - timedelta(days=1)

            daily_prev = [b for b in daily_bars if b["t"].date() < today_date_et]
            daily_prev.sort(key=lambda x: x["t"])

            prev_close = float(daily_prev[-1]["c"]) if daily_prev else 0.0
            prev_day_high = float(daily_prev[-1]["h"]) if daily_prev else None
            prev_day_low = float(daily_prev[-1]["l"]) if daily_prev else None
            if len(daily_prev) >= 2:
                c_last = float(daily_prev[-1]["c"])
                c_prev = float(daily_prev[-2]["c"])
                prev_day_change_pct = ((c_last - c_prev) / c_prev * 100.0) if c_prev else 0.0
            else:
                prev_day_change_pct = 0.0

            bars_1m_pre = _filter_bars_before(bars_dict.get("1m", []), cutoff_et)
            if not bars_1m_pre:
                continue
            _bars_pm_4am = [b for b in bars_1m_pre if b["t"].hour >= 4]
            pm_high = max((float(b["h"]) for b in _bars_pm_4am), default=None)
            pm_low = min((float(b["l"]) for b in _bars_pm_4am), default=None)
            precio_premarket = float(bars_1m_pre[-1]["c"])
            rango_pm = (
                precio_en_rango(precio_premarket, pm_high, pm_low)
                if (pm_high is not None and pm_low is not None)
                else {"pct": 0.5, "label": "sin_datos"}
            )
            rango_prev_day = (
                precio_en_rango(precio_premarket, prev_day_high, prev_day_low)
                if (prev_day_high is not None and prev_day_low is not None)
                else {"pct": 0.5, "label": "sin_datos"}
            )

            if prev_close > 0:
                gap_pct = ((precio_premarket - prev_close) / prev_close) * 100.0
                gap_type = "GAP_UP" if gap_pct > 0 else ("GAP_DOWN" if gap_pct < 0 else "FLAT")
            else:
                gap_pct = 0.0
                gap_type = "FLAT"

            cutoff_prev_1600 = datetime(
                prev_date_et.year, prev_date_et.month, prev_date_et.day, 16, 0, 0, tzinfo=TIMEZONE
            )

            signals_str = compute_signals_3_9(bars_dict, cutoff_et)
            badge_long = compute_badge_long(
                bars_dict,
                cutoff_time=cutoff_et,
                now_time=datetime.now(TIMEZONE),
                precio=float(precio_premarket),
            )
            bb_flags = compute_bb_flags(bars_dict, precio_premarket, cutoff_prev_1600)

            range_3d = TargetsCalculator.calculate_range_3d(
                ticker,
                daily_prev,
                pm_high=pm_high,
                pm_low=pm_low,
                bars_1h=bars_dict.get("1h", []),
                cutoff_time=cutoff_et,
            )
            targets = TargetsCalculator.calculate_targets(bp, range_3d, [bb_flags, gap_type])
            logger.info(
                "[%s] TARGETS: int_pos=%.4f int_neg=%.4f max_pos=%.4f max_neg=%.4f",
                ticker,
                targets.get("int_pos"),
                targets.get("int_neg"),
                targets.get("max_pos"),
                targets.get("max_neg"),
            )

            skip_reason = None
            if SkipFilter.apply_skip_filters(ticker, prev_day_change_pct, gap_pct, [gap_type]):
                skip_reason = "Filtro SKIP activado"

            dist_pm = precio_premarket - bp
            direction_pm = direction_from_dist(dist_pm)

            logger.info(
                f"[{ticker}] precio_pm={round(precio_premarket, 4)} | "
                f"dist_bp={round(dist_pm, 4)} | "
                f"dir={direction_pm} | gap={gap_type} {round(gap_pct, 3)}%"
            )
            logger.info(
                f"[{ticker}] bb_flags='{bb_flags}' | "
                f"signals='{signals_str}' | "
                f"badge={round(badge_long, 1)}%"
            )

            output_data["tickers"][ticker] = {
                "bp": bp,
                "int_pos": targets["int_pos"],
                "int_neg": targets["int_neg"],
                "max_pos": targets["max_pos"],
                "max_neg": targets["max_neg"],
                "int_dist": targets["int_dist"],
                "max_dist": targets["max_dist"],
                "gap_type": gap_type,
                "gap_pct": gap_pct,
                "prev_day_change": prev_day_change_pct,
                "signals": signals_str,
                "signals_3_9": signals_str,
                "badge_long": round(badge_long, 2),
                "bb_flags": bb_flags,
                "skip": skip_reason is not None,
                "skip_reason": skip_reason,
                "dist": dist_pm,
                "direction": direction_pm,
                "prev_day_hint": _get_prev_day_hint(
                    ticker,
                    float(prev_day_change_pct)
                    if prev_day_change_pct not in (None, "", "nan")
                    else None,
                    direction_pm,
                ),
                "rango_pm": rango_pm,
                "rango_prev_day": rango_prev_day,
            }

        except Exception as e:
            logger.error(f"[{ticker}] Error procesando: {e}", exc_info=True)
            continue

    tickers_ok = output_data.get("tickers", {})
    skips_n = sum(1 for t in tickers_ok.values() if t.get("skip"))
    logger.info(
        f"=== MODO premarket_9_15 completado | OK={len(tickers_ok)} | SKIP={skips_n} ==="
    )
    finalize_dashboard_output(output_data)
    write_json(output_data, f"premarket_9_15_{date_str}.json")
    write_context_compressed(output_data, date_str, "premarket_9_15")
    write_ai_dashboard(output_data, date_str, "premarket_9_15")
