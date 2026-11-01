"""Project NOAH hazard around each city, from NOAH's vector tiles.

Reads only the zoom-14 tiles around each city (HTTP range requests into the
combined PMTiles file on Hugging Face, published by BetterGov.ph), instead of
downloading 23 GB of shapefiles. For every hazard layer it records the level at
the city centre, the highest level within 1 km, and the share of a 2 km disc at
medium-or-high and at high hazard.

The maps are static, so this runs once a year (or by hand with --once noah).
Needs pmtiles, mapbox-vector-tile and shapely (requirements-jupyter.txt).
"""
from __future__ import annotations

import functools
import gzip
import math

from ingest.cities import LOCATIONS
from ingest.common import Context, upsert, utcnow

NAME = "noah"
EVERY = 365 * 86400
SCHEMAS = ["hazards"]

URL = ("https://huggingface.co/datasets/bettergovph/project-noah-hazard-maps/resolve/main/"
       "PMTiles/noah_hazard_maps.pmtiles")
ZOOM = 14
LAYERS = {
    "flood_5yr": ("flood", "5yr"), "flood_25yr": ("flood", "25yr"), "flood_100yr": ("flood", "100yr"),
    "landslide": ("landslide", "any"), "debris_flow": ("debris_flow", "any"),
    "storm_surge_ssa1": ("storm_surge", "ssa1"), "storm_surge_ssa2": ("storm_surge", "ssa2"),
    "storm_surge_ssa3": ("storm_surge", "ssa3"), "storm_surge_ssa4": ("storm_surge", "ssa4"),
}
DISC_M, NEAR_M = 2000, 1000
COLS = ["location_id", "hazard", "scenario", "level_at_center", "max_level_1km", "pct_medium_high_2km",
        "pct_high_2km", "computed_at"]


def _tile(lat: float, lon: float) -> tuple[float, float]:
    """Fractional tile coordinates at ZOOM."""
    n = 2 ** ZOOM
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def run(ctx: Context) -> str:
    import mapbox_vector_tile
    import numpy as np
    from pmtiles.reader import Reader
    from shapely import make_valid
    from shapely.geometry import Point, shape
    from shapely.ops import transform, unary_union

    # The reader looks up the same directory ranges for every tile; cache them so
    # each is fetched once per run instead of once per tile.
    @functools.lru_cache(maxsize=4096)
    def get_bytes(offset: int, length: int) -> bytes:
        resp = ctx.http.get(URL, headers={"Range": f"bytes={offset}-{offset + length - 1}"}, timeout=120)
        resp.raise_for_status()
        return resp.content

    reader = Reader(get_bytes)
    n = 2 ** ZOOM
    rows, computed_at = [], utcnow()
    for city in LOCATIONS:
        m_per_lon = 111320 * math.cos(math.radians(city.lat))
        pad_lat, pad_lon = (DISC_M + 200) / 110574, (DISC_M + 200) / m_per_lon
        x0, y1 = _tile(city.lat - pad_lat, city.lon - pad_lon)
        x1, y0 = _tile(city.lat + pad_lat, city.lon + pad_lon)

        by_layer: dict[str, dict[int, list]] = {name: {1: [], 2: [], 3: []} for name in LAYERS}
        for tx in range(int(x0), int(x1) + 1):
            for ty in range(int(y0), int(y1) + 1):
                data = reader.get(ZOOM, tx, ty)
                if not data:
                    continue
                if data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                tile = mapbox_vector_tile.decode(data, default_options={"y_coord_down": True})

                def to_metres(px, py, tx=tx, ty=ty, extent=4096):
                    px, py = np.asarray(px, dtype=float), np.asarray(py, dtype=float)
                    lon = (tx + px / extent) / n * 360 - 180
                    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (ty + py / extent) / n))))
                    return (lon - city.lon) * m_per_lon, (lat - city.lat) * 110574

                for name, layer in tile.items():
                    if name not in by_layer:
                        continue
                    extent = layer.get("extent", 4096)
                    for feat in layer["features"]:
                        props = feat.get("properties", {})
                        level = int(float(props.get("Var", props.get("HAZ", 0)) or 0))
                        if level not in (1, 2, 3) or feat["geometry"]["type"] not in ("Polygon", "MultiPolygon"):
                            continue
                        geom = make_valid(shape(feat["geometry"]))
                        by_layer[name][level].append(
                            transform(lambda x, y, e=extent: to_metres(x, y, extent=e), geom))

        centre, near, disc = Point(0, 0), Point(0, 0).buffer(NEAR_M), Point(0, 0).buffer(DISC_M)
        for name, (hazard, scenario) in LAYERS.items():
            unions = {lvl: unary_union(geoms) if geoms else None for lvl, geoms in by_layer[name].items()}
            at_centre = max((lvl for lvl, u in unions.items() if u is not None and u.contains(centre)), default=0)
            within_1km = max((lvl for lvl, u in unions.items() if u is not None and u.intersects(near)), default=0)
            medium_high = unary_union([u for lvl, u in unions.items() if u is not None and lvl >= 2])
            high = unions[3]
            pct_mh = 100 * medium_high.intersection(disc).area / disc.area if not medium_high.is_empty else 0.0
            pct_h = 100 * high.intersection(disc).area / disc.area if high is not None else 0.0
            rows.append((city.location_id, hazard, scenario, at_centre, within_1km, round(pct_mh, 1),
                         round(pct_h, 1), computed_at))

    with ctx.connect() as conn:
        upsert(conn, "hazards.city_hazard", COLS, rows, key=["location_id", "hazard", "scenario"])
    flagged = sum(1 for r in rows if r[4] >= 2)
    return f"{len(rows)} city-hazard rows for {len(LOCATIONS)} cities; {flagged} with medium or high hazard within 1 km"
