# BB Premarket

Pipeline de análisis premarket para 17 tickers usando Bollinger Bands (BB) y niveles de ruptura (BP).

## Modos

| Modo | Hora ET | Descripción |
|---|---|---|
| `premarket_9_15` | 9:15 AM | Análisis inicial premarket |
| `premarket_9_28` | 9:28 AM | Análisis final antes del open |
| `open_930` | 9:30 AM | Apertura — calcula `bb_flags_real_930` y `bb_shift` |

## Tickers

```
NVDA QQQ SPY IWM DIA GLD TLT TSLA AMD AAPL META MSFT GOOGL AMZN COIN PLTR AVGO
```

## Instalación

```bash
pip install -r requirements.txt
cp .env.example .env
# editar .env con tus keys de Alpaca
```

## Uso

```bash
# Todos los tickers
python -m dc.main premarket_9_15
python -m dc.main premarket_9_28
python -m dc.main open_930

# Ticker individual
python -m dc.main open_930 --ticker NVDA

# Fecha específica (default: hoy)
python -m dc.main premarket_9_28 --date 2026-05-08
```

## Outputs

Cada modo escribe en `outputs/`:

- `premarket_9_28_YYYY-MM-DD.json` — datos completos
- `context_compressed_YYYY-MM-DD_premarket_9_28.txt` — resumen comprimido para contexto AI
- `ai_dashboard_prompt_YYYY-MM-DD_premarket_9_28.txt` — dashboard estructurado para análisis

## Variables de entorno

```env
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
```

## Estructura

```
dc/
├── constants.py        — tickers, familias, zonas horarias
├── data_clients.py     — Alpaca API, BPCalculator, TargetsCalculator, SkipFilter
├── indicators.py       — BB flags, badge_long, signals_3_9, cruces, zonas open
├── main.py             — CLI entry point
├── outputs.py          — escritura JSON + context_compressed + ai_dashboard
├── premium_detector.py — helpers bb_flags, is_directo, get_triple
├── utils.py            — bar helpers, compute_bb_from_closes (EWM)
└── modes/
    ├── mode_9_15.py
    ├── mode_9_28.py
    └── mode_930.py     — incluye bb_flags_real_930 y bb_shift
```

## Conceptos clave

- **BP (Break Point):** promedio EMA3/EMA9 de todos los TFs, congelado al cutoff
- **bb_flags:** flags BBT/BBB por TF vs BB(20,2) EWM de cierres del día anterior
- **bb_shift:** comparación premarket vs 9:30 → `igual / escalo / desaparecio / nuevo / cambio_tipo`
- **direction:** `ALCISTA` (open > BP+$0.25) / `BAJISTA` (open < BP-$0.25) / `ZONA_MUERTA`
- **INT:** BP ± (range_3d × 0.33) | **MAX:** BP ± (range_3d × 0.66)
