# Weather-Commodity Alternative Data Pipeline

This README contains instructions on how to run and interpret the project for part 2.
This is an alternative data pipeline for commodity traders that pulls real weather
observations from 9 key growing regions around the world, scores temperature
and precipitation anomalies against historical monthly baselines, and outputs
directional supply signals for 6 commodity contracts.

The pipeline writes its output to a JSON file. A browser-based dashboard reads
that file and presents the data in a dashboard.

---

## Requirements

- Python 3.10 or newer
- No API keys are required. Weather data comes from Open-Meteo, which is free
  and open-source.

---

## Installation

**1. Clone or unzip the project.**

Extract the downloaded zip to a folder. You should end up with the structure shown above.

**2. Open a terminal and navigate to the project folder.**

```bash
cd path/to/weather-commodity-pipeline
```

**3. Create a virtual environment.**

Here, as an example, the virtual environment is called `venv`.

```bash
python -m venv venv
```

Activate it:

```bash
# Windows (PowerShell):
venv\Scripts\Activate
```

**4. Install dependencies.**

```bash
pip install aiohttp pandas numpy scipy requests
```

---

## Running the pipeline

From the project root folder, run:

```bash
python run_pipeline.py
```

This does three things:

1. Fetches the last 30 days of weather data for all 9 regions from Open-Meteo
2. Scores each region's temperature and precipitation anomalies
3. Rolls those up into commodity signals and writes them to `data/`

A successful run looks like this in the terminal:

```
2026-07-27T21:44:53 [INFO] pipeline.runner — STEP 1/3 — Fetching weather data...
2026-07-27T21:44:55 [INFO] pipeline.weather_fetcher — Weather fetch complete: 9/9 regions OK
2026-07-27T21:44:55 [INFO] pipeline.runner — STEP 2/3 — Scoring weather anomalies...
2026-07-27T21:44:55 [INFO] pipeline.runner — STEP 3/3 — Exporting data...
2026-07-27T21:44:55 [INFO] pipeline.runner — PIPELINE COMPLETE
  ZC    NEUTRAL    -17.9  [HIGH  ]
  ZW    BULLISH    -37.7  [HIGH  ]  ▲▲▲▲▲▲▲
  ZS    NEUTRAL    -17.9  [HIGH  ]
  ...
```

After the run, the `data/` folder will be created (if it didn't exist) and
populated with JSON and CSV files.

### CLI options

```
--lookback N      Number of days of historical weather to fetch. Default is 30.
                  Use a smaller number (e.g. 7) for faster runs during testing.

--dry-run         Runs the fetch and scoring steps but skips writing any files.
                  Useful for checking that everything works without actually creating output.
```

Examples:

```bash
python run_pipeline.py --lookback 14
python run_pipeline.py --dry-run
```

---

## Viewing the dashboard

The dashboard is a single HTML file at `dashboard/dashboard.html`. It reads
`data/signals_latest.json` to display the signals.

To view the dashboard:

**Step 1:** Run the pipeline at least once so `data/signals_latest.json` exists.

```bash
python run_pipeline.py
```

**Step 2:** Start a local web server from the project root folder.

```bash
python -m http.server 8000
```

Leave this terminal running. You should see:

```
Serving HTTP on 0.0.0.0 port 8000 (http://0.0.0.0:8000/) ...
```

**Step 3:** Open the browser and go to:

```
http://localhost:8000/dashboard/dashboard.html
```

The dashboard will load and display the current signals.

**To refresh after a new pipeline run:** just press F5 in
the browser. The dashboard always reads from `data/signals_latest.json`, which
is overwritten on every run.

**To stop the web server:** press Ctrl+C in the terminal where it's running.

### What the dashboard shows

- **KPI row at the top:** strongest signal across all commodities, the most
  weather-stressed region, how many regions are currently in a critical growth
  month, and data coverage.

- **Signal cards:** one card per commodity. The left border is red for BULLISH
  (supply stress), green for BEARISH (favourable conditions), grey for NEUTRAL.
  Click any card to expand a breakdown by region.

- **Filter pills:** filter cards by sector (Agricultural / Soft commodities) or
  show only the BULLISH signals.

- **Region grid:** all 9 growing regions with their temperature and precipitation
  anomaly, and whether they're currently in a critical growth period.

- **Bar chart:** composite scores for all regions in one view. Red bars indicate
  stress, green bars indicate favourable conditions.

---

## Understanding the output

### signals_latest.json

The main output file. Always contains the result of the most recent run.
Structure:

```json
{
  "run_id": "20260727T133315Z",
  "generated_at": "2026-07-27T13:33:15Z",
  "lookback_days": 30,
  "pipeline_health": {
    "regions_fetched": 9,
    "regions_total": 9,
    "fetch_success_rate": 1.0,
    "commodities_scored": 6
  },
  "commodity_signals": {
    "ZW": {
      "ticker": "ZW",
      "name": "Wheat",
      "sector": "agricultural",
      "signal_score": -37.66,
      "signal_direction": "BULLISH",
      "confidence": "HIGH",
      "confidence_score": 0.85,
      "headline": "Moderate weather stress in key Wheat growing regions...",
      "detail_lines": [
        "US Great Plains: temp 3.3°C above norm, precip 60% below norm"
      ],
      "region_contributions": [
        {
          "region_name": "US Great Plains",
          "weight": 0.15,
          "composite_score": -45.56,
          "temp_anomaly_c": 3.27,
          "precip_anomaly_pct": -60.5,
          "is_critical_month": false,
          "data_quality": "good"
        }
      ],
      "data_coverage": 1.0
    }
  },
  "region_anomalies": {
    "us_great_plains": {
      "temp_anomaly_c": 3.27,
      "precip_anomaly_pct": -60.5,
      "composite_score": -45.56,
      "is_critical_month": false,
      "data_quality": "good",
      "observation_days": 30
    }
  }
}
```

### signals\_<run_id>.csv

Flat CSV with one row per commodity. Columns: `run_id`, `generated_at`, `ticker`, `name`, `sector`, `signal_score`, `signal_direction`, `confidence`,
`confidence_score`, `data_coverage`, `headline`.

### regions\_<run_id>.csv

Flat CSV with one row per growing region. Columns include `temp_anomaly_c`,
`precip_anomaly_pct`, `composite_score`, `is_critical_month`, `data_quality`.

---

## How the scoring works

The pipeline has two scoring stages.
This scoring has been simplified for the purpose of this prototype. The limitations and areas for extension are included in the subsequent section.

### Stage 1: Region anomaly score

For each of the 9 growing regions, it computes three component scores, each
on a scale of −100 to +100:

**Convention: negative = supply stress = bullish price signal.**
A drought that stresses a crop -> negative score -> BULLISH direction.
Ideal growing conditions -> positive score -> BEARISH direction.

```
temp_score     = -temp_anomaly_c × temp_sensitivity × 15
                 (warm anomaly -> heat stress -> negative)

precip_score   = precip_anomaly_pct × precip_sensitivity × 0.8
                 (rainfall deficit -> drought -> negative)

moisture_score = soil_moisture_zscore × 20
                 (inferred from precip anomaly; dry soil → negative)
```

These are combined into a weighted composite:

```
composite_raw = (temp_score × 0.30) + (precip_score × 0.50) + (moisture_score × 0.20)
```

The 50/30/20 split was simply chosen as a reasonable prior.
In production, one should fit these weights using historical yield data and weather anomalies using, for example, LASSO regression or a Shapley decomposition.

If the current calendar month is a **critical growth period** for that region
(e.g. July–August for US corn during pollination), an amplitude boost is
applied:

```
amplitude_boost = 1.0 + (critical_month_factor - 1.0) × 0.5
composite       = composite_raw × amplitude_boost   (clamped to ±100)
```

Critical months are defined per region in `pipeline/config.py`. Off-season
months get a factor of 1.0 (no boost). Critical months get 2.0 (50% boost to
the final score). Adjacent months get 1.5 (25% boost).

### Stage 2: Commodity signal

Each commodity maps to multiple growing regions, each with a production weight
reflecting its share of global output. The commodity signal is the
production-weighted average of its regions' composite scores:

```
signal_score = sum_of(region_composite × region_weight) / sum_of(weights)
```

Example: Wheat maps to Ukraine/Black Sea (18% weight) and US Great Plains
(15% weight). If both are stressed, both contribute negative scores, weighted
by their production share.

### Signal thresholds

| Score      | Direction | What it means                                       |
| ---------- | --------- | --------------------------------------------------- |
| ≤ −25      | BULLISH   | Meaningful supply stress across key growing regions |
| −25 to +25 | NEUTRAL   | Conditions broadly within seasonal norms            |
| ≥ +25      | BEARISH   | Favourable conditions — supply outlook improving    |

Magnitude:

| Absolute score | Severity    |
| -------------- | ----------- |
| 25–50          | Moderate    |
| 50–75          | Significant |
| 75–100         | Extreme     |

### Confidence levels

| Level  | Condition                                            |
| ------ | ---------------------------------------------------- |
| HIGH   | 25+ days of good data across all regions             |
| MEDIUM | 15+ days, or some regions with partial data          |
| LOW    | Fewer than 15 days, or fetch failures across regions |

### Limitations

Some ways the scoring is simplified is detailed below::

- It assumes linear relationships between anomaly magnitude and supply impact. In reality, these are non-linear - a 20% precipitation deficit in a drought-stressed soil is far worse than a 20% deficit on top of a wet baseline.
- It treats temperature and precipitation independently, even though in reality, tehy interact.
- There is no memory - it only looks at the last 30 days, so a e.g. 90-day cumulative drough doesn't score worse than a 30-day one.

---

## Commodities and regions covered

### Commodities

| Ticker | Name         | Sector       | Temp sensitivity | Precip sensitivity |
| ------ | ------------ | ------------ | ---------------- | ------------------ |
| ZC     | Corn         | Agricultural | 0.8              | 1.2                |
| ZW     | Wheat        | Agricultural | 0.6              | 0.9                |
| ZS     | Soybeans     | Agricultural | 0.7              | 1.1                |
| KC     | Coffee (Ara) | Soft         | 0.5              | 1.4                |
| CC     | Cocoa        | Soft         | 0.4              | 1.6                |
| SB     | Sugar #11    | Soft         | 0.3              | 1.0                |

Sensitivity values control how strongly a 1°C or 10% precipitation anomaly
moves the signal. Cocoa, for example, is extremely moisture-sensitive (1.6),
while sugar is less temperature-sensitive (0.3).

These sensitivity values were also set as estimates, not calibrated against historical price moves or yield data.
In practice, one should regress commodity futures returns against weather anomalies in each region during critical months, estimate the beta, and use that as the sensitivity.

### Growing regions

Note that for simplicity, the critical months have been hardcoded and are
based on agronomic knowledge, generally following well-established crop calendars.
In production, it would be better to validate these critical months against
yield regression studies, or crop progress reports from official sources.

| Region key                | Name                          | Country       | Critical months        |
| ------------------------- | ----------------------------- | ------------- | ---------------------- |
| us_corn_belt              | US Corn Belt                  | United States | June, July, August     |
| brazil_mato_grosso        | Brazil – Mato Grosso          | Brazil        | Nov, Dec, Jan, Feb     |
| ukraine_black_sea         | Ukraine – Black Sea Region    | Ukraine       | April, May, June       |
| us_great_plains           | US Great Plains               | United States | April, May, June       |
| vietnam_central_highlands | Vietnam – Central Highlands   | Vietnam       | April, May, Oct, Nov   |
| colombia_coffee_axis      | Colombia – Coffee Axis        | Colombia      | March, April, Sep, Oct |
| ivory_coast_cocoa         | Ivory Coast – Cocoa Belt      | Côte d'Ivoire | Sep, Oct, Mar, Apr     |
| brazil_sao_paulo_sugar    | Brazil – São Paulo Sugar Belt | Brazil        | Oct, Nov, Dec, Jan     |
| india_deccan              | India – Deccan Plateau        | India         | June, July, Aug, Sep   |

---

## Data sources

**Weather observations:** [Open-Meteo](https://open-meteo.com/) — free,
no API key required, based on ERA5 reanalysis and NWP model data. The pipeline
uses the daily variables
`temperature_2m_max`, `temperature_2m_min`, `temperature_2m_mean`,
`precipitation_sum`, and `et0_fao_evapotranspiration`.
