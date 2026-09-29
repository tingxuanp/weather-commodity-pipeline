"""
exporter.py — Export pipeline output to JSON and CSV formats.

Produces:
  - signals_<run_id>.json   Full structured output (for downstream systems)
  - signals_latest.json     Always-current copy (for dashboard polling)
  - signals_<run_id>.csv    Flat CSV for quant consumption
  - region_anomalies_<run_id>.csv  Region-level detail
"""

import json
import csv
import os
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from signals.anomaly_scorer import PipelineOutput, CommoditySignal, RegionAnomaly

logger = logging.getLogger(__name__)


def _signal_to_dict(sig: CommoditySignal) -> dict:
    return {
        "ticker": sig.ticker,
        "name": sig.name,
        "sector": sig.sector,
        "signal_score": sig.signal_score,
        "signal_direction": sig.signal_direction,
        "confidence": sig.confidence,
        "confidence_score": sig.confidence_score,
        "headline": sig.headline,
        "detail_lines": sig.detail_lines,
        "region_contributions": sig.region_contributions,
        "data_coverage": sig.data_coverage,
        "generated_at": sig.generated_at,
    }


def _anomaly_to_dict(ra: RegionAnomaly) -> dict:
    return {
        "region_key": ra.region_key,
        "region_name": ra.region_name,
        "country": ra.country,
        "temp_anomaly_c": ra.temp_anomaly_c,
        "precip_anomaly_pct": ra.precip_anomaly_pct,
        "soil_moisture_zscore": ra.soil_moisture_zscore,
        "composite_score": ra.composite_score,
        "temp_score": ra.temp_score,
        "precip_score": ra.precip_score,
        "moisture_score": ra.moisture_score,
        "critical_month_factor": ra.critical_month_factor,
        "is_critical_month": ra.is_critical_month,
        "observation_days": ra.observation_days,
        "data_quality": ra.data_quality,
    }


def export_json(output: PipelineOutput, export_dir: str = "data") -> str:
    """Write full JSON export. Returns path to written file."""
    Path(export_dir).mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": output.run_id,
        "generated_at": output.generated_at,
        "lookback_days": output.lookback_days,
        "pipeline_health": output.pipeline_health,
        "commodity_signals": {
            ticker: _signal_to_dict(sig)
            for ticker, sig in output.commodity_signals.items()
        },
        "region_anomalies": {
            key: _anomaly_to_dict(ra)
            for key, ra in output.region_anomalies.items()
        },
    }

    # Timestamped file
    fname = f"signals_{output.run_id}.json"
    fpath = os.path.join(export_dir, fname)
    with open(fpath, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"JSON export → {fpath}")

    # Always-latest copy for dashboard
    latest_path = os.path.join(export_dir, "signals_latest.json")
    with open(latest_path, "w") as f:
        json.dump(payload, f, indent=2)
    logger.info(f"Latest JSON → {latest_path}")

    return fpath


def export_signals_csv(output: PipelineOutput, export_dir: str = "data") -> str:
    """Write flat CSV of commodity signals."""
    Path(export_dir).mkdir(parents=True, exist_ok=True)
    fname = f"signals_{output.run_id}.csv"
    fpath = os.path.join(export_dir, fname)

    fieldnames = [
        "run_id", "generated_at", "ticker", "name", "sector",
        "signal_score", "signal_direction", "confidence", "confidence_score",
        "data_coverage", "headline",
    ]

    with open(fpath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ticker, sig in output.commodity_signals.items():
            writer.writerow({
                "run_id": output.run_id,
                "generated_at": output.generated_at,
                "ticker": sig.ticker,
                "name": sig.name,
                "sector": sig.sector,
                "signal_score": sig.signal_score,
                "signal_direction": sig.signal_direction,
                "confidence": sig.confidence,
                "confidence_score": sig.confidence_score,
                "data_coverage": sig.data_coverage,
                "headline": sig.headline,
            })

    logger.info(f"Signals CSV → {fpath}")
    return fpath


def export_regions_csv(output: PipelineOutput, export_dir: str = "data") -> str:
    """Write flat CSV of region-level anomalies."""
    Path(export_dir).mkdir(parents=True, exist_ok=True)
    fname = f"regions_{output.run_id}.csv"
    fpath = os.path.join(export_dir, fname)

    fieldnames = [
        "run_id", "generated_at", "region_key", "region_name", "country",
        "temp_anomaly_c", "precip_anomaly_pct", "soil_moisture_zscore",
        "composite_score", "temp_score", "precip_score", "moisture_score",
        "critical_month_factor", "is_critical_month", "observation_days", "data_quality",
    ]

    with open(fpath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for key, ra in output.region_anomalies.items():
            row = _anomaly_to_dict(ra)
            row["run_id"] = output.run_id
            row["generated_at"] = output.generated_at
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    logger.info(f"Regions CSV → {fpath}")
    return fpath


def export_all(output: PipelineOutput, export_dir: str = "data") -> dict:
    """Run all exporters. Returns dict of {format: filepath}."""
    return {
        "json": export_json(output, export_dir),
        "signals_csv": export_signals_csv(output, export_dir),
        "regions_csv": export_regions_csv(output, export_dir),
    }
