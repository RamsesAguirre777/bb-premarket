# 📈 BB Premarket

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Alpaca Markets](https://img.shields.io/badge/data-Alpaca%20Markets-yellow.svg)](https://alpaca.markets/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

> **Pipeline de análisis premarket para 17 tickers de alto volumen. Calcula BP, targets INT/MAX, BB flags, señales 3/9 y dirección al open — todo en 3 snapshots: 9:15, 9:28 y 9:30 ET.**

---

## 🌟 ¿Qué hace?

- **3 modos cronológicos** — snapshot completo en cada momento clave antes y durante el open
- **BB Flags por TF** — detecta BBT/BBB en 1m/5m/15m/30m/1h/1d usando BB(20,2) EWM de cierres del día anterior
- **BB Shift al open** — compara flags premarket vs flags reales a las 9:30 (`igual / escalo / desaparecio / nuevo / cambio_tipo`)
- **Dirección automática** — `ALCISTA / BAJISTA / ZONA_MUERTA` basada en open vs BP (umbral ±$0.25)
- **Targets precisos** — INT = BP ± (range_3d × 0.33) | MAX = BP ± (range_3d × 0.66)
- **3 outputs por modo** — JSON estructurado + context comprimido para AI + dashboard de análisis

---

## 🚀 Quick Start

### 1. Clonar e instalar

```bash
git clone https://github.com/RamsesAguirre777/bb-premarket.git
cd bb-premarket
pip install -r requirements.txt
```

### 2. Configurar credenciales

```bash
cp .env.example .env
# Editar .env con tus API keys de Alpaca
```

```env
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
```

### 3. Correr

```bash
# Todos los tickers — cada modo en su ventana horaria
python -m dc.main premarket_9_15   # ~9:15 AM ET
python -m dc.main premarket_9_28   # ~9:28 AM ET
python -m dc.main open_930         # ~9:30 AM ET

# Ticker individual
python -m dc.main open_930 --ticker NVDA

# Fecha específica (para replay)
python -m dc.main premarket_9_28 --date 2026-05-08
```

---

## 🛠️ Los 3 Modos

### 📊 `premarket_9_15` — Primera foto del día

Snapshot inicial a las 9:15 AM ET. Establece el BP base y los primeros targets con los datos que hay disponibles.

```bash
python -m dc.main premarket_9_15
# Output: outputs/premarket_9_15_YYYY-MM-DD.json
```

### 📊 `premarket_9_28` — Foto definitiva pre-open

Snapshot final antes del open. Refina BP con más velas disponibles, recalcula targets y señales. **Este es el modo más importante** — es la base que usa `open_930`.

```bash
python -m dc.main premarket_9_28
# Output: outputs/premarket_9_28_YYYY-MM-DD.json
```

### 🔔 `open_930` — Al abrir el mercado

Lee el precio de apertura real vía Alpaca snapshot, determina dirección vs BP, calcula `bb_flags_real_930` comparando con los flags premarket, y genera `bb_shift`.

```bash
python -m dc.main open_930
# Output: outputs/open_930_YYYY-MM-DD.json
```

---

## 🎯 Conceptos Clave

### Break Point (BP)
Promedio de EMA3 y EMA9 calculado sobre todos los timeframes disponibles, congelado al cutoff de cada modo.

```
bp = avg(ema3_all_tfs + ema9_all_tfs)
```

### BB Flags
Detecta si el precio está fuera de las Bandas de Bollinger (20 períodos, 2σ, EWM) calculadas con los cierres del día anterior hasta las 16:00 ET.

```
BBT {TF}  →  precio > banda superior
BBB {TF}  →  precio < banda inferior
```

Ejemplo: `BBT 1M BBT 5M BBB 1H` → precio en zona de sobrecompra en 1m/5m y sobreventa en 1h.

### BB Shift
Compara los flags del premarket contra los flags reales al abrir a las 9:30.

| Valor | Significado |
|---|---|
| `igual` | Mismos flags — sin cambio |
| `escalo` | Más flags al open — señal amplificada |
| `desaparecio` | Menos flags — presión liberada |
| `nuevo` | Sin flags en PM → flags al open |
| `cambio_tipo` | Mismo TF pero BBT↔BBB invertido |

### Dirección

```
open > BP + $0.25  →  ALCISTA
open < BP - $0.25  →  BAJISTA
|open - BP| ≤ $0.25  →  ZONA_MUERTA
```

### Targets

```
range_3d  →  BB(20,2) EWM width en 1H pre-cutoff (fallback: avg H-L últimos 3 días)
INT_POS   =  BP + (range_3d × 0.33)
INT_NEG   =  BP - (range_3d × 0.33)
MAX_POS   =  BP + (range_3d × 0.66)
MAX_NEG   =  BP - (range_3d × 0.66)
```

---

## 📁 Outputs

Cada modo genera 3 archivos en `outputs/`:

| Archivo | Uso |
|---|---|
| `{modo}_YYYY-MM-DD.json` | Datos completos estructurados — útil para scripts y backtesting |
| `context_compressed_YYYY-MM-DD_{modo}.txt` | Resumen comprimido para pegar como contexto a un AI |
| `ai_dashboard_prompt_YYYY-MM-DD_{modo}.txt` | Dashboard narrativo para análisis por AI (Claude, GPT, etc.) |

### Ejemplo de datos por ticker (`premarket_9_28`)

```json
{
  "NVDA": {
    "bp": 138.42,
    "int_pos": 140.18,
    "int_neg": 136.66,
    "max_pos": 141.94,
    "max_neg": 134.90,
    "int_dist": 1.76,
    "max_dist": 3.52,
    "gap_type": "GAP_UP",
    "gap_pct": 1.23,
    "prev_day_change": -0.87,
    "bb_flags": "BBT 1M BBT 5M",
    "badge_long": 72.5,
    "signals_3_9": "up_15m up_30m down_1h",
    "direction": "ALCISTA",
    "dist": 0.58,
    "rango_pm": { "label": "sup_tercio", "pct": 0.82 },
    "rango_prev_day": { "label": "mid", "pct": 0.51 }
  }
}
```

---

## 📋 Tickers

17 tickers cubiertos organizados por familia:

| Familia | Tickers |
|---|---|
| **ETFs Índices** | QQQ · SPY · IWM · DIA |
| **Refugio** | TLT · GLD |
| **Semis** | NVDA · AMD · AVGO |
| **Mega-tech** | META · MSFT · GOOGL · AMZN · AAPL |
| **Momentum** | TSLA · COIN · PLTR |

---

## 🏗️ Arquitectura

```
bb-premarket/
├── dc/
│   ├── constants.py        — tickers, familias, TIER1/TIER2, timezone
│   ├── data_clients.py     — AlpacaHistoricalClient · AlpacaSnapshotClient
│   │                         BPCalculator · TargetsCalculator · SkipFilter
│   ├── indicators.py       — compute_bb_flags · compute_signals_3_9
│   │                         compute_badge_long · compute_open_zone
│   │                         compute_cruces · finalize_dashboard_output
│   ├── premium_detector.py — _bb_flags_short · is_directo · get_triple
│   │                         get_n_caution · PremiumDetector
│   ├── utils.py            — _bars_list_to_mi_dataframe · _filter_bars_before
│   │                         _compute_bb_from_closes (BB EWM)
│   ├── outputs.py          — write_json · write_context_compressed
│   │                         write_ai_dashboard
│   ├── main.py             — CLI entry point
│   └── modes/
│       ├── mode_9_15.py    — snapshot 9:15 ET
│       ├── mode_9_28.py    — snapshot 9:28 ET (base para open_930)
│       └── mode_930.py     — open real: bb_flags_real_930 + bb_shift
│                             (incluye _rth_mask_vectorized, _build_tfs_rth,
│                              _compute_caution_real_930 reimplementados)
└── outputs/                — generado automáticamente (en .gitignore)
```

---

## 🔒 Seguridad

- **Sin datos persistentes** — todo se procesa en tiempo real desde Alpaca
- **API keys solo en `.env`** — nunca en el código
- **outputs/ en `.gitignore`** — tus datos de trading no se suben al repo

---

## 📄 Licencia

MIT — libre para usar, modificar y distribuir.

---

<div align="center">
  <p>Construido para traders que necesitan señales claras antes del open.</p>
  <a href="https://github.com/RamsesAguirre777">GitHub</a>
</div>
