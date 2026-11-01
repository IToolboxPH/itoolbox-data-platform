"""NASA POWER daily weather history for each city, from 1991.

The first run fetches the whole history per city in one request; later runs re-read
the last 45 days, because POWER fills in recent days over a few weeks.
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from ingest.cities import LOCATIONS, upsert_locations
from ingest.common import Context, get, number, upsert

NAME = "nasa_power"
EVERY = 86400
SCHEMAS = ["weather"]

API = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = {
    "PRECTOTCORR": "rain_mm", "T2M": "temp_mean_c", "T2M_MAX": "temp_max_c", "T2M_MIN": "temp_min_c",
    "RH2M": "humidity_pct", "WS10M": "wind_mean_ms", "WS10M_MAX": "wind_max_ms",
}
HISTORY_FROM = date(1991, 1, 1)
COLS = ["location_id", "day", *PARAMS.values()]


def run(ctx: Context) -> str:
    with ctx.connect() as conn:
        upsert_locations(conn)
        latest = dict(conn.execute(
            "SELECT location_id, max(day) FROM weather.daily_history GROUP BY location_id").fetchall())
    end = date.today() - timedelta(days=1)
    total = 0
    for city in LOCATIONS:
        start = max(HISTORY_FROM, latest[city.location_id] - timedelta(days=45)) if city.location_id in latest \
            else HISTORY_FROM
        body = get(ctx.http, API, timeout=180, params={
            "parameters": ",".join(PARAMS), "community": "AG", "latitude": city.lat, "longitude": city.lon,
            "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON",
            "time-standard": "LST",
        }).json()
        series = body["properties"]["parameter"]
        days = sorted(next(iter(series.values())).keys())
        rows = [(city.location_id, date(int(d[:4]), int(d[4:6]), int(d[6:])),
                 *(number(series[p].get(d)) for p in PARAMS)) for d in days]
        with ctx.connect() as conn:
            total += upsert(conn, "weather.daily_history", COLS, rows, key=["location_id", "day"])
        time.sleep(1)
    return f"{total} city-days for {len(LOCATIONS)} cities, through {end}"
