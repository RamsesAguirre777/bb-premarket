# 📈 BB Premarket

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Alpaca Markets](https://img.shields.io/badge/data-Alpaca%20Markets-yellow.svg)](https://alpaca.markets/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: Active](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

> **Premarket analysis pipeline for 17 high-volume tickers. Calculates BP, INT/MAX targets, BB flags, 3/9 signals and open direction — across 3 time snapshots: 9:15, 9:28 and 9:30 ET.**

---

## 🌟 What It Does

- **3 chronological modes** — complete snapshot at each key moment before and during market open
- **BB Flags per timeframe** — detects BBT/BBB across 1m/5m/15m/30m/1h/1d using BB(20,2) EWM of previous day closes
- **BB Shift at open** — compares premarket flags vs real 9:30 flags (`equal / escalated / disappeared / new / type_change`)
- **Automatic direction** — `BULLISH / BEARISH / DEAD_ZONE` based on open vs BP (±$0.25 threshold)
- **Precise targets** — INT = BP ± (range_3d × 0.33) | MAX = BP ± (range_3d × 0.66)
- **3 outputs per mode** — structured JSON + AI-ready compressed context + analysis dashboard

---

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/RamsesAguirre777/bb-premarket.git
cd bb-premarket
pip install -r requirements.txt
```

### 2. Configure Credentials

```bash
cp .env.example .env
# Edit .env with your Alpaca API keys
```

```env
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
```

### 3. Run

```bash
# All tickers — run each mode in its time window
python -m dc.main premarket_9_15   # ~9:15 AM ET
python -m dc.main premarket_9_28   # ~9:28 AM ET
python -m dc.main open_930         # ~9:30 AM ET

# Single ticker
python -m dc.main open_930 --ticker NVDA

# Specific date (for replay)
python -m dc.main premarket_9_28 --date 2026-05-08
```

---

## 🛠️ The 3 Modes

### 📊 `premarket_9_15` — First snapshot of the day

Initial snapshot at 9:15 AM ET. Establishes the base BP and first targets with the data available at that time.

```bash
python -m dc.main premarket_9_15
# Output: outputs/premarket_9_15_YYYY-MM-DD.json
```

### 📊 `premarket_9_28` — Final pre-open snapshot

Last snapshot before market open. Refines BP with more candles available, recalculates targets and signals. **This is the most important mode** — it serves as the base for `open_930`.

```bash
python -m dc.main premarket_9_28
# Output: outputs/premarket_9_28_YYYY-MM-DD.json
```

### 🔔 `open_930` — At market open

Reads the real open price via Alpaca snapshot, determines direction vs BP, computes `bb_flags_real_930` by comparing against premarket flags, and generates `bb_shift`.

```bash
python -m dc.main open_930
# Output: outputs/open_930_YYYY-MM-DD.json
```

---

## 🎯 Key Concepts

### Break Point (BP)
Average of EMA3 and EMA9 computed across all available timeframes, frozen at each mode's cutoff time.

```
bp = avg(ema3_all_tfs + ema9_all_tfs)
```

### BB Flags
Detects whether price is outside the Bollinger Bands (20 periods, 2σ, EWM) calculated from the previous day's closes up to 16:00 ET.

```
BBT {TF}  →  price > upper band
BBB {TF}  →  price < lower band
```

Example: `BBT 1M BBT 5M BBB 1H` → price in overbought zone on 1m/5m and oversold on 1h.

### BB Shift
Compares premarket flags against the real flags at the 9:30 open.

| Value | Meaning |
|---|---|
| `igual` | Same flags — no change |
| `escalo` | More flags at open — amplified signal |
| `desaparecio` | Fewer flags — pressure released |
| `nuevo` | No flags in PM → flags appear at open |
| `cambio_tipo` | Same TF but BBT↔BBB flipped |

### Direction

```
open > BP + $0.25  →  BULLISH
open < BP - $0.25  →  BEARISH
|open - BP| ≤ $0.25  →  DEAD ZONE
```

### Targets

```
range_3d  →  BB(20,2) EWM width on 1H pre-cutoff (fallback: avg H-L of last 3 daily bars)
INT_POS   =  BP + (range_3d × 0.33)
INT_NEG   =  BP - (range_3d × 0.33)
MAX_POS   =  BP + (range_3d × 0.66)
MAX_NEG   =  BP - (range_3d × 0.66)
```

---

## 📁 Outputs

Each mode writes 3 files to `outputs/`:

| File | Use |
|---|---|
| `{mode}_YYYY-MM-DD.json` | Full structured data — useful for scripts and backtesting |
| `context_compressed_YYYY-MM-DD_{mode}.txt` | Compressed summary to paste as AI context |
| `ai_dashboard_prompt_YYYY-MM-DD_{mode}.txt` | Narrative dashboard for AI analysis (Claude, GPT, etc.) |

### Sample ticker data (`premarket_9_28`)

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

17 tickers organized by market family:

| Family | Tickers |
|---|---|
| **Index ETFs** | QQQ · SPY · IWM · DIA |
| **Safe Haven** | TLT · GLD |
| **Semiconductors** | NVDA · AMD · AVGO |
| **Mega-cap Tech** | META · MSFT · GOOGL · AMZN · AAPL |
| **Momentum** | TSLA · COIN · PLTR |

---

## 🏗️ Architecture

```
bb-premarket/
├── dc/
│   ├── constants.py        — tickers, families, TIER1/TIER2, timezone
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
│       ├── mode_9_15.py    — 9:15 ET snapshot
│       ├── mode_9_28.py    — 9:28 ET snapshot (base for open_930)
│       └── mode_930.py     — real open: bb_flags_real_930 + bb_shift
│                             (includes _rth_mask_vectorized, _build_tfs_rth,
│                              _compute_caution_real_930 reimplemented)
└── outputs/                — auto-generated (gitignored)
```

---

## 🔒 Security

- **No persistent data** — everything processed in real-time from Alpaca
- **API keys in `.env` only** — never hardcoded
- **`outputs/` in `.gitignore`** — your trading data stays local

---

## 📄 License

MIT — free to use, modify and distribute.

---

<div align="center">
  <p>Built for traders who need clear signals before the open.</p>
  <a href="https://github.com/RamsesAguirre777">GitHub</a>
</div>
