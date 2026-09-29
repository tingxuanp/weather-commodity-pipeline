"""
config.py — Growing region and commodity configuration.

Maps commodities to their key production regions with coordinates,
historical climate baselines, and signal sensitivity weights.
"""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class GrowingRegion:
    name: str
    country: str
    lat: float
    lon: float
    # Historical monthly baselines (Jan–Dec): [temp_c, precip_mm]
    temp_baseline_monthly: List[float]   # mean temp °C per month
    precip_baseline_monthly: List[float] # mean precip mm per month
    critical_months: List[int]           # months where weather matters most (1=Jan)
    commodity_weight: float              # region's share of global production (0–1)


@dataclass
class Commodity:
    ticker: str          # CME/ICE contract code
    name: str
    sector: str          # "agricultural" | "soft"
    unit: str
    regions: List[str]   # region keys
    # Directional sensitivity: positive = hot/dry is bullish, negative = bearish
    temp_sensitivity: float   # per 1°C anomaly → signal delta
    precip_sensitivity: float # per 10% precip deficit → signal delta


# ── Growing Regions ──────────────────────────────────────────────────────────

REGIONS: Dict[str, GrowingRegion] = {

    # ── CORN BELT (US) ─────────────────────────────────────────────────────
    "us_corn_belt": GrowingRegion(
        name="US Corn Belt",
        country="United States",
        lat=41.5, lon=-93.6,  # Des Moines, Iowa centroid
        temp_baseline_monthly=[-8.5,-5.8,0.6,9.2,15.4,20.6,23.1,22.2,16.8,10.1,2.3,-5.8],
        precip_baseline_monthly=[25,27,45,85,105,112,95,88,78,62,42,28],
        critical_months=[6, 7, 8],  # June–Aug: pollination
        commodity_weight=0.55
    ),

    # ── BRAZIL (MATO GROSSO) — Corn + Soybeans ─────────────────────────────
    "brazil_mato_grosso": GrowingRegion(
        name="Brazil – Mato Grosso",
        country="Brazil",
        lat=-12.6, lon=-55.4,
        temp_baseline_monthly=[26.8,26.5,26.3,26.0,25.2,24.1,23.8,25.0,26.5,27.1,27.0,27.0],
        precip_baseline_monthly=[260,210,230,130,60,20,15,30,90,160,230,270],
        critical_months=[11, 12, 1, 2],  # Nov–Feb: Brazilian summer crop
        commodity_weight=0.30
    ),

    # ── UKRAINE / BLACK SEA — Wheat ─────────────────────────────────────────
    "ukraine_black_sea": GrowingRegion(
        name="Ukraine – Black Sea Region",
        country="Ukraine",
        lat=49.0, lon=32.0,
        temp_baseline_monthly=[-4.2,-3.5,1.8,9.5,16.1,19.8,21.6,21.0,15.2,8.8,2.4,-2.2],
        precip_baseline_monthly=[38,38,38,42,52,60,70,52,40,35,40,40],
        critical_months=[4, 5, 6],  # Apr–Jun: heading + grain fill
        commodity_weight=0.18
    ),

    # ── US GREAT PLAINS — Wheat ─────────────────────────────────────────────
    "us_great_plains": GrowingRegion(
        name="US Great Plains",
        country="United States",
        lat=38.5, lon=-97.5,  # Kansas centroid
        temp_baseline_monthly=[-1.8,0.8,6.5,13.2,18.8,24.1,27.3,26.5,21.0,14.0,5.8,-0.2],
        precip_baseline_monthly=[18,22,38,52,72,78,55,60,52,40,28,18],
        critical_months=[4, 5, 6],
        commodity_weight=0.15
    ),

    # ── VIETNAM / MEKONG — Coffee ───────────────────────────────────────────
    "vietnam_central_highlands": GrowingRegion(
        name="Vietnam – Central Highlands",
        country="Vietnam",
        lat=12.7, lon=108.1,  # Dak Lak province
        temp_baseline_monthly=[19.0,20.5,22.5,23.8,23.5,22.0,21.5,21.8,21.5,20.8,19.5,18.5],
        precip_baseline_monthly=[10,15,40,100,220,260,280,250,200,150,80,25],
        critical_months=[4, 5, 10, 11],  # Wet season onset + dry spell for flowering
        commodity_weight=0.30
    ),

    # ── COLOMBIA — Coffee (Arabica) ─────────────────────────────────────────
    "colombia_coffee_axis": GrowingRegion(
        name="Colombia – Coffee Growing Axis",
        country="Colombia",
        lat=5.0, lon=-75.5,
        temp_baseline_monthly=[17.0,17.5,17.8,17.5,17.2,16.8,16.5,16.8,17.0,17.2,17.0,16.8],
        precip_baseline_monthly=[100,110,160,200,220,160,150,150,200,230,200,120],
        critical_months=[3, 4, 9, 10],  # bimodal flowering seasons
        commodity_weight=0.15
    ),

    # ── IVORY COAST / GHANA — Cocoa ─────────────────────────────────────────
    "ivory_coast_cocoa": GrowingRegion(
        name="Ivory Coast – Cocoa Belt",
        country="Côte d'Ivoire",
        lat=6.5, lon=-5.5,
        temp_baseline_monthly=[27.0,28.0,28.5,28.0,27.5,26.5,25.5,25.5,26.0,26.5,27.5,27.0],
        precip_baseline_monthly=[30,55,110,140,280,480,160,60,80,160,80,30],
        critical_months=[9, 10, 3, 4],  # main crop + mid-crop
        commodity_weight=0.44
    ),

    # ── BRAZIL (NORTHEAST) — Sugar ──────────────────────────────────────────
    "brazil_sao_paulo_sugar": GrowingRegion(
        name="Brazil – São Paulo / Sugarcane Belt",
        country="Brazil",
        lat=-22.5, lon=-47.5,
        temp_baseline_monthly=[23.5,23.8,23.0,21.5,19.0,17.0,16.5,18.0,20.5,22.0,23.0,23.5],
        precip_baseline_monthly=[215,195,140,62,58,40,30,38,75,120,150,195],
        critical_months=[10, 11, 12, 1],  # growing season
        commodity_weight=0.35
    ),

    # ── INDIA (UP/MAHARASHTRA) — Sugar + Soybeans ───────────────────────────
    "india_deccan": GrowingRegion(
        name="India – Deccan Plateau",
        country="India",
        lat=18.5, lon=76.0,
        temp_baseline_monthly=[23.0,25.5,29.0,32.5,33.0,28.5,26.5,26.5,27.0,27.5,25.0,22.5],
        precip_baseline_monthly=[10,8,12,18,28,120,180,160,110,60,20,8],
        critical_months=[6, 7, 8, 9],  # Monsoon critical for kharif crop
        commodity_weight=0.18
    ),
}


# ── Commodities ───────────────────────────────────────────────────────────────

COMMODITIES: Dict[str, Commodity] = {

    "ZC": Commodity(
        ticker="ZC",
        name="Corn",
        sector="agricultural",
        unit="¢/bu",
        regions=["us_corn_belt", "brazil_mato_grosso"],
        temp_sensitivity=0.8,    # heat stress → bullish
        precip_sensitivity=1.2,  # drought → strongly bullish
    ),

    "ZW": Commodity(
        ticker="ZW",
        name="Wheat",
        sector="agricultural",
        unit="¢/bu",
        regions=["ukraine_black_sea", "us_great_plains"],
        temp_sensitivity=0.6,
        precip_sensitivity=0.9,
    ),

    "ZS": Commodity(
        ticker="ZS",
        name="Soybeans",
        sector="agricultural",
        unit="¢/bu",
        regions=["us_corn_belt", "brazil_mato_grosso"],
        temp_sensitivity=0.7,
        precip_sensitivity=1.1,
    ),

    "KC": Commodity(
        ticker="KC",
        name="Coffee (Arabica)",
        sector="soft",
        unit="¢/lb",
        regions=["vietnam_central_highlands", "colombia_coffee_axis"],
        temp_sensitivity=0.5,
        precip_sensitivity=1.4,  # rainfall timing is critical for flowering
    ),

    "CC": Commodity(
        ticker="CC",
        name="Cocoa",
        sector="soft",
        unit="$/MT",
        regions=["ivory_coast_cocoa"],
        temp_sensitivity=0.4,
        precip_sensitivity=1.6,  # very moisture-sensitive
    ),

    "SB": Commodity(
        ticker="SB",
        name="Sugar #11",
        sector="soft",
        unit="¢/lb",
        regions=["brazil_sao_paulo_sugar", "india_deccan"],
        temp_sensitivity=0.3,
        precip_sensitivity=1.0,
    ),
}

# Which regions belong to which commodities (reverse lookup)
REGION_TO_COMMODITIES: Dict[str, List[str]] = {}
for ticker, comm in COMMODITIES.items():
    for region_key in comm.regions:
        REGION_TO_COMMODITIES.setdefault(region_key, []).append(ticker)
