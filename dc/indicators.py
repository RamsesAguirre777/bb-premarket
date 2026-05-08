from __future__ import annotations
from datetime import datetime
import pandas as pd
import numpy as np
import logging

from dc.constants import (
    REBOTE_UMBRAL_PCT,
    VELOCIDAD_REGLA,
    SEGUNDO_TOQUE_REGLA,
    FAMILIAS,
    N_VELAS_BB,
    ZM_THRESHOLD_PCT,
    CAUTION_TEXTS,
    PREV_DAY_RULES,
    _OPEN_ZONE_SKIP_RULES,
    _OPEN_ZONE_WARN_RULES,
    ZONE_SIZE_HINT,
    ALC_T3_SOLO_INT_TICKERS,
)
from dc.utils import (
    _compute_bb_from_closes,
    _filter_bars_before,
    _filter_bars_upto_inclusive,
)
from dc.premium_detector import PremiumDetector

logger = logging.getLogger(__name__)

_CAUTION_TF_PAIRS = [
    ("1m", "1M"),
    ("5m", "5M"),
    ("15m", "15M"),
    ("30m", "30M"),
    ("1h", "1H"),
    ("1d", "1D"),
]


def _get_prev_day_hint(ticker: str, prev_day_pct: float | None, direction: str) -> str:
    if prev_day_pct is None:
        return "neutral"
    rules = PREV_DAY_RULES.get(ticker, PREV_DAY_RULES["DEFAULT"])
    if direction == "ALCISTA":
        if prev_day_pct < rules.get("alc_skip_bajo", -3.0):
            return "SKIP"
        if prev_day_pct < 0:
            return "REDUCIR_x0.5"
        if prev_day_pct >= rules.get("alc_size2_bajo", 2.0):
            return "SIZE_x2"
        return "SIZE_x1"
    if direction == "BAJISTA":
        if prev_day_pct > rules.get("baj_skip_positivo", 0.0):
            return "SKIP"
        if prev_day_pct < rules.get("baj_size2_alto", -3.0):
            return "SIZE_x2"
        if prev_day_pct < 0:
            return "SIZE_x1"
        return "REDUCIR_x0.5"
    if prev_day_pct >= 2.0:
        return "regime_alcista"
    if prev_day_pct <= -3.0:
        return "regime_bajista"
    return "neutral"


def evaluar_rebote(rebote_actual: float, int_dist: float) -> str:
    if int_dist <= 0:
        return "mantener"
    pct = rebote_actual / int_dist
    if pct >= 1.0:
        return "sesgo_cambia"
    if pct >= REBOTE_UMBRAL_PCT:
        return "salir"
    return "mantener"


def compute_badge_long(
    bars_dict: dict,
    cutoff_time: datetime,
    now_time: datetime,
    precio: float | None = None,
) -> float:
    up = 0.0

    bars_1m = bars_dict.get("1m", [])
    if bars_1m:
        filtered = _filter_bars_before(bars_1m, cutoff_time)
        if len(filtered) >= 20:
            closes = pd.Series([float(b["c"]) for b in filtered], dtype=float)
            ema9 = float(closes.ewm(span=9, adjust=False).mean().iloc[-1])
            ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
            if ema9 > ema20:
                up += 25.0

    bars_15m = bars_dict.get("15m", [])
    if bars_15m and precio is not None:
        filtered = _filter_bars_before(bars_15m, cutoff_time)
        if len(filtered) >= 20:
            closes = pd.Series([float(b["c"]) for b in filtered], dtype=float)
            ema20_15m = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
            if precio > ema20_15m:
                up += 25.0

    if bars_1m:
        filtered = _filter_bars_before(bars_1m, now_time)
        if len(filtered) >= 20:
            closes = pd.Series([float(b["c"]) for b in filtered], dtype=float)
            ema9 = float(closes.ewm(span=9, adjust=False).mean().iloc[-1])
            ema20 = float(closes.ewm(span=20, adjust=False).mean().iloc[-1])
            if ema9 > ema20:
                up += 25.0

    GAP_THRESHOLD = 0.0005
    for tf in ("1d", "1h", "30m", "15m", "5m"):
        bars = bars_dict.get(tf, [])
        if not bars:
            continue
        filtered = _filter_bars_before(bars, now_time)
        if len(filtered) < 2:
            continue
        last = filtered[-1]
        prev = filtered[-2]
        open_p = float(last["o"])
        close_p = float(last["c"])
        prev_close = float(prev["c"])
        if prev_close == 0:
            continue
        gap_pct = (open_p - prev_close) / prev_close
        if gap_pct > GAP_THRESHOLD:
            up += 5
        elif gap_pct < -GAP_THRESHOLD:
            pass
        elif close_p > open_p:
            up += 5

    return float(up)


def compute_signals_3_9(bars_dict: dict, cutoff_time: datetime) -> str:
    parts = []
    for tf in ["15m", "30m", "1h"]:
        if tf not in bars_dict:
            continue
        bars_tf = bars_dict[tf]
        if isinstance(bars_tf, pd.DataFrame):
            if bars_tf.empty:
                continue
        else:
            if not bars_tf:
                continue
        filtered = _filter_bars_before(bars_tf, cutoff_time)
        if len(filtered) < 9:
            continue
        tail20 = filtered[-N_VELAS_BB:]
        closes = pd.Series([float(b["c"]) for b in tail20], dtype=float)
        ema3 = float(closes.ewm(span=3, adjust=False).mean().iloc[-1])
        ema9 = float(closes.ewm(span=9, adjust=False).mean().iloc[-1])
        signal = "up" if ema3 > ema9 else "down"
        parts.append(f"3/9 {signal} {tf}")
    return ", ".join(parts) if parts else ""


def compute_bb_flags(
    bars_dict: dict,
    precio_premarket: float,
    cutoff_prev_1600: datetime,
) -> str:
    """BB flags: price vs BB(20,2) built from prev-day bars up to 16:00."""
    cautions = []
    for tf, label in _CAUTION_TF_PAIRS:
        if tf not in bars_dict:
            continue
        bars_tf = bars_dict[tf]
        if isinstance(bars_tf, pd.DataFrame):
            if bars_tf.empty:
                continue
        else:
            if not bars_tf:
                continue
        filtered_prev = _filter_bars_upto_inclusive(bars_tf, cutoff_prev_1600)
        closes_prev = [b["c"] for b in filtered_prev]
        bbt, bbb = _compute_bb_from_closes(closes_prev)
        if bbt is not None and precio_premarket > bbt:
            key = f"BBT {label}"
            cautions.append(CAUTION_TEXTS.get(key, key))
        if bbb is not None and precio_premarket < bbb:
            key = f"BBB {label}"
            cautions.append(CAUTION_TEXTS.get(key, key))
    return " ".join(cautions) if cautions else "Sin caution"


def ema_alignment(
    open_p: float,
    e20: float,
    e50: float,
    e200: float,
    pct: float = 0.001,
) -> str:
    def zone(o, e):
        if not e or e == 0:
            return "unknown"
        d = (o - e) / e
        return "above" if d > pct else ("below" if d < -pct else "at")

    zones = [zone(open_p, e20), zone(open_p, e50), zone(open_p, e200)]
    if "at" in zones:
        return "at_any"
    if all(z == "above" for z in zones):
        return "sobre_3"
    if all(z == "below" for z in zones):
        return "bajo_3"
    return "entre"


def ema_sr_context(
    precio: float,
    e20: float | None,
    e50: float | None,
    e200: float | None,
) -> str:
    parts = []
    for label, ema in (("EMA20", e20), ("EMA50", e50), ("EMA200", e200)):
        if not ema:
            continue
        dist_pct = (precio - ema) / ema * 100
        role = "soporte" if dist_pct > 0 else "resistencia"
        parts.append(f"{label} {role} {dist_pct:+.2f}%")
    return " | ".join(parts) if parts else ""


def precio_en_rango(precio: float, high: float, low: float) -> dict:
    rango = high - low
    if rango <= 0:
        return {"pct": 0.5, "label": "sin_rango"}
    pct = (precio - low) / rango
    pct = max(0.0, min(1.0, pct))
    if pct >= 0.75:
        label = "cerca_max"
    elif pct <= 0.25:
        label = "cerca_min"
    else:
        label = "zona_media"
    return {"pct": round(pct, 3), "label": label}


def direction_from_dist(dist: float, int_dist: float = 0.0) -> str:
    threshold = (int_dist * ZM_THRESHOLD_PCT) if int_dist > 0 else 0.25
    if dist > threshold:
        return "ALCISTA"
    if dist < -threshold:
        return "BAJISTA"
    return "ZONA_MUERTA"


def compute_open_zone(
    open_930: float,
    bp: float,
    int_pos: float | None,
    int_neg: float | None,
    direction: str,
    int_dist: float = 0.0,
) -> tuple[str | None, float | None]:
    threshold = (int_dist * ZM_THRESHOLD_PCT) if int_dist > 0 else 0.25
    dist_abs = abs(open_930 - bp)
    if dist_abs < threshold:
        return "doble_dir_zone", 0.0

    if direction == "ALCISTA":
        if int_pos is None:
            return None, None
        rango = int_pos - bp
        if rango <= 0:
            return "doble_dir_zone", 0.0
        pct = (open_930 - bp) / rango
    elif direction == "BAJISTA":
        if int_neg is None:
            return None, None
        rango = bp - int_neg
        if rango <= 0:
            return "doble_dir_zone", 0.0
        pct = (bp - open_930) / rango
    else:
        return "doble_dir_zone", 0.0

    if pct <= 0:
        return "doble_dir_zone", round(pct, 4)
    if pct <= 0.333:
        zone = "normal_t1"
    elif pct <= 0.667:
        zone = "normal_t2"
    elif pct <= 1.0:
        zone = "normal_t3"
    else:
        zone = "ext_int_max"
    return zone, round(pct, 4)


def get_rebote_umbral(int_dist: float) -> float:
    if int_dist <= 0:
        return 0.0
    return int_dist * REBOTE_UMBRAL_PCT


def _match_open_zone_dir_spec(spec: str | None, direction: str, gap_type: str) -> bool:
    if spec is None:
        return True
    if spec == "BAJISTA+GAP_DOWN":
        return direction == "BAJISTA" and gap_type == "GAP_DOWN"
    return direction == spec


def _open_zone_skip_match(
    ticker: str,
    open_zone: str | None,
    caution_1v3: str | None,
    direction: str,
    gap_type: str,
    rule: tuple[list[str], list[str], str, str | None, str],
) -> bool:
    tickers_r, zones_r, c1_r, dir_r, _motivo = rule
    if ticker not in tickers_r or not open_zone or open_zone not in zones_r:
        return False
    if c1_r != "cualquier":
        if caution_1v3 != c1_r:
            return False
    if not _match_open_zone_dir_spec(dir_r, direction, gap_type):
        return False
    return True


def _gestion_live_fragments(ticker: str, direction: str) -> list[str]:
    out: list[str] = []
    std_vel_alc, std_vel_baj = True, True
    std_2t_alc, std_2t_baj = True, True

    vr = VELOCIDAD_REGLA.get(ticker)
    if vr:
        alc_c, baj_c, nota = vr
        if direction == "ALCISTA" and alc_c != std_vel_alc:
            out.append(f">30min→{'cerrar_INT' if alc_c else 'NO_cerrar'} ({nota})")
        elif direction == "BAJISTA" and baj_c != std_vel_baj:
            out.append(f">30min→{'cerrar_INT' if baj_c else 'NO_cerrar'} ({nota})")

    sr = SEGUNDO_TOQUE_REGLA.get(ticker)
    if sr:
        e_alc, e_baj, nota = sr
        if (e_alc, e_baj) != (std_2t_alc, std_2t_baj):
            parts = []
            if e_alc != std_2t_alc:
                parts.append(f"2do_toque→{'exit_ALC' if e_alc else 'no_exit_ALC'}")
            if e_baj != std_2t_baj:
                parts.append(f"2do_toque→{'exit_BAJ' if e_baj else 'no_exit_BAJ'}")
            if parts:
                out.append(" | ".join(parts) + f" ({nota})")
    return out


def _gestion_open_930_line(ticker: str, td: dict, direction: str) -> str | None:
    chunks: list[str] = []

    open_zone = td.get("open_zone")
    if open_zone == "ext_int_max":
        int_level = (
            td.get("int_pos") if direction == "ALCISTA" else td.get("int_neg")
        )
        if int_level is not None:
            chunks.append(
                f"ABRIÓ MÁS ALLÁ DEL INT (${float(int_level):.2f}) — "
                f"si cruza de vuelta hacia BP → CERRAR"
            )

    ru = td.get("rebote_umbral")
    if ru is not None and abs(float(ru) - 1.50) > 0.001:
        chunks.append(f"umbral_rebote=${float(ru):.2f}")
    chunks.extend(_gestion_live_fragments(ticker, direction))
    for w in td.get("evaluation", {}).get("warnings", []):
        if (
            "Zona+1v3:" in w
            or "escalo en t1/t2" in w
            or "escalo ALC — operable" in w
        ):
            chunks.append(w)
    if not chunks:
        return None
    return " | ".join(chunks)


def compute_cruces(tickers_data: dict) -> dict:
    cruces = {}
    for familia, members in FAMILIAS.items():
        dirs = {}
        for t in members:
            if t in tickers_data:
                dirs[t] = tickers_data[t].get("direction", "ZONA_MUERTA")
        if len(dirs) < 2:
            cruces[familia] = "SIN_DATOS"
            continue
        vals = list(dirs.values())
        tickers_str = list(dirs.keys())
        if all(v == "ALCISTA" for v in vals):
            cruces[familia] = f"AMBOS_ALC — {' + '.join(tickers_str)} alineados alcistas"
        elif all(v == "BAJISTA" for v in vals):
            cruces[familia] = f"AMBOS_BAJ — {' + '.join(tickers_str)} alineados bajistas"
        elif all(v == "ZONA_MUERTA" for v in vals):
            cruces[familia] = "AMBOS_ZM — sector indeciso"
        else:
            resumen = " | ".join([f"{t}={d}" for t, d in dirs.items()])
            cruces[familia] = f"DIVERGENCIA — {resumen}"

    for refugio in ("TLT", "GLD"):
        if refugio not in tickers_data:
            cruces["MACRO_REFUGIOS"] = f"⚠️ {refugio} sin datos — Patrón V incompleto"
            return cruces

    tlt_dir = tickers_data.get("TLT", {}).get("direction", "ZONA_MUERTA")
    gld_dir = tickers_data.get("GLD", {}).get("direction", "ZONA_MUERTA")
    if tlt_dir == "ALCISTA" and gld_dir == "ALCISTA":
        cruces["MACRO_REFUGIOS"] = "⚠️ PANIC SIGNAL — TLT+GLD ambos ALC = SKIP alcistas"
    elif tlt_dir == "BAJISTA" and gld_dir == "BAJISTA":
        cruces["MACRO_REFUGIOS"] = "✅ RISK-ON MÁXIMO — TLT+GLD ambos BAJ = full size alcistas"
    elif tlt_dir == "BAJISTA" and gld_dir == "ALCISTA":
        cruces["MACRO_REFUGIOS"] = "⚠️ INFLACIÓN/USD DÉBIL — GLD ALC con máxima convicción"
    elif tlt_dir == "ALCISTA" and gld_dir == "BAJISTA":
        cruces["MACRO_REFUGIOS"] = "⚠️ HUIDA A USD — bajistas USD-sensibles"
    else:
        cruces["MACRO_REFUGIOS"] = "NEUTRAL — refugios en ZM, contexto indeciso"
    return cruces


def finalize_dashboard_output(output_data: dict) -> None:
    """Move skip tickers, compute cruces. No EC evaluation."""
    output_data.setdefault("skips", {})
    tickers = output_data.setdefault("tickers", {})
    for t in list(tickers.keys()):
        td = tickers[t]
        if td.get("skip"):
            output_data["skips"][t] = td.get("skip_reason", "Skip")
    output_data["cruces"] = compute_cruces(output_data.get("tickers", {}))
