"""The cities BantAI watches. Every job that works per city reads this list.

Starter list: a major city in every region, weighted toward the typhoon belt
(Bicol, Eastern Visayas, Caraga). Coordinates are city centres checked against
OpenWeather's geocoder; PSGC codes are PSA's 9-digit codes, from psgc.gitlab.io.
Add a city here and every job picks it up on its next run.
"""
from __future__ import annotations

from typing import NamedTuple


class City(NamedTuple):
    location_id: str
    name: str
    province: str
    region: str
    lat: float
    lon: float
    psgc_code: str


LOCATIONS: list[City] = [
    City("manila", "Manila", "Metro Manila", "NCR", 14.5904, 120.9804, "133900000"),
    City("quezon-city", "Quezon City", "Metro Manila", "NCR", 14.6511, 121.0486, "137404000"),
    City("baguio", "Baguio", "Benguet", "CAR", 16.4120, 120.5934, "141102000"),
    City("laoag", "Laoag", "Ilocos Norte", "Region I (Ilocos)", 18.1973, 120.5935, "012812000"),
    City("tuguegarao", "Tuguegarao", "Cagayan", "Region II (Cagayan Valley)", 17.6119, 121.7300, "021529000"),
    City("san-fernando-pampanga", "City of San Fernando", "Pampanga", "Region III (Central Luzon)", 15.0283, 120.6938, "035416000"),
    City("calamba", "Calamba", "Laguna", "Region IV-A (CALABARZON)", 14.2091, 121.1652, "043405000"),
    City("calapan", "Calapan", "Oriental Mindoro", "MIMAROPA", 13.4146, 121.1795, "175205000"),
    City("puerto-princesa", "Puerto Princesa", "Palawan", "MIMAROPA", 9.7399, 118.7438, "175316000"),
    City("legazpi", "Legazpi", "Albay", "Region V (Bicol)", 13.1389, 123.7343, "050506000"),
    City("naga", "Naga", "Camarines Sur", "Region V (Bicol)", 13.6240, 123.1850, "051724000"),
    City("virac", "Virac", "Catanduanes", "Region V (Bicol)", 13.5804, 124.2312, "052011000"),
    City("iloilo-city", "Iloilo City", "Iloilo", "Region VI (Western Visayas)", 10.6927, 122.5737, "063022000"),
    City("bacolod", "Bacolod", "Negros Occidental", "NIR (Negros Island)", 10.6763, 122.9514, "064501000"),
    City("cebu-city", "Cebu City", "Cebu", "Region VII (Central Visayas)", 10.2936, 123.9019, "072217000"),
    City("tacloban", "Tacloban", "Leyte", "Region VIII (Eastern Visayas)", 11.2436, 125.0080, "083747000"),
    City("catarman", "Catarman", "Northern Samar", "Region VIII (Eastern Visayas)", 12.4997, 124.6366, "084805000"),
    City("surigao-city", "Surigao City", "Surigao del Norte", "Caraga", 9.7905, 125.4936, "166724000"),
    City("butuan", "Butuan", "Agusan del Norte", "Caraga", 8.9483, 125.5369, "160202000"),
    City("cagayan-de-oro", "Cagayan de Oro", "Misamis Oriental", "Region X (Northern Mindanao)", 8.4756, 124.6422, "104305000"),
    City("davao-city", "Davao City", "Davao del Sur", "Region XI (Davao)", 7.0648, 125.6081, "112402000"),
    City("zamboanga-city", "Zamboanga City", "Zamboanga del Sur", "Region IX (Zamboanga Peninsula)", 6.9047, 122.0765, "097332000"),
    City("general-santos", "General Santos", "South Cotabato", "Region XII (SOCCSKSARGEN)", 6.1122, 125.1722, "126303000"),
    City("cotabato-city", "Cotabato City", "Maguindanao del Norte", "BARMM", 7.2238, 124.2467, "129804000"),
]


def nearest(lat: float, lon: float) -> tuple[str, float]:
    """The closest city and its distance in km."""
    from ingest.common import haversine_km  # local import keeps this module data-only

    best = min(LOCATIONS, key=lambda c: haversine_km(lat, lon, c.lat, c.lon))
    return best.location_id, haversine_km(lat, lon, best.lat, best.lon)


def upsert_locations(conn) -> None:
    """Keep weather.locations in step with this list; other schemas join to it."""
    from ingest.common import upsert

    upsert(conn, "weather.locations",
           ["location_id", "name", "province", "region", "lat", "lon", "psgc_code"],
           [tuple(c) for c in LOCATIONS], key=["location_id"])
