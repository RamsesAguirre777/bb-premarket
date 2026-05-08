from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path

from dc.constants import TICKERS, TICKERS_MACRO, TIMEZONE, FAMILIAS
from dc.premium_detector import _bb_flags_short
from dc.indicators import _gestion_open_930_line

logger = logging.getLogger(__name__)


def _ensure_outputs_dir() -> None:
    Path("outputs").mkdir(parents=True, exist_ok=True)


def _signals_display(ticker_data: dict) -> str:
    return ticker_data.get("signals_3_9") or ticker_data.get("signals", "")


def _format_context_compressed_body(data: dict, mode: str) -> str:
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    time_label = {
        "premarket_9_15": "9:15 AM",
        "premarket_9_28": "9:28 AM",
        "open_930": "9:30 AM",
    }.get(mode, "9:28 AM")
    tickers_line = data.get("tickers_order") or TICKERS
    parts: list[str] = []
    parts.append(f"═══ BB PREMARKET — {today} {time_label} ═══\n")
    parts.append("MACRO: ")
    macro = data.get("macro") or {}
    parts.append(
        " | ".join(
            f"{ticker}={macro.get(ticker, {}).get('price', 0)} "
            f"({float(macro.get(ticker, {}).get('change', 0)):.2f}%)"
            for ticker in TICKERS_MACRO
        )
        + "\n"
    )
    parts.append("Por ticker (excluir SKIPs):\n")
    for ticker in tickers_line:
        if ticker in data["tickers"] and not data["tickers"][ticker].get("skip"):
            td = data["tickers"][ticker]
            sig = _signals_display(td)
            line = (
                f"{ticker}: BP={td['bp']:.2f} | "
                f"INT±{td['int_dist']:.2f} | "
                f"MAX±{td['max_dist']:.2f} | "
                f"GAP={td['gap_type']} {td['gap_pct']:.2f}% | "
                f"prev_day={td['prev_day_change']:.2f}% | "
                f"signals={sig} | "
                f"badge={td['badge_long']}% | "
                f"bb_flags={_bb_flags_short(td.get('bb_flags', 'Sin caution'))}"
                f" | pm={td.get('rango_pm', {}).get('label', '?')}({int(td.get('rango_pm', {}).get('pct', 0.5)*100)}%)"
                f" | prev={td.get('rango_prev_day', {}).get('label', '?')}({int(td.get('rango_prev_day', {}).get('pct', 0.5)*100)}%)"
            )
            if "dist" in td and "direction" in td:
                line += f" | dir={td['direction']} dist={td['dist']:.2f}"
            parts.append(line + "\n")
    parts.append("SKIP ALERTS:\n")
    for ticker in tickers_line:
        if ticker in data["tickers"] and data["tickers"][ticker].get("skip"):
            parts.append(f"{ticker}: {data['tickers'][ticker]['skip_reason']}\n")
    if mode == "open_930":
        parts.append("\nOPEN 9:30:\n")
        for ticker in tickers_line:
            if ticker in data["tickers"] and "open_930" in data["tickers"][ticker]:
                td = data["tickers"][ticker]
                direction = td["direction"]
                dist = td["dist"]
                int_pos = td.get("int_pos")
                int_neg = td.get("int_neg")
                max_pos = td.get("max_pos")
                max_neg = td.get("max_neg")
                open_p = td.get("open_930")
                open_z = td.get("open_zone")
                opct = td.get("open_pct_en_rango")
                pct_s = f"{int(round(100 * float(opct)))}%" if opct is not None else "—"
                line_head = f"{ticker}: {direction}"
                if open_z:
                    line_head += f" | ZONA: {open_z} ({pct_s})"
                line_head += f" | dist={dist:.2f}"
                bb_shift = td.get("bb_shift")
                if bb_shift:
                    shift_emoji = {
                        "igual": "🟰",
                        "nuevo": "🆕",
                        "escalo": "📈" if td.get("direction") == "ALCISTA" else "📉",
                        "desaparecio": "💨",
                        "cambio_tipo": "🔄",
                    }.get(bb_shift, "❓")
                    line_head += f" | shift={shift_emoji}{bb_shift}"
                parts.append(line_head + "\n")
                if direction == "BAJISTA" and int_neg is not None and open_p is not None:
                    rec_i = abs(float(open_p) - float(int_neg))
                    tail = f"   → INT_NEG={float(int_neg):.2f} (recorrido: ${rec_i:.2f})"
                    if max_neg is not None:
                        tail += f" | MAX_NEG={float(max_neg):.2f}"
                    if open_z == "ext_int_max":
                        tail += " ← PRECIO YA BAJO INT"
                    parts.append(tail + "\n")
                elif direction == "ALCISTA" and int_pos is not None and open_p is not None:
                    rec_i = abs(float(int_pos) - float(open_p))
                    tail = f"   → INT_POS={float(int_pos):.2f} (recorrido: ${rec_i:.2f})"
                    if max_pos is not None:
                        tail += f" | MAX_POS={float(max_pos):.2f}"
                    if open_z == "ext_int_max":
                        tail += " ← PRECIO YA SUPERÓ INT"
                    parts.append(tail + "\n")
                elif int_pos is not None and int_neg is not None:
                    mp = f"{float(max_pos):.2f}" if max_pos is not None else "—"
                    mn = f"{float(max_neg):.2f}" if max_neg is not None else "—"
                    parts.append(
                        f"   → INT_POS={float(int_pos):.2f} INT_NEG={float(int_neg):.2f} "
                        f"| MAX_POS={mp} MAX_NEG={mn}\n"
                    )
                gest = _gestion_open_930_line(ticker, td, direction)
                if gest:
                    parts.append(f"   ⚠ GESTIÓN: {gest}\n")
    return "".join(parts)


def write_json(data: dict, filename: str) -> None:
    _ensure_outputs_dir()
    path = Path("outputs") / filename
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing.setdefault("tickers", {}).update(data.get("tickers", {}))
            existing.setdefault("skips", {}).update(data.get("skips", {}))
            for k in ("macro", "tickers_order", "cruces"):
                if k in data:
                    existing[k] = data[k]
            data = existing
        except Exception:
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def write_context_compressed(data: dict, date_str: str, modo: str) -> None:
    _ensure_outputs_dir()
    text = _format_context_compressed_body(data, modo)
    path = Path("outputs") / f"context_compressed_{date_str}_{modo}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_ai_dashboard(data: dict, date_str: str, modo: str) -> None:
    _ensure_outputs_dir()
    time_label = {
        "premarket_9_15": "9:15 AM",
        "premarket_9_28": "9:28 AM",
        "open_930": "9:30 AM",
    }.get(modo, "9:28 AM")

    tickers_line = data.get("tickers_order") or TICKERS
    tickers_data = data.get("tickers", {})
    macro = data.get("macro", {})
    parts: list[str] = []

    parts.append(f"{'━'*50}\n")
    parts.append(f"BB PREMARKET — {date_str} {time_label}\n")
    parts.append(f"{'━'*50}\n\n")

    parts.append("MACRO:\n")
    for t in TICKERS_MACRO:
        if t in macro:
            chg = macro[t].get("change", 0) or 0
            price = macro[t].get("price", 0) or 0
            signo = "+" if chg >= 0 else ""
            parts.append(f"  {t:<5} {price:.2f}  ({signo}{chg:.2f}%)\n")
    parts.append("  [Agregar aquí: sentimiento macro + futuros YM/NQ/ES si disponibles]\n\n")

    # ── Separar tickers ────────────────────────────────────────────
    activos: list[str] = []
    sin_oportunidad: list[tuple[str, str]] = []

    for ticker in tickers_line:
        td = tickers_data.get(ticker)
        if td is None:
            razon = data.get("skips", {}).get(ticker, "sin datos")
            sin_oportunidad.append((ticker, str(razon)))
            continue
        if td.get("skip"):
            sin_oportunidad.append((ticker, td.get("skip_reason", "skip")))
        else:
            activos.append(ticker)

    # ── TICKERS ACTIVOS ────────────────────────────────────────────
    if activos:
        parts.append("TICKERS ACTIVOS:\n")
        parts.append(f"{'─'*50}\n")
        for ticker in activos:
            td = tickers_data.get(ticker, {})
            direction = td.get("direction", "") or ""
            bb_shift = td.get("bb_shift")
            open_930 = td.get("open_930")
            bp = td.get("bp", 0) or 0
            int_pos = td.get("int_pos", 0) or 0
            int_neg = td.get("int_neg", 0) or 0
            max_pos = td.get("max_pos", 0) or 0
            max_neg = td.get("max_neg", 0) or 0
            n_flags = (td.get("bb_flags", "") or "").count("BBT") + (td.get("bb_flags", "") or "").count("BBB")
            signals = td.get("signals_3_9", "") or ""
            gap_type = td.get("gap_type", "") or ""
            gap_pct = td.get("gap_pct", 0) or 0
            prev_day = td.get("prev_day_change", 0) or 0

            parts.append(f"\n━━━ {ticker} {'━'*(20-len(ticker))}\n")

            if modo == "open_930":
                oz = td.get("open_zone")
                opct = td.get("open_pct_en_rango")
                ru = td.get("rebote_umbral")
                if oz is not None:
                    pct_d = int(round(100 * float(opct))) if opct is not None else 0
                    ru_s = f"${float(ru):.2f}" if ru is not None else "—"
                    parts.append(f"  {direction} | ZONA: {oz} ({pct_d}%) | umbral_rebote={ru_s}\n")
                gv = _gestion_open_930_line(ticker, td, direction)
                if gv:
                    parts.append(f"  REGLAS VIVO: {gv}\n")

            if direction == "ZONA_MUERTA":
                open_ref = open_930 if open_930 else bp
                parts.append("ZONA NEUTRA al abrir — espera el primer movimiento\n")
                parts.append(f"  Si BAJA del BP (${bp:.2f}) → SHORT\n")
                parts.append(f"    Objetivo 1: ${int_neg:.2f}  |  Objetivo 2 (MAX): ${max_neg:.2f}\n")
                parts.append(f"    Recorrido:  ${abs(int_neg - open_ref):.2f} al obj1\n")
                parts.append(f"  Si SUBE del BP (${bp:.2f}) → LONG\n")
                parts.append(f"    Objetivo 1: ${int_pos:.2f}  |  Objetivo 2 (MAX): ${max_pos:.2f}\n")
                parts.append(f"    Recorrido:  ${abs(int_pos - open_ref):.2f} al obj1\n")
            elif direction == "ALCISTA":
                open_ref = open_930 if open_930 else bp
                parts.append("LONG (comprar)\n")
                parts.append(f"  Objetivo 1: ${int_pos:.2f}  |  Objetivo 2 (MAX): ${max_pos:.2f}\n")
                parts.append(f"  Recorrido:  ${abs(int_pos - open_ref):.2f} al obj1 / ${abs(max_pos - open_ref):.2f} al obj2\n")
            elif direction == "BAJISTA":
                open_ref = open_930 if open_930 else bp
                parts.append("SHORT (vender)\n")
                parts.append(f"  Objetivo 1: ${int_neg:.2f}  |  Objetivo 2 (MAX): ${max_neg:.2f}\n")
                parts.append(f"  Recorrido:  ${abs(int_neg - open_ref):.2f} al obj1 / ${abs(max_neg - open_ref):.2f} al obj2\n")

            sig_parts = []
            ups = signals.count("up")
            downs = signals.count("down")
            if ups == 3:
                sig_parts.append("señales 3/9 todas alcistas")
            elif downs == 3:
                sig_parts.append("señales 3/9 todas bajistas")
            elif ups > downs:
                sig_parts.append("señales 3/9 mayoría alcistas")
            elif downs > ups:
                sig_parts.append("señales 3/9 mayoría bajistas")
            if n_flags == 0:
                sig_parts.append("0 BB flags")
            elif n_flags > 0:
                sig_parts.append(f"{n_flags} BB flag{'s' if n_flags > 1 else ''}: {_bb_flags_short(td.get('bb_flags', ''))}")
            if bb_shift:
                sig_parts.append(f"bb_shift={bb_shift}")
            if sig_parts:
                parts.append(f"  Contexto: {' | '.join(sig_parts)}\n")

            rango_pm = td.get("rango_pm", {})
            rango_prev = td.get("rango_prev_day", {})
            pm_label = rango_pm.get("label", "")
            prev_label = rango_prev.get("label", "")
            pm_pct = int(rango_pm.get("pct", 0.5) * 100)
            prev_pct = int(rango_prev.get("pct", 0.5) * 100)
            if pm_label and pm_label != "sin_datos":
                parts.append(f"  Rango PM: {pm_label} ({pm_pct}%) | Prev day: {prev_label} ({prev_pct}%)\n")

            if gap_type != "FLAT":
                parts.append(f"  GAP: {gap_type} {gap_pct:.2f}% | prev_day: {prev_day:.2f}%\n")
    else:
        parts.append("SIN TICKERS ACTIVOS ESTE MOMENTO\n")

    # ── FAMILIAS / CRUCES ──────────────────────────────────────────
    cruces = data.get("cruces", {})
    cruces_relevantes = {k: v for k, v in cruces.items() if v and "SIN_DATOS" not in v and "NEUTRAL" not in v}
    if cruces_relevantes:
        parts.append(f"\n{'─'*50}\n")
        parts.append("CONTEXTO DE MERCADO:\n")
        for familia, estado in cruces_relevantes.items():
            parts.append(f"  {familia}: {estado}\n")

    # ── SIN OPORTUNIDAD ────────────────────────────────────────────
    if sin_oportunidad:
        parts.append(f"\n{'─'*50}\n")
        parts.append("SKIP / SIN DATOS:\n")
        for ticker, razon in sin_oportunidad:
            parts.append(f"  {ticker}: {razon}\n")

    parts.append(f"\n{'━'*50}\n")

    path = Path("outputs") / f"ai_dashboard_prompt_{date_str}_{modo}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
