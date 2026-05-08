from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timedelta

import pandas as pd

from dc.constants import TIMEZONE, OPEN_930_TF_LIST, N_VELAS_BB
from dc.utils import (
    _bars_list_to_mi_dataframe,
    _filter_bars_before,
    _compute_bb_from_closes,
)
from dc.indicators import (
    precio_en_rango,
    direction_from_dist,
    compute_open_zone,
    get_rebote_umbral,
    _get_prev_day_hint,
    evaluar_rebote,
    finalize_dashboard_output,
)
from dc.premium_detector import PremiumDetector
from dc.data_clients import AlpacaHistoricalClient, AlpacaSnapshotClient
from dc.outputs import write_json, write_context_compressed, write_ai_dashboard

logger = logging.getLogger(__name__)

# Pairs: (bar_tf_key, label_for_flags)
_CAUTION_TF_PAIRS = [
    ("1m", "1M"), ("5m", "5M"), ("15m", "15M"),
    ("30m", "30M"), ("1h", "1H"), ("1d", "1D"),
]


# ── Private helpers (ported from mi_backtesting_nvda) ──────────────────────

def _rth_mask_vectorized(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: True for rows within RTH (09:30–16:00 ET)."""
    if df is None or df.empty:
        return pd.Series(dtype=bool)
    ts_col = "timestamp" if "timestamp" in df.columns else df.index
    if isinstance(ts_col, str):
        ts = pd.to_datetime(df[ts_col])
    else:
        ts = pd.to_datetime(ts_col)
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(TIMEZONE)
    else:
        ts = ts.dt.tz_convert(TIMEZONE)
    time = ts.dt.time
    rth_start = pd.Timestamp("09:30").time()
    rth_end = pd.Timestamp("16:00").time()
    return pd.Series((time >= rth_start) & (time <= rth_end), index=df.index)


def _build_tfs_rth(tfs_live: dict[str, pd.DataFrame], ticker: str) -> dict[str, pd.DataFrame]:
    """Filter each TF dataframe to RTH bars only."""
    result: dict[str, pd.DataFrame] = {}
    for tf, df in tfs_live.items():
        if df is None or df.empty:
            result[tf] = pd.DataFrame()
            continue
        mask = _rth_mask_vectorized(df)
        if mask.empty:
            result[tf] = pd.DataFrame()
        else:
            result[tf] = df.loc[mask].reset_index(drop=True)
    return result


def _compute_caution_real_930(
    tfs_live: dict[str, pd.DataFrame],
    fecha_today: object,
    open_price: float,
    ticker: str,
    tfs_rth: dict[str, pd.DataFrame] | None = None,
) -> str:
    """
    Compute BB flags at 9:30 open using the same BB(20,2) EWM logic as compute_bb_flags.
    Uses prev-session closes (RTH closes up to 16:00 yesterday) for each TF.
    """
    if tfs_rth is None:
        tfs_rth = _build_tfs_rth(tfs_live, ticker)

    cautions: list[str] = []
    for tf, label in _CAUTION_TF_PAIRS:
        df = tfs_live.get(tf)
        if df is None or df.empty:
            continue
        # Get closes from prev sessions (exclude today)
        if "date_et" in df.columns:
            prev_df = df[df["date_et"] < fecha_today]
        elif "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"])
            if ts.dt.tz is None:
                ts = ts.dt.tz_localize(TIMEZONE)
            else:
                ts = ts.dt.tz_convert(TIMEZONE)
            prev_df = df[ts.dt.date < fecha_today]
        else:
            prev_df = df

        if prev_df.empty:
            continue

        close_col = "close" if "close" in prev_df.columns else "c"
        if close_col not in prev_df.columns:
            continue

        closes = prev_df[close_col].dropna().values[-N_VELAS_BB:]
        if len(closes) < 2:
            continue

        bbt, bbb = _compute_bb_from_closes(closes)
        if bbt is not None and open_price > bbt:
            cautions.append(f"BBT {label}")
        if bbb is not None and open_price < bbb:
            cautions.append(f"BBB {label}")

    return " ".join(cautions) if cautions else "Sin caution"


def _parse_flags(flags_str: str | None) -> set[str]:
    """Parse 'BBT 1H BBB 5M' → {'BBT 1H', 'BBB 5M'}."""
    if not flags_str or flags_str.strip() in ("Sin caution", "PENDIENTE", "Sin datos BB"):
        return set()
    found = re.findall(r"(BBT|BBB)\s+(\w+)", flags_str)
    return {f"{a} {b}" for a, b in found}


def compute_bb_shift(
    bb_flags_premarket: str | None,
    bb_flags_real_930: str | None,
) -> str:
    """
    Compare premarket BB flags vs real 9:30 BB flags.

    Returns one of: igual / escalo / desaparecio / nuevo / cambio_tipo
    - igual: same set of flags
    - nuevo: flags appeared that weren't in premarket (0 → something)
    - desaparecio: flags disappeared (something → fewer / 0)
    - escalo: more flags in real than premarket (worsened)
    - cambio_tipo: same TF but BBT↔BBB flipped
    """
    old = _parse_flags(bb_flags_premarket)
    new = _parse_flags(bb_flags_real_930)

    if old == new:
        return "igual"

    # Detect cambio_tipo: a TF changed from BBT to BBB or vice versa
    old_tfs = {f.split()[1]: f.split()[0] for f in old}
    new_tfs = {f.split()[1]: f.split()[0] for f in new}
    shared_tfs = set(old_tfs) & set(new_tfs)
    if any(old_tfs[tf] != new_tfs[tf] for tf in shared_tfs):
        return "cambio_tipo"

    if not old and new:
        return "nuevo"
    if old and not new:
        return "desaparecio"
    if len(new) > len(old):
        return "escalo"
    return "desaparecio"


# ── Main mode ──────────────────────────────────────────────────────────────

async def run_mode_930(tickers_to_run: list, date_str: str) -> None:
    logger.info(f"=== MODO: open_930 | tickers: {len(tickers_to_run)} ===")
    try:
        with open(f"outputs/premarket_9_28_{date_str}.json", "r", encoding="utf-8") as f:
            premarket_data = json.load(f)
    except FileNotFoundError:
        logger.warning("Error: No se encontraron datos premarket_9_28")
        return

    premarket_data["tickers_order"] = tickers_to_run
    for ticker in tickers_to_run:
        try:
            if ticker not in premarket_data["tickers"]:
                if ticker in premarket_data.get("skips", {}):
                    td = premarket_data["skips"][ticker]
                    if not isinstance(td, dict):
                        logger.warning(f"[{ticker}] skips sin dict — omitido open_930")
                        continue
                else:
                    logger.warning(f"[{ticker}] sin fila en premarket_9_28.json — omitido open_930")
                    continue
            else:
                td = premarket_data["tickers"][ticker]

            open_price = AlpacaSnapshotClient.get_open_price(ticker)
            if open_price is None:
                logger.warning("%s: sin open_930 (Alpaca)", ticker)
                continue

            bp = td["bp"]
            dist = open_price - bp
            _int_dist = float(td.get("int_dist") or 0.0)
            direction = direction_from_dist(dist, int_dist=_int_dist)

            td["open_930"] = open_price
            td["dist"] = dist
            td["direction"] = direction

            oz, opct = compute_open_zone(
                open_price,
                bp,
                td.get("int_pos"),
                td.get("int_neg"),
                direction,
                int_dist=_int_dist,
            )
            td["open_zone"] = oz
            td["open_pct_en_rango"] = opct
            td["rebote_umbral"] = get_rebote_umbral(_int_dist)

            logger.info(
                f"[{ticker}] open_930={open_price} | "
                f"open_zone={oz} | "
                f"dist_open={round(open_price - bp, 4)}"
            )

            prev_date_et = datetime.now(TIMEZONE).date() - timedelta(days=1)
            cutoff_et = datetime.now(TIMEZONE).replace(hour=9, minute=28, second=0, microsecond=0)
            cutoff_prev_1600 = datetime(
                prev_date_et.year, prev_date_et.month, prev_date_et.day, 16, 0, 0, tzinfo=TIMEZONE
            )

            end_fetch = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
            bars_dict: dict[str, list] = {}
            for tf in OPEN_930_TF_LIST:
                if tf == "1d":
                    start_fetch = (datetime.now(TIMEZONE) - timedelta(days=10)).strftime("%Y-%m-%d")
                elif tf == "1h":
                    start_fetch = (datetime.now(TIMEZONE) - timedelta(days=365)).strftime("%Y-%m-%d")
                else:
                    start_fetch = (datetime.now(TIMEZONE) - timedelta(days=2)).strftime("%Y-%m-%d")
                try:
                    bars_dict[tf] = AlpacaHistoricalClient.fetch_bars(ticker, tf, start_fetch, end_fetch)
                except Exception as _fetch_exc:
                    logger.warning(f"[{ticker}] fetch {tf} falló: {_fetch_exc} — usando lista vacía")
                    bars_dict[tf] = []

            if "1d" in bars_dict:
                bars_dict["1d"] = _filter_bars_before(bars_dict["1d"], cutoff_et)

            bars_1m_pre = _filter_bars_before(bars_dict.get("1m", []), cutoff_et)
            _bars_pm_4am = [b for b in bars_1m_pre if b["t"].hour >= 4]
            pm_high = max((float(b["h"]) for b in _bars_pm_4am), default=None)
            pm_low = min((float(b["l"]) for b in _bars_pm_4am), default=None)
            precio_premarket = float(bars_1m_pre[-1]["c"]) if bars_1m_pre else None

            prev_day_high = float(bars_dict["1d"][-1]["h"]) if bars_dict.get("1d") else None
            prev_day_low = float(bars_dict["1d"][-1]["l"]) if bars_dict.get("1d") else None

            rango_pm = (
                precio_en_rango(float(precio_premarket), pm_high, pm_low)
                if (precio_premarket is not None and pm_high is not None and pm_low is not None)
                else {"pct": 0.5, "label": "sin_datos"}
            )
            rango_prev_day = (
                precio_en_rango(float(precio_premarket), prev_day_high, prev_day_low)
                if (precio_premarket is not None and prev_day_high is not None and prev_day_low is not None)
                else {"pct": 0.5, "label": "sin_datos"}
            )

            for tf, bars in bars_dict.items():
                n = len(bars)
                first_ts = str(bars[0]["t"])[:16] if n > 0 else "sin datos"
                last_ts = str(bars[-1]["t"])[:16] if n > 0 else "sin datos"
                logger.debug(f"[{ticker}] {tf}: {n} velas | {first_ts} → {last_ts}")

            td["bb_flags_real_930"] = None
            td["bb_shift"] = None

            tfs_live = {
                tf: _bars_list_to_mi_dataframe(bars_dict.get(tf, []))
                for tf in OPEN_930_TF_LIST
            }
            try:
                fecha_today = datetime.now(TIMEZONE).date()
                ts_930 = pd.Timestamp(
                    datetime.now(TIMEZONE).replace(hour=9, minute=30, second=0, microsecond=0)
                )
                _inyecto_vela_930 = False
                for tf in list(tfs_live.keys()):
                    df_tf = tfs_live[tf]
                    if df_tf is None or df_tf.empty:
                        continue
                    if "date_et" not in df_tf.columns:
                        continue
                    mask_hoy = df_tf["date_et"] == fecha_today
                    ya_rth_hoy = False
                    if mask_hoy.any():
                        sub_hoy = df_tf.loc[mask_hoy]
                        ya_rth_hoy = bool(_rth_mask_vectorized(sub_hoy).any())
                    if ya_rth_hoy:
                        continue
                    fila = pd.DataFrame([{
                        "timestamp": ts_930,
                        "open": float(open_price),
                        "high": float(open_price),
                        "low": float(open_price),
                        "close": float(open_price),
                        "volume": 0.0,
                        "date_et": fecha_today,
                    }])
                    tfs_live[tf] = (
                        pd.concat([df_tf, fila], ignore_index=True)
                        .sort_values("timestamp")
                        .reset_index(drop=True)
                    )
                    _inyecto_vela_930 = True
                if _inyecto_vela_930:
                    logger.info(f"[{ticker}] vela RTH inyectada: open_930={open_price} | ts={ts_930}")

                tfs_rth = _build_tfs_rth(tfs_live, ticker)
                cr930 = _compute_caution_real_930(tfs_live, fecha_today, open_price, ticker, tfs_rth)
                td["bb_flags_real_930"] = cr930
                td["bb_shift"] = compute_bb_shift(td.get("bb_flags"), cr930)
                logger.info(
                    f"[{ticker}] bb_flags_real_930='{cr930}' | "
                    f"bb_shift='{td.get('bb_shift')}'"
                )
            except Exception as _caut_exc:
                logger.warning("  [bb_shift] %s: %s", ticker, _caut_exc)

            td["rango_pm"] = rango_pm
            td["rango_prev_day"] = rango_prev_day

            _pdc = td.get("prev_day_change")
            _prev_f = float(_pdc) if _pdc not in (None, "", "nan") else None
            td["prev_day_hint"] = _get_prev_day_hint(ticker, _prev_f, td.get("direction", "ZONA_MUERTA"))
            td["rebote_hint"] = evaluar_rebote(
                float(td.get("rebote_actual", 0)),
                float(td.get("int_dist", 0)),
            )

            logger.info(
                f"[{ticker}] open_930 resultado: direction={direction} | "
                f"open_zone={oz} | bb_shift={td.get('bb_shift')}"
            )

        except Exception as e:
            logger.error(f"[{ticker}] Error procesando: {e}", exc_info=True)
            continue

    premarket_data.setdefault("skips", {})
    n_ok = len(tickers_to_run)
    skips_n = sum(1 for t in tickers_to_run if premarket_data.get("tickers", {}).get(t, {}).get("skip"))
    logger.info(f"=== MODO open_930 completado | OK={n_ok} | SKIP={skips_n} ===")
    finalize_dashboard_output(premarket_data)
    write_json(premarket_data, f"open_930_{date_str}.json")
    write_context_compressed(premarket_data, date_str, "open_930")
    write_ai_dashboard(premarket_data, date_str, "open_930")
