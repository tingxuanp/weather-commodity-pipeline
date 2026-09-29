"""
weather_fetcher.py — Fetches current + recent weather for growing regions.

Uses Open-Meteo (open-meteo.com) — free, no API key, WMO-quality data.
Returns 30-day rolling observations per region for anomaly computation.
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta, date
from dataclasses import dataclass
from typing import Dict, List, Optional
import json

from pipeline.config import REGIONS, GrowingRegion

logger = logging.getLogger(__name__)

BASE_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "et0_fao_evapotranspiration",  # evapotranspiration → drought index component
]


@dataclass
class DailyObs:
    date: str
    temp_max: float
    temp_min: float
    temp_mean: float
    precip_mm: float
    et0: float
    soil_moisture: Optional[float]


@dataclass
class RegionWeather:
    region_key: str
    region_name: str
    country: str
    lat: float
    lon: float
    fetch_timestamp: str
    observations: List[DailyObs]  # last 30 days
    fetch_ok: bool
    error: Optional[str] = None

    # Computed summaries (filled by scorer)
    avg_temp_30d: Optional[float] = None
    total_precip_30d: Optional[float] = None
    avg_soil_moisture: Optional[float] = None


def _parse_daily(raw: dict) -> List[DailyObs]:
    """Parse Open-Meteo daily response into DailyObs list."""
    daily = raw.get("daily", {})
    dates = daily.get("time", [])
    results = []
    for i, d in enumerate(dates):
        def safe(key, default=0.0):
            vals = daily.get(key, [])
            v = vals[i] if i < len(vals) else None
            return float(v) if v is not None else default

        results.append(DailyObs(
            date=d,
            temp_max=safe("temperature_2m_max"),
            temp_min=safe("temperature_2m_min"),
            temp_mean=safe("temperature_2m_mean"),
            precip_mm=safe("precipitation_sum"),
            et0=safe("et0_fao_evapotranspiration"),
            soil_moisture=None,
        ))
    return results


async def _fetch_region(
    session: aiohttp.ClientSession,
    region_key: str,
    region: GrowingRegion,
    lookback_days: int = 30,
) -> RegionWeather:
    """Fetch last `lookback_days` of daily weather for one region."""
    end_date = date.today()
    start_date = end_date - timedelta(days=lookback_days)

    params = {
        "latitude": region.lat,
        "longitude": region.lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ",".join(DAILY_VARS),
        "timezone": "UTC",
    }

    try:
        # Open-Meteo serves recent historical via the forecast endpoint
        async with session.get(BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")
            raw = await resp.json()

        obs = _parse_daily(raw)
        rw = RegionWeather(
            region_key=region_key,
            region_name=region.name,
            country=region.country,
            lat=region.lat,
            lon=region.lon,
            fetch_timestamp=datetime.utcnow().isoformat() + "Z",
            observations=obs,
            fetch_ok=True,
        )

        # Quick summaries
        if obs:
            rw.avg_temp_30d = round(sum(o.temp_mean for o in obs) / len(obs), 2)
            rw.total_precip_30d = round(sum(o.precip_mm for o in obs), 1)
            rw.avg_soil_moisture = None

        logger.info(
            f"[{region_key}] fetched {len(obs)} days | "
            f"avg_temp={rw.avg_temp_30d}°C | precip={rw.total_precip_30d}mm"
        )
        return rw

    except Exception as exc:
        logger.error(f"[{region_key}] fetch failed: {exc}")
        return RegionWeather(
            region_key=region_key,
            region_name=region.name,
            country=region.country,
            lat=region.lat,
            lon=region.lon,
            fetch_timestamp=datetime.utcnow().isoformat() + "Z",
            observations=[],
            fetch_ok=False,
            error=str(exc),
        )


async def fetch_all_regions(lookback_days: int = 30) -> Dict[str, RegionWeather]:
    """Concurrently fetch weather for all configured regions."""
    logger.info(f"Fetching weather for {len(REGIONS)} regions (last {lookback_days} days)…")
    connector = aiohttp.TCPConnector(limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            _fetch_region(session, key, region, lookback_days)
            for key, region in REGIONS.items()
        ]
        results = await asyncio.gather(*tasks)

    region_map = {rw.region_key: rw for rw in results}
    ok = sum(1 for rw in results if rw.fetch_ok)
    logger.info(f"Weather fetch complete: {ok}/{len(results)} regions OK")
    return region_map


def fetch_all_regions_sync(lookback_days: int = 30) -> Dict[str, RegionWeather]:
    """Synchronous wrapper around async fetch."""
    return asyncio.run(fetch_all_regions(lookback_days))
