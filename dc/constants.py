"""Constantes del sistema BB Premarket."""
import pytz

TICKERS = ["NVDA", "QQQ", "SPY", "IWM", "DIA", "GLD", "TLT", "TSLA", "AMD", "AAPL", "META", "MSFT", "GOOGL", "AMZN", "COIN", "PLTR", "AVGO"]
TICKERS_MACRO = ["QQQ", "SPY", "DIA"]

TIER1 = ["GLD", "QQQ", "META", "NVDA", "TSLA", "COIN", "PLTR"]
TIER2 = ["AMD", "SPY", "MSFT", "AAPL", "AMZN", "DIA", "TLT", "IWM", "AVGO"]
CONFIRMADORES = ["GOOGL"]
MACRO_SEMAFORO = ["TLT", "GLD", "IWM", "QQQ", "DIA"]

FAMILIAS = {
    "SEMIS": ["NVDA", "AMD"],
    "ADS": ["META", "GOOGL"],
    "CLOUD": ["MSFT", "AMZN"],
    "BETA": ["TSLA", "IWM"],
    "INDICES": ["QQQ", "DIA"],
    "SEMIS_NEW": ["AVGO", "PLTR"],
}

TIMEZONE = pytz.timezone("America/New_York")
TF_LIST = ["1m", "5m", "15m", "30m", "1h", "1d"]
OPEN_930_TF_LIST = ["1m", "5m", "15m", "30m", "1h", "1d"]
UTC = pytz.UTC
N_VELAS_BB = 20

ZM_THRESHOLD_PCT = 0.333 * 0.333
REBOTE_UMBRAL_PCT: float = 0.33

PREV_DAY_RULES: dict[str, dict[str, float | str]] = {
    "DEFAULT": {
        "alc_skip_bajo": -3.0,
        "alc_reducir_bajo": -3.0,
        "alc_size2_bajo": 2.0,
        "baj_skip_positivo": 0.0,
        "baj_size2_alto": -3.0,
        "baj_reducir_positivo": 0.0,
    },
    "META": {
        "alc_skip_bajo": -999.0,
        "alc_reducir_bajo": -3.0,
        "alc_size2_bajo": 2.0,
        "baj_skip_positivo": 0.0,
        "baj_size2_alto": -3.0,
        "baj_reducir_positivo": 0.0,
    },
    "COIN": {
        "alc_skip_bajo": -3.0,
        "alc_reducir_bajo": -3.0,
        "alc_size2_bajo": 5.0,
        "baj_skip_positivo": 0.0,
        "baj_size2_alto": -3.0,
        "baj_reducir_positivo": 0.0,
    },
    "PLTR": {
        "alc_skip_bajo": 0.0,
        "alc_reducir_bajo": 0.0,
        "alc_size2_bajo": 5.0,
        "baj_skip_positivo": 2.0,
        "baj_size2_alto": -3.0,
        "baj_reducir_positivo": 0.0,
    },
    "TLT": {
        "alc_skip_bajo": -3.0,
        "alc_reducir_bajo": -3.0,
        "alc_size2_bajo": 0.0,
        "baj_skip_positivo": 0.0,
        "baj_size2_alto": -3.0,
        "baj_reducir_positivo": 0.0,
    },
    "AVGO": {
        "alc_skip_bajo": -3.0,
        "alc_reducir_bajo": -3.0,
        "alc_size2_bajo": 0.0,
        "baj_skip_positivo": 2.0,
        "baj_size2_alto": -3.0,
        "baj_reducir_positivo": 0.0,
    },
}

VELOCIDAD_REGLA: dict[str, tuple[bool, bool, str]] = {
    "QQQ":  (False, False, "QQQ: resistente tardío — no cerrar"),
    "SPY":  (False, False, "SPY ZM tardío 61% — no cerrar"),
    "DIA":  (True,  True,  "DIA >30min = cerrar en INT"),
    "IWM":  (True,  False, "IWM: ALC >30min = 28.2% cerrar / BAJ >30min = 50% NO cerrar"),
    "NVDA": (True,  True,  "NVDA >30min = 36.7% — cerrar en INT"),
    "AMD":  (True,  True,  "AMD >30min = 33.3% — cerrar en INT"),
    "TSLA": (True,  True,  "TSLA >30min = 39.4% — cerrar en INT"),
    "AAPL": (True,  False, "AAPL: ALC fuera ZM >30min = 38.8% cerrar / ZM >30min = 55.2% NO cerrar"),
    "META": (True,  True,  "META >30min = 44.4% ALC / 37.5% BAJ — cerrar"),
    "MSFT": (True,  False, "MSFT: ALC fuera ZM >30min = 27.8% cerrar / BAJ >30min = 35% reducir"),
    "GOOGL":(False, False, "GOOGL >30min = 39.6% ALC reducir / BAJ 34.1% reducir — no cerrar obligatorio"),
    "AMZN": (True,  False, "AMZN: ALC >30min = 33.3% cerrar / BAJ >30min = 46.7% NO cerrar"),
    "GLD":  (True,  True,  "GLD >30min = cerrar en INT"),
    "TLT":  (True,  False, "TLT: ALC >30min = 33.3% cerrar / BAJ >30min = 42.9% reducir"),
    "COIN": (False, False, "COIN ZM >30min = 72.5% MAX — NO cerrar en ninguna dir"),
    "PLTR": (True,  True,  "PLTR >30min = 34.6% — cerrar en INT"),
    "AVGO": (True,  False, "AVGO: ALC fuera ZM >30min = 32.9% cerrar / BAJ = 44.4% reducir"),
}

SEGUNDO_TOQUE_REGLA: dict[str, tuple[bool, bool, str]] = {
    "TSLA": (False, False, "TSLA: 2do toque ALC=70.3% BAJ=70.8% — MANTENER"),
    "META": (False, False, "META: 2do toque ALC=59.6% BAJ=51.7% — REDUCIR no salir"),
    "COIN": (False, False, "COIN: 2do toque ALC=50.8% BAJ=42.3% — REDUCIR"),
    "MSFT": (False, False, "MSFT: 2do toque ALC=47.7% BAJ=53.2% — REDUCIR"),
    "QQQ":  (False, False, "QQQ: 2do toque ~60% — reducir no salir"),
    "SPY":  (False, False, "SPY: 2do toque BAJ=75.5% — mantener BAJ / reducir ALC"),
    "DIA":  (False, False, "DIA: 2do toque BAJ=67.3% — mantener BAJ"),
    "AVGO": (False, False, "AVGO: 2do toque ALC=41.5% BAJ=44.3% — REDUCIR"),
    "GLD":  (False, False, "GLD: 2do toque ~54% — reducir"),
    "AMZN": (True,  False, "AMZN: 2do toque ALC=31.4% SALIR / BAJ=42.6% REDUCIR"),
    "NVDA": (True,  True,  "NVDA: 2do toque ALC=30.6% BAJ=38% — SALIR ambos"),
    "AMD":  (False, True,  "AMD: 2do toque ALC=43.9% REDUCIR / BAJ=33.9% SALIR"),
    "PLTR": (False, True,  "PLTR: 2do toque ALC=44.6% REDUCIR / BAJ=40.4% SALIR"),
    "GOOGL":(True,  True,  "GOOGL: 2do toque ALC=34.7% BAJ=33% — SALIR ambos"),
    "TLT":  (True,  True,  "TLT: 2do toque ALC=38.9% BAJ=29.9% — SALIR ambos"),
    "IWM":  (True,  True,  "IWM: 2do toque ALC=20.7% BAJ=28.5% — SALIR"),
    "AAPL": (True,  True,  "AAPL: 2do toque ALC=36.3% BAJ=34.9% — SALIR"),
}

_OPEN_ZONE_SKIP_RULES: list[tuple[list[str], list[str], str, str | None, str]] = [
    (
        ["AAPL"],
        ["normal_t1"],
        "cualquier",
        "BAJISTA+GAP_DOWN",
        "BAJ GAP DOWN t1 AAPL — playbook: Contra>52% — SKIP",
    ),
    (
        ["META"],
        ["normal_t1"],
        "escalo",
        "BAJISTA",
        "escalo BAJ t1 META = 0% INT — SKIP absoluto",
    ),
    (
        ["MSFT", "AMZN", "AVGO", "PLTR"],
        ["normal_t1"],
        "cualquier",
        "BAJISTA+GAP_DOWN",
        "BAJ GAP DOWN t1 — Contra>50% — SKIP",
    ),
]

_OPEN_ZONE_WARN_RULES: list[tuple[list[str], list[str], str, str | None, str]] = [
    (
        ["GOOGL"],
        ["normal_t3"],
        "igual",
        None,
        "igual en t3 GOOGL = ~25% MAX — target solo INT",
    ),
    (
        ["TLT"],
        ["normal_t2"],
        "cualquier",
        "BAJISTA+GAP_DOWN",
        "BAJ GAP DOWN t2 TLT — solo INT (MAX ~21%)",
    ),
]

ZONE_SIZE_HINT: dict[tuple[str, str | None], str] = {
    ("doble_dir_zone", None): "ZM — esperar INT, SIZE x2",
    ("normal_t1", "No"): "t1 sin bp — SIZE x0.5-x1",
    ("normal_t1", "Si"): "t1 tocó BP — SKIP/reducir",
    ("normal_t2", "No"): "t2 sin bp — SIZE x1-x2",
    ("normal_t2", "Si"): "t2 tocó BP — SKIP/reducir",
    ("normal_t3", "No"): "t3 sin bp — SIZE x2",
    ("normal_t3", "Si"): "t3 tocó BP — SKIP",
    ("ext_int_max", None): "Abrió pasado INT — SIZE x1-x2, target MAX",
}

ALC_T3_SOLO_INT_TICKERS = frozenset({"AVGO", "AMZN"})

CAUTION_TEXTS = {
    "BBT 1M": "CAUTION: Price outside of the BBT 1M\nSlightly overbought on 1-minute candles.",
    "BBB 1M": "CAUTION: Price outside of the BBB 1M\nSlightly oversold on 1-minute candles.",
    "BBT 5M": "CAUTION: Price outside of the BBT 5M\nOverbought on 5-minute candles.",
    "BBB 5M": "CAUTION: Price outside of the BBB 5M\nOversold on 5-minute candles, expect a low correction.",
    "BBT 30M": "CAUTION: Price outside of the BBT 30M\nOverbought on 30-minute candles.",
    "BBB 30M": "CAUTION: Price outside of the BBB 30M\nOversold on 30-minute candles, expect a low correction.",
    "BBT 1H": "CAUTION: Price outside of the BBT 1H\nOverbought on 1-hour candles.",
    "BBB 1H": "CAUTION: Price outside of the BBB 1H\nOversold on 1-hour candles, expect a low correction.",
}
