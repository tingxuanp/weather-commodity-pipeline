"""
anomaly_scorer.py — Multi-factor weather anomaly scoring engine.

For each growing region, computes:
  1. Temperature anomaly vs. historical monthly baseline
  2. Precipitation deficit/surplus vs. historical baseline
  3. Soil moisture stress index
  4. Critical-month weighting (weather during key growth stages matters more)
  5. Combined Z-score → directional signal with confidence band

Signal scale: -100 to +100
  Positive = supply-bearish conditions (favourable weather → ample crop)
  Negative = supply-bullish conditions (stress weather → potential supply shock)
  Magnitude reflects severity; ±30 is notable, ±60 is significant, ±80+ is extreme.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import math
import logging

from pipeline.config import REGIONS, COMMODITIES, REGION_TO_COMMODITIES, GrowingRegion, Commodity
from pipeline.weather_fetcher import RegionWeather, DailyObs

logger = logging.getLogger(__name__)


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class RegionAnomaly:
    region_key: str
    region_name: str
    country: str
    # Raw anomalies
    temp_anomaly_c: float          # observed – baseline (°C)
    precip_anomaly_pct: float      # (observed – baseline) / baseline * 100
    soil_moisture_zscore: float    # z-score vs expected range
    # Critical-month multiplier applied
    critical_month_factor: float   # 1.0 = off-season, up to 2.0 = peak season
    # Component scores (each –100 to +100, negative = supply-bullish)
    temp_score: float
    precip_score: float
    moisture_score: float
    # Composite (weighted)
    composite_score: float
    # Metadata
    observation_days: int
    current_month: int
    is_critical_month: bool
    data_quality: str              # "good" | "partial" | "stale"


@dataclass
class CommoditySignal:
    ticker: str
    name: str
    sector: str
    # Weighted signal across all producing regions
    signal_score: float            # –100 to +100
    signal_direction: str          # "BULLISH" | "BEARISH" | "NEUTRAL"
    confidence: str                # "HIGH" | "MEDIUM" | "LOW"
    confidence_score: float        # 0–1
    # Per-region breakdown
    region_contributions: List[Dict]
    # Narrative
    headline: str
    detail_lines: List[str]
    # Metadata
    generated_at: str
    data_coverage: float           # fraction of regions with good data


@dataclass
class PipelineOutput:
    run_id: str
    generated_at: str
    lookback_days: int
    region_anomalies: Dict[str, RegionAnomaly]
    commodity_signals: Dict[str, CommoditySignal]
    pipeline_health: Dict


# ── Scoring Logic ─────────────────────────────────────────────────────────────

def _current_month_baseline(region: GrowingRegion, month: int) -> Tuple[float, float]:
    """Return (temp_baseline_c, precip_baseline_mm) for a given month (1–12)."""
    idx = month - 1
    return (
        region.temp_baseline_monthly[idx],
        region.precip_baseline_monthly[idx],
    )


def _critical_month_factor(region: GrowingRegion, month: int) -> Tuple[float, bool]:
    """
    Returns (factor, is_critical).
    Factor scales between 1.0 (off-season) and 2.0 (peak critical month).
    Adjacent months get partial credit (1.5).
    """
    if month in region.critical_months:
        return 2.0, True
    # Adjacent months (±1 wrap around year)
    adjacent = set()
    for cm in region.critical_months:
        adjacent.add((cm - 2) % 12 + 1)
        adjacent.add(cm % 12 + 1)
    if month in adjacent:
        return 1.5, False
    return 1.0, False


def _temp_score(anomaly_c: float, sensitivity: float) -> float:
    """
    Convert temperature anomaly → score component.
    Positive anomaly (warmer) → negative score (heat stress = supply risk = bullish price).
    Negative anomaly (cooler) → positive score (good conditions = bearish price).
    Cap at ±100.
    """
    # Warmer → stress → negative score
    raw = -anomaly_c * sensitivity * 15   # 1°C with sens=0.8 → -12 pts
    return max(-100.0, min(100.0, raw))


def _precip_score(anomaly_pct: float, sensitivity: float) -> float:
    """
    Convert precip anomaly % → score component.
    Deficit (negative %) → negative score (drought = supply risk = bullish price).
    Surplus (positive %) → positive score (good moisture = bearish price).
    Cap at ±100.
    """
    # Drought (negative anomaly_pct) → negative score
    raw = anomaly_pct * sensitivity * 0.8
    return max(-100.0, min(100.0, raw))


def _soil_moisture_score(zscore: float) -> float:
    """
    Soil moisture Z-score → score.
    Negative Z (dry soil) → negative score (drought risk = bullish price).
    Positive Z (wet soil) → positive score (good moisture = bearish price).
    """
    raw = zscore * 20   # positive Z (wet) → positive score
    return max(-100.0, min(100.0, raw))


def _confidence_from_coverage(data_quality: str, obs_days: int) -> Tuple[str, float]:
    if data_quality == "good" and obs_days >= 25:
        return "HIGH", 0.85
    elif data_quality in ("good", "partial") and obs_days >= 15:
        return "MEDIUM", 0.60
    else:
        return "LOW", 0.35


def _direction_label(score: float) -> str:
    if score <= -25:
        return "BULLISH"   # supply stress → bullish price signal
    elif score >= 25:
        return "BEARISH"   # favourable conditions → bearish price signal
    else:
        return "NEUTRAL"


def _generate_headline(ticker: str, name: str, score: float, direction: str, regions: List[Dict]) -> str:
    severity = (
        "Extreme" if abs(score) >= 75 else
        "Significant" if abs(score) >= 50 else
        "Moderate" if abs(score) >= 25 else
        "Mild"
    )
    worst_region = max(regions, key=lambda r: abs(r["contribution"]), default=None)
    region_str = f" ({worst_region['region_name']})" if worst_region else ""

    if direction == "BULLISH":
        return f"{severity} weather stress in key {name} growing regions{region_str} — potential supply disruption"
    elif direction == "BEARISH":
        return f"Favourable conditions across {name} production zones{region_str} — supply outlook improving"
    else:
        return f"{name} growing conditions near seasonal norms — no material weather signal"


def _generate_detail_lines(
    name: str,
    region_anomalies: List[Tuple[str, RegionAnomaly, float]],
    comm: Commodity,
) -> List[str]:
    lines = []
    for region_key, ra, weight in region_anomalies:
        temp_dir = "above" if ra.temp_anomaly_c > 0 else "below"
        precip_dir = "above" if ra.precip_anomaly_pct > 0 else "below"
        crit = " [critical growth period]" if ra.is_critical_month else ""
        lines.append(
            f"{ra.region_name}: temp {abs(ra.temp_anomaly_c):.1f}°C {temp_dir} norm, "
            f"precip {abs(ra.precip_anomaly_pct):.0f}% {precip_dir} norm{crit}"
        )
    return lines


# ── Main Scoring Functions ────────────────────────────────────────────────────

def score_region(
    region_key: str,
    region: GrowingRegion,
    weather: RegionWeather,
    current_month: int,
    commodity_sensitivity: Optional[Tuple[float, float]] = None,
) -> RegionAnomaly:
    """
    Produce a RegionAnomaly for one region.
    commodity_sensitivity: (temp_sens, precip_sens) from the commodity config.
    """
    temp_sens, precip_sens = commodity_sensitivity or (0.7, 1.0)

    # Data quality assessment
    obs_days = len(weather.observations)
    if not weather.fetch_ok or obs_days == 0:
        data_quality = "stale"
    elif obs_days >= 25:
        data_quality = "good"
    else:
        data_quality = "partial"

    # Baseline for current month
    temp_baseline, precip_baseline = _current_month_baseline(region, current_month)

    # Observed values (use fetched summaries if available)
    obs_temp = weather.avg_temp_30d if weather.avg_temp_30d is not None else temp_baseline
    obs_precip = weather.total_precip_30d if weather.total_precip_30d is not None else precip_baseline

    # Annualise precip baseline to 30-day window
    # Monthly baselines are for a ~30-day month, so direct comparison is valid
    temp_anomaly = round(obs_temp - temp_baseline, 2)
    precip_anomaly_pct = round(
        ((obs_precip - precip_baseline) / precip_baseline * 100)
        if precip_baseline > 0 else 0.0,
        1
    )

    # Soil moisture Z-score (rough: actual vs expected 0.2–0.4 range)
    sm = weather.avg_soil_moisture
    if sm is not None:
        # Normalise to expected range [0.1, 0.5] → z-score
        sm_mean, sm_std = 0.28, 0.08
        sm_zscore = round((sm - sm_mean) / sm_std, 2)
    else:
        # Infer from precip deficit as proxy
        sm_zscore = round(-precip_anomaly_pct / 50, 2)

    crit_factor, is_critical = _critical_month_factor(region, current_month)

    # Component scores
    ts = _temp_score(temp_anomaly, temp_sens)
    ps = _precip_score(precip_anomaly_pct, precip_sens)
    ms = _soil_moisture_score(sm_zscore)

    # Weighted composite: precip dominates, temp secondary, moisture tertiary
    # critical_month_factor [1.0, 2.0] boosts signal magnitude during key growth stages
    # Scale factor so crit=1.0→1.0x, crit=1.5→1.25x, crit=2.0→1.5x amplitude
    amplitude_boost = 1.0 + (crit_factor - 1.0) * 0.5
    composite_raw = (ts * 0.30) + (ps * 0.50) + (ms * 0.20)
    composite = round(composite_raw * amplitude_boost, 2)
    composite = max(-100.0, min(100.0, composite))

    return RegionAnomaly(
        region_key=region_key,
        region_name=region.name,
        country=region.country,
        temp_anomaly_c=temp_anomaly,
        precip_anomaly_pct=precip_anomaly_pct,
        soil_moisture_zscore=sm_zscore,
        critical_month_factor=crit_factor,
        temp_score=round(ts, 2),
        precip_score=round(ps, 2),
        moisture_score=round(ms, 2),
        composite_score=composite,
        observation_days=obs_days,
        current_month=current_month,
        is_critical_month=is_critical,
        data_quality=data_quality,
    )


def score_commodity(
    ticker: str,
    comm: Commodity,
    region_anomalies: Dict[str, RegionAnomaly],
    regions_config: dict,
) -> CommoditySignal:
    """Roll up region anomalies into a single commodity signal."""
    now = datetime.utcnow().isoformat() + "Z"
    region_contributions = []
    weighted_score = 0.0
    total_weight = 0.0
    good_regions = 0

    for region_key in comm.regions:
        region = regions_config.get(region_key)
        ra = region_anomalies.get(region_key)
        if region is None or ra is None:
            continue

        w = region.commodity_weight
        contribution = ra.composite_score * w
        weighted_score += contribution
        total_weight += w

        if ra.data_quality == "good":
            good_regions += 1

        region_contributions.append({
            "region_key": region_key,
            "region_name": ra.region_name,
            "country": ra.country,
            "weight": round(w, 3),
            "composite_score": ra.composite_score,
            "contribution": round(contribution, 2),
            "temp_anomaly_c": ra.temp_anomaly_c,
            "precip_anomaly_pct": ra.precip_anomaly_pct,
            "is_critical_month": ra.is_critical_month,
            "data_quality": ra.data_quality,
        })

    # Normalise by total weight
    final_score = round((weighted_score / total_weight) if total_weight > 0 else 0.0, 2)
    final_score = max(-100.0, min(100.0, final_score))

    direction = _direction_label(final_score)
    data_coverage = good_regions / max(len(comm.regions), 1)
    avg_quality = "good" if data_coverage >= 0.7 else "partial" if data_coverage >= 0.4 else "stale"
    avg_obs = int(
        sum(
            region_anomalies[rk].observation_days
            for rk in comm.regions
            if rk in region_anomalies
        ) / max(len(comm.regions), 1)
    )
    conf_label, conf_score = _confidence_from_coverage(avg_quality, avg_obs)

    # Sort contributions by absolute impact
    region_contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)

    headline = _generate_headline(ticker, comm.name, final_score, direction, region_contributions)
    detail_lines = _generate_detail_lines(
        comm.name,
        [(rc["region_key"], region_anomalies[rc["region_key"]], rc["weight"])
         for rc in region_contributions if rc["region_key"] in region_anomalies],
        comm,
    )

    return CommoditySignal(
        ticker=ticker,
        name=comm.name,
        sector=comm.sector,
        signal_score=final_score,
        signal_direction=direction,
        confidence=conf_label,
        confidence_score=round(conf_score, 2),
        region_contributions=region_contributions,
        headline=headline,
        detail_lines=detail_lines,
        generated_at=now,
        data_coverage=round(data_coverage, 2),
    )


def run_scoring(
    weather_data: Dict[str, RegionWeather],
    current_month: Optional[int] = None,
) -> PipelineOutput:
    """Full scoring pass: regions → commodity signals."""
    if current_month is None:
        current_month = datetime.utcnow().month

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    logger.info(f"[{run_id}] Scoring {len(weather_data)} regions for month={current_month}")

    # Step 1: Score each region (use mean sensitivity across its commodities)
    region_anomalies: Dict[str, RegionAnomaly] = {}
    for region_key, region in REGIONS.items():
        weather = weather_data.get(region_key)
        if weather is None:
            logger.warning(f"No weather data for {region_key}, skipping")
            continue

        # Average sensitivity from all commodities that use this region
        comm_keys = REGION_TO_COMMODITIES.get(region_key, [])
        if comm_keys:
            avg_temp_sens = sum(COMMODITIES[c].temp_sensitivity for c in comm_keys) / len(comm_keys)
            avg_prec_sens = sum(COMMODITIES[c].precip_sensitivity for c in comm_keys) / len(comm_keys)
        else:
            avg_temp_sens, avg_prec_sens = 0.7, 1.0

        ra = score_region(
            region_key, region, weather, current_month,
            commodity_sensitivity=(avg_temp_sens, avg_prec_sens)
        )
        region_anomalies[region_key] = ra
        logger.debug(
            f"  [{region_key}] composite={ra.composite_score:+.1f} | "
            f"temp={ra.temp_anomaly_c:+.2f}°C | precip={ra.precip_anomaly_pct:+.0f}%"
        )

    # Step 2: Roll up into commodity signals
    commodity_signals: Dict[str, CommoditySignal] = {}
    for ticker, comm in COMMODITIES.items():
        sig = score_commodity(ticker, comm, region_anomalies, REGIONS)
        commodity_signals[ticker] = sig
        logger.info(
            f"  [{ticker}] {sig.name}: score={sig.signal_score:+.1f} "
            f"({sig.signal_direction}, {sig.confidence})"
        )

    # Pipeline health summary
    ok_regions = sum(1 for rw in weather_data.values() if rw.fetch_ok)
    health = {
        "run_id": run_id,
        "regions_fetched": ok_regions,
        "regions_total": len(REGIONS),
        "fetch_success_rate": round(ok_regions / max(len(REGIONS), 1), 2),
        "commodities_scored": len(commodity_signals),
        "current_month": current_month,
    }

    return PipelineOutput(
        run_id=run_id,
        generated_at=datetime.utcnow().isoformat() + "Z",
        lookback_days=30,
        region_anomalies=region_anomalies,
        commodity_signals=commodity_signals,
        pipeline_health=health,
    )
