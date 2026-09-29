"""
synthetic_data.py — Generate realistic synthetic weather for demo/testing.

Produces data seeded from actual climate baselines with realistic anomalies.
July 2026: uses documented 2026 climate conditions where known:
  - La Niña-to-neutral transition → variable moisture across regions
  - Elevated baseline temps in line with post-2023 trend
  - Brazilian winter (dry season) conditions
  - US summer heat in progress
"""

import random
import math
from datetime import date, timedelta
from typing import Dict

from pipeline.config import REGIONS
from pipeline.weather_fetcher import RegionWeather, DailyObs

# Seed for reproducibility — use today's date as seed for "daily" consistency
SEED = 20260727
random.seed(SEED)


# Real-world-informed anomaly offsets for July 2026
# Based on ENSO-neutral with warm bias, regional patterns
REGION_ANOMALIES = {
    # US Corn Belt: moderate heat, slightly below-normal rain (active weather market)
    "us_corn_belt":            {"temp_offset": +1.8, "precip_mult": 0.72, "sm_offset": -0.06},
    # Brazil Mato Grosso: dry season, near-normal for July
    "brazil_mato_grosso":      {"temp_offset": +0.5, "precip_mult": 0.90, "sm_offset": -0.02},
    # Ukraine: warm and dry — concern for winter wheat establishment
    "ukraine_black_sea":       {"temp_offset": +2.4, "precip_mult": 0.55, "sm_offset": -0.09},
    # US Great Plains: very hot, severe drought (ongoing conditions)
    "us_great_plains":         {"temp_offset": +3.1, "precip_mult": 0.38, "sm_offset": -0.12},
    # Vietnam highlands: late monsoon delayed, drier than normal
    "vietnam_central_highlands":{"temp_offset": +0.9, "precip_mult": 0.78, "sm_offset": -0.05},
    # Colombia: bimodal season, currently in dry inter-season, near normal
    "colombia_coffee_axis":    {"temp_offset": +0.3, "precip_mult": 0.95, "sm_offset": +0.01},
    # Ivory Coast: mid-crop period, good rains so far
    "ivory_coast_cocoa":       {"temp_offset": -0.4, "precip_mult": 1.22, "sm_offset": +0.04},
    # São Paulo sugar belt: off-season (southern hemisphere winter), near normal
    "brazil_sao_paulo_sugar":  {"temp_offset": +0.8, "precip_mult": 0.85, "sm_offset": -0.03},
    # India Deccan: monsoon 2026 tracking below normal — sugar/kharif risk
    "india_deccan":            {"temp_offset": +1.2, "precip_mult": 0.61, "sm_offset": -0.08},
}


def _generate_daily_obs(
    base_temp: float,
    base_precip_daily: float,
    temp_offset: float,
    precip_mult: float,
    sm_base: float,
    sm_offset: float,
    n_days: int = 30,
) -> list:
    """Generate n_days of synthetic daily observations with realistic variation."""
    obs = []
    today = date(2026, 7, 27)

    for i in range(n_days):
        d = today - timedelta(days=n_days - i - 1)

        # Daily temperature variation (sinusoidal + noise)
        day_of_year = d.timetuple().tm_yday
        seasonal_cycle = math.sin(2 * math.pi * (day_of_year - 15) / 365) * 1.5
        noise = random.gauss(0, 1.2)

        t_mean = base_temp + temp_offset + seasonal_cycle + noise
        t_max = t_mean + random.uniform(4, 8)
        t_min = t_mean - random.uniform(4, 8)

        # Precipitation (gamma-like distribution — most days dry, some wet)
        if random.random() < 0.35:  # 35% chance of rain on any day
            rain = max(0.0, random.expovariate(1 / (base_precip_daily * precip_mult * 3)) )
        else:
            rain = 0.0
        rain = round(min(rain, 120), 1)  # cap at 120mm/day

        # ET0 correlated with temperature
        et0 = max(1.0, t_mean * 0.18 + random.gauss(0, 0.5))

        # Soil moisture
        sm = max(0.01, min(0.55, sm_base + sm_offset + random.gauss(0, 0.02)))

        obs.append(DailyObs(
            date=d.isoformat(),
            temp_max=round(t_max, 1),
            temp_min=round(t_min, 1),
            temp_mean=round(t_mean, 1),
            precip_mm=rain,
            et0=round(et0, 2),
            soil_moisture=round(sm, 4),
        ))
    return obs


def generate_synthetic_weather(lookback_days: int = 30) -> Dict[str, RegionWeather]:
    """Generate synthetic RegionWeather for all regions using climate baselines + anomalies."""
    results = {}
    month = 7  # July

    for region_key, region in REGIONS.items():
        anomaly = REGION_ANOMALIES.get(region_key, {"temp_offset": 0.0, "precip_mult": 1.0, "sm_offset": 0.0})

        base_temp = region.temp_baseline_monthly[month - 1]
        base_precip_monthly = region.precip_baseline_monthly[month - 1]
        base_precip_daily = base_precip_monthly / 30.0
        sm_base = 0.28  # global mean soil moisture

        obs = _generate_daily_obs(
            base_temp=base_temp,
            base_precip_daily=base_precip_daily,
            temp_offset=anomaly["temp_offset"],
            precip_mult=anomaly["precip_mult"],
            sm_base=sm_base,
            sm_offset=anomaly["sm_offset"],
            n_days=lookback_days,
        )

        avg_temp = round(sum(o.temp_mean for o in obs) / len(obs), 2)
        total_precip = round(sum(o.precip_mm for o in obs), 1)
        sm_vals = [o.soil_moisture for o in obs if o.soil_moisture]
        avg_sm = round(sum(sm_vals) / len(sm_vals), 4) if sm_vals else None

        results[region_key] = RegionWeather(
            region_key=region_key,
            region_name=region.name,
            country=region.country,
            lat=region.lat,
            lon=region.lon,
            fetch_timestamp="2026-07-27T13:32:00Z",
            observations=obs,
            fetch_ok=True,
            avg_temp_30d=avg_temp,
            total_precip_30d=total_precip,
            avg_soil_moisture=avg_sm,
        )

    return results


if __name__ == "__main__":
    weather = generate_synthetic_weather()
    for k, rw in weather.items():
        print(f"{k:30s}  temp={rw.avg_temp_30d:5.1f}°C  precip={rw.total_precip_30d:6.1f}mm  sm={rw.avg_soil_moisture:.3f}")
