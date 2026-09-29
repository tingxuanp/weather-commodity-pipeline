"""
run_pipeline.py — Orchestrates the full weather → signal pipeline.

Usage:
    python run_pipeline.py              # full run, all exports
    python run_pipeline.py --dry-run    # score only, no exports
    python run_pipeline.py --lookback 14
"""

import argparse
import logging
import sys
import os
import time
from datetime import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.weather_fetcher import fetch_all_regions_sync
from signals.anomaly_scorer import run_scoring
from signals.exporter import export_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("pipeline.runner")


def run(lookback_days: int = 30, dry_run: bool = False, export_dir: str = "data") -> dict:
    """
    Full pipeline execution.
    Returns dict with run summary.
    """
    start = time.time()
    logger.info("=" * 60)
    logger.info("WEATHER-COMMODITY SIGNAL PIPELINE — RUN STARTING")
    logger.info(f"Lookback: {lookback_days}d | Dry run: {dry_run}")
    logger.info("=" * 60)

    # ── Step 1: Fetch weather data ────────────────────────────────────────
    logger.info("STEP 1/3 — Fetching weather data from Open-Meteo…")
    t0 = time.time()
    weather_data = fetch_all_regions_sync(lookback_days=lookback_days)
    fetch_elapsed = round(time.time() - t0, 2)
    ok_count = sum(1 for rw in weather_data.values() if rw.fetch_ok)
    logger.info(f"  Fetch complete in {fetch_elapsed}s — {ok_count}/{len(weather_data)} regions OK")

    # ── Step 2: Score anomalies ───────────────────────────────────────────
    logger.info("STEP 2/3 — Scoring weather anomalies and generating signals…")
    t1 = time.time()
    output = run_scoring(weather_data)
    score_elapsed = round(time.time() - t1, 2)
    logger.info(f"  Scoring complete in {score_elapsed}s")

    # ── Step 3: Export ────────────────────────────────────────────────────
    exports = {}
    if not dry_run:
        logger.info("STEP 3/3 — Exporting data…")
        t2 = time.time()
        exports = export_all(output, export_dir=export_dir)
        export_elapsed = round(time.time() - t2, 2)
        logger.info(f"  Exports complete in {export_elapsed}s")
    else:
        logger.info("STEP 3/3 — Skipped (dry run)")

    total_elapsed = round(time.time() - start, 2)

    # ── Summary ───────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Run ID       : {output.run_id}")
    logger.info(f"  Total time   : {total_elapsed}s")
    logger.info(f"  Data coverage: {output.pipeline_health['fetch_success_rate']*100:.0f}%")
    logger.info("")
    logger.info("  COMMODITY SIGNALS:")
    for ticker, sig in output.commodity_signals.items():
        bar_len = int(abs(sig.signal_score) / 5)
        bar = ("▲" if sig.signal_score < 0 else "▼") * bar_len
        logger.info(
            f"    {ticker:4s}  {sig.signal_direction:7s}  {sig.signal_score:+6.1f}  "
            f"[{sig.confidence:6s}]  {bar}"
        )
    logger.info("=" * 60)

    return {
        "run_id": output.run_id,
        "total_elapsed_s": total_elapsed,
        "pipeline_health": output.pipeline_health,
        "exports": exports,
        "output": output,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Weather-Commodity Alternative Data Pipeline"
    )
    parser.add_argument(
        "--lookback", type=int, default=30,
        help="Days of historical weather to fetch (default: 30)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skip file exports"
    )
    parser.add_argument(
        "--export-dir", default="data",
        help="Directory for output files (default: data/)"
    )
    args = parser.parse_args()

    result = run(
        lookback_days=args.lookback,
        dry_run=args.dry_run,
        export_dir=args.export_dir,
    )

    if result["pipeline_health"]["fetch_success_rate"] < 0.5:
        logger.error("Pipeline completed with low data coverage — review fetch errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
