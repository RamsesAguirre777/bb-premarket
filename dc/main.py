from __future__ import annotations
import argparse
import asyncio
import logging
import sys
from datetime import datetime

from dc.constants import TICKERS, TIMEZONE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

MODES = ["premarket_9_15", "premarket_9_28", "open_930"]


async def main() -> None:
    parser = argparse.ArgumentParser(description="BB Premarket pipeline")
    parser.add_argument("mode", choices=MODES, help="Pipeline mode to run")
    parser.add_argument(
        "--ticker",
        metavar="TICKER",
        help="Run for a single ticker (default: all)",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Date string for output filenames (default: today)",
    )
    args = parser.parse_args()

    date_str = args.date or datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    tickers_to_run = [args.ticker.upper()] if args.ticker else list(TICKERS)

    logger.info("mode=%s | date=%s | tickers=%s", args.mode, date_str, tickers_to_run)

    if args.mode == "premarket_9_15":
        from dc.modes.mode_9_15 import run_mode_9_15
        output_data: dict = {"tickers": {}, "macro": {}, "tickers_order": tickers_to_run}
        await run_mode_9_15(tickers_to_run, date_str, output_data)

    elif args.mode == "premarket_9_28":
        from dc.modes.mode_9_28 import run_mode_9_28
        output_data = {"tickers": {}, "macro": {}, "tickers_order": tickers_to_run}
        await run_mode_9_28(tickers_to_run, date_str, output_data)

    elif args.mode == "open_930":
        from dc.modes.mode_930 import run_mode_930
        await run_mode_930(tickers_to_run, date_str)


if __name__ == "__main__":
    asyncio.run(main())
