"""OpenStreetMap facilities within 5 km of each city, through the Overpass API.

Hospitals, clinics, schools (the usual evacuation centres), fire and police
stations, and assembly points. One query per city, spaced out per Overpass's
fair-use rules; each city's rows are replaced in full.
"""
from __future__ import annotations

import time

from ingest.cities import LOCATIONS
from ingest.common import Context, get, haversine_km, upsert, utcnow

NAME = "osm_facilities"
EVERY = 30 * 86400
SCHEMAS = ["reference"]

OVERPASS = "https://overpass-api.de/api/interpreter"
RADIUS_M = 5000
QUERY = """[out:json][timeout:120];
(
  nwr["amenity"~"^(hospital|clinic|school|fire_station|police)$"](around:{r},{lat},{lon});
  nwr["emergency"="assembly_point"](around:{r},{lat},{lon});
);
out center tags;"""
COLS = ["osm_id", "location_id", "kind", "name", "lat", "lon", "distance_km", "fetched_at"]


def run(ctx: Context) -> str:
    total = 0
    for i, city in enumerate(LOCATIONS):
        if i:
            time.sleep(10)
        body = get(ctx.http, OVERPASS, timeout=180,
                   params={"data": QUERY.format(r=RADIUS_M, lat=city.lat, lon=city.lon)}).json()
        fetched_at, rows = utcnow(), {}
        for el in body.get("elements", []):
            lat = el.get("lat", (el.get("center") or {}).get("lat"))
            lon = el.get("lon", (el.get("center") or {}).get("lon"))
            if lat is None:
                continue
            tags = el.get("tags", {})
            kind = tags.get("amenity") if tags.get("amenity") in (
                "hospital", "clinic", "school", "fire_station", "police") else "assembly_point"
            osm_id = f"{el['type']}/{el['id']}"
            rows[osm_id] = (osm_id, city.location_id, kind, tags.get("name") or tags.get("name:en"), lat, lon,
                            round(haversine_km(city.lat, city.lon, lat, lon), 2), fetched_at)
        with ctx.connect() as conn:
            conn.execute("DELETE FROM reference.facilities WHERE location_id = %s", (city.location_id,))
            total += upsert(conn, "reference.facilities", COLS, rows.values(), key=["osm_id", "location_id"])
    return f"{total} facilities within {RADIUS_M // 1000} km of {len(LOCATIONS)} cities"
