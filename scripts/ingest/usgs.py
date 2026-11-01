"""USGS earthquake catalogue around the Philippines, magnitude 3 and up.

The first run backfills from 2000, a year per request (the API caps a response at
20,000 events). Later runs re-read the last 30 days, which also picks up revised
magnitudes and locations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingest.cities import nearest
from ingest.common import Context, get, upsert, utcnow

NAME = "usgs_earthquakes"
EVERY = 3600
SCHEMAS = ["weather", "hazards"]

API = "https://earthquake.usgs.gov/fdsnws/event/1/query"
BOX = {"minlatitude": 4, "maxlatitude": 22, "minlongitude": 116, "maxlongitude": 128}
MIN_MAGNITUDE = 3.0
BACKFILL_FROM = 2000

COLS = ["event_id", "occurred_at", "lat", "lon", "depth_km", "magnitude", "mag_type", "place",
        "felt_reports", "max_intensity_mmi", "pager_alert", "tsunami_flag", "significance",
        "nearest_location_id", "nearest_km", "url", "updated_at"]


def _ms(value) -> datetime | None:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc) if value is not None else None


def _fetch(ctx: Context, start: datetime, end: datetime) -> list[tuple]:
    body = get(ctx.http, API, timeout=120, params={
        "format": "geojson", "starttime": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "endtime": end.strftime("%Y-%m-%dT%H:%M:%S"), "minmagnitude": MIN_MAGNITUDE,
        "orderby": "time-asc", "limit": 20000, **BOX,
    }).json()
    rows = []
    for f in body.get("features", []):
        p, (lon, lat, depth) = f["properties"], f["geometry"]["coordinates"][:3]
        loc, km = nearest(lat, lon)
        rows.append((f["id"], _ms(p["time"]), lat, lon, depth, p.get("mag"), p.get("magType"), p.get("place"),
                     p.get("felt"), p.get("mmi"), p.get("alert"), bool(p.get("tsunami")), p.get("sig"),
                     loc, round(km, 1), p.get("url"), _ms(p.get("updated"))))
    return rows


def run(ctx: Context) -> str:
    with ctx.connect() as conn:
        have = conn.execute("SELECT count(*) FROM hazards.earthquakes").fetchone()[0]
    now = utcnow()
    if have:
        windows = [(now - timedelta(days=30), now)]
    else:
        windows = [(datetime(y, 1, 1, tzinfo=timezone.utc), min(datetime(y + 1, 1, 1, tzinfo=timezone.utc), now))
                   for y in range(BACKFILL_FROM, now.year + 1)]
    total = 0
    with ctx.connect() as conn:
        for start, end in windows:
            total += upsert(conn, "hazards.earthquakes", COLS, _fetch(ctx, start, end), key=["event_id"])
            conn.commit()
    return f"{total} events {'(backfill since %d)' % BACKFILL_FROM if not have else 'in the last 30 days'}"
