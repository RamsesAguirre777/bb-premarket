from __future__ import annotations
import re
import logging

from dc.constants import (
    ZONE_SIZE_HINT,
    ALC_T3_SOLO_INT_TICKERS,
    _OPEN_ZONE_SKIP_RULES,
    _OPEN_ZONE_WARN_RULES,
)
from dc.utils import _get_igual_baj_rate

logger = logging.getLogger(__name__)


class PremiumDetector:

    @staticmethod
    def _signals_str(ticker_data: dict) -> str:
        return ticker_data.get("signals_3_9") or ticker_data.get("signals", "")

    @staticmethod
    def is_directo(ticker_data: dict) -> bool:
        badge = ticker_data.get("badge_long", 50)
        direction = ticker_data.get("direction", "ZONA_MUERTA")
        if direction == "ALCISTA" and badge >= 62:
            return True
        if direction == "BAJISTA" and badge <= 38:
            return True
        return False

    @staticmethod
    def get_triple(ticker_data: dict) -> str:
        signals = PremiumDetector._signals_str(ticker_data)
        ups = signals.count("up")
        downs = signals.count("down")
        if ups >= 3:
            return "TRIPLE_UP"
        if downs >= 3:
            return "TRIPLE_DOWN"
        if ups == 0 and downs >= 2:
            return "DOUBLE_DOWN"
        if downs == 0 and ups >= 2:
            return "DOUBLE_UP"
        return "NEUTRO"

    @staticmethod
    def get_n_caution(ticker_data: dict) -> int:
        bb_flags = ticker_data.get("bb_flags", "Sin caution")
        if bb_flags in ("Sin caution", "PENDIENTE"):
            return 0
        return bb_flags.count("BBT") + bb_flags.count("BBB")


def _bb_flags_short(full_note: str, max_len: int = 40) -> str:
    """Compact labels like BBT 1H BBB 5M for tables."""
    if not full_note or full_note.strip() == "Sin caution":
        return "Sin caution"
    found = re.findall(r"(BBT|BBB)\s+(\d+[MH])", full_note)
    if found:
        return " ".join(f"{a} {b}" for a, b in found)
    one = full_note.replace("\n", " ").strip()
    return one if len(one) <= max_len else one[: max_len - 3] + "..."
