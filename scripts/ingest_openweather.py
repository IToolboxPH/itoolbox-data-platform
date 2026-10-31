"""Load OpenWeather data for Philippine cities into the weather schema, for BantAI.

Each run fetches, for every city in LOCATIONS, through OpenWeather's free APIs:

  current weather          -> weather.observations
  5-day/3-hour forecast    -> weather.forecasts   (latest forecast per step)
  air pollution            -> weather.air_quality

Rows are upserted, so a rerun never duplicates anything.

  python scripts/ingest_openweather.py               # one run
  python scripts/ingest_openweather.py --every 3600  # run hourly until stopped

Reads OPENWEATHER_API_KEY and TIMESCALE_URL from the environment. The compose
service itoolbox-ingest runs it hourly; see README.md.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests

API = "https://api.openweathermap.org/data/2.5"
SCHEMA_SQL = Path(__file__).parent / "sql" / "weather.sql"

# The free tier allows 60 calls a minute; a run makes three per city.
CALL_INTERVAL_S = 1.1

# Starter list: a major city in every region, weighted toward the typhoon belt
# (Bicol, Eastern Visayas, Caraga). Coordinates are city centres, checked against
# OpenWeather's geocoder. Edit freely; the job upserts the list on every start.
#            location_id               name                      province               region
LOCATIONS = [
    ("manila", "Manila", "Metro Manila", "NCR", 14.5904, 120.9804),
    ("quezon-city", "Quezon City", "Metro Manila", "NCR", 14.6511, 121.0486),
    ("baguio", "Baguio", "Benguet", "CAR", 16.4120, 120.5934),
    ("laoag", "Laoag", "Ilocos Norte", "Region I (Ilocos)", 18.1973, 120.5935),
    ("tuguegarao", "Tuguegarao", "Cagayan", "Region II (Cagayan Valley)", 17.6119, 121.7300),
    ("san-fernando-pampanga", "City of San Fernando", "Pampanga", "Region III (Central Luzon)", 15.0283, 120.6938),
    ("calamba", "Calamba", "Laguna", "Region IV-A (CALABARZON)", 14.2091, 121.1652),
    ("calapan", "Calapan", "Oriental Mindoro", "MIMAROPA", 13.4146, 121.1795),
    ("puerto-princesa", "Puerto Princesa", "Palawan", "MIMAROPA", 9.7399, 118.7438),
    ("legazpi", "Legazpi", "Albay", "Region V (Bicol)", 13.1389, 123.7343),
    ("naga", "Naga", "Camarines Sur", "Region V (Bicol)", 13.6240, 123.1850),
    ("virac", "Virac", "Catanduanes", "Region V (Bicol)", 13.5804, 124.2312),
    ("iloilo-city", "Iloilo City", "Iloilo", "Region VI (Western Visayas)", 10.6927, 122.5737),
    ("bacolod", "Bacolod", "Negros Occidental", "NIR (Negros Island)", 10.6763, 122.9514),
    ("cebu-city", "Cebu City", "Cebu", "Region VII (Central Visayas)", 10.2936, 123.9019),
    ("tacloban", "Tacloban", "Leyte", "Region VIII (Eastern Visayas)", 11.2436, 125.0080),
    ("catarman", "Catarman", "Northern Samar", "Region VIII (Eastern Visayas)", 12.4997, 124.6366),
    ("surigao-city", "Surigao City", "Surigao del Norte", "Caraga", 9.7905, 125.4936),
    ("butuan", "Butuan", "Agusan del Norte", "Caraga", 8.9483, 125.5369),
    ("cagayan-de-oro", "Cagayan de Oro", "Misamis Oriental", "Region X (Northern Mindanao)", 8.4756, 124.6422),
    ("davao-city", "Davao City", "Davao del Sur", "Region XI (Davao)", 7.0648, 125.6081),
    ("zamboanga-city", "Zamboanga City", "Zamboanga del Sur", "Region IX (Zamboanga Peninsula)", 6.9047, 122.0765),
    ("general-santos", "General Santos", "South Cotabato", "Region XII (SOCCSKSARGEN)", 6.1122, 125.1722),
    ("cotabato-city", "Cotabato City", "Maguindanao del Norte", "BARMM", 7.2238, 124.2467),
]


def log(msg: str) -> None:
    print(f"[ingest_openweather {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%SZ}] {msg}", flush=True)


def ts(unix: int) -> datetime:
    return datetime.fromtimestamp(unix, tz=timezone.utc)


class OpenWeather:
    def __init__(self, key: str) -> None:
        self._key = key
        self._session = requests.Session()
        self._last_call = 0.0

    def get(self, path: str, lat: float, lon: float) -> dict:
        """GET with the free tier's pacing; retries 429 and 5xx with backoff."""
        for attempt in range(4):
            wait = CALL_INTERVAL_S - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
            resp = self._session.get(
                f"{API}/{path}",
                params={"lat": lat, "lon": lon, "units": "metric", "appid": self._key},
                timeout=30,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(2 ** attempt * 5)
                continue
            if resp.status_code != 200:
                # The body is OpenWeather's message; the URL would carry the key.
                raise RuntimeError(f"{path}: HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        raise RuntimeError(f"{path}: still failing after retries (HTTP {resp.status_code})")


def observation_row(location_id: str, body: dict, fetched_at: datetime) -> tuple:
    main, wind, weather = body.get("main", {}), body.get("wind", {}), (body.get("weather") or [{}])[0]
    return (
        location_id, ts(body["dt"]), main.get("temp"), main.get("feels_like"), main.get("humidity"),
        main.get("pressure"), wind.get("speed"), wind.get("gust"), wind.get("deg"),
        body.get("clouds", {}).get("all"), body.get("visibility"),
        body.get("rain", {}).get("1h"), body.get("rain", {}).get("3h"),
        weather.get("main"), weather.get("description"), fetched_at,
    )


def forecast_rows(location_id: str, body: dict, issued_at: datetime) -> list[tuple]:
    rows = []
    for step in body.get("list", []):
        main, wind, weather = step.get("main", {}), step.get("wind", {}), (step.get("weather") or [{}])[0]
        rows.append((
            location_id, ts(step["dt"]), issued_at, main.get("temp"), main.get("feels_like"),
            main.get("humidity"), main.get("pressure"), wind.get("speed"), wind.get("gust"),
            wind.get("deg"), step.get("clouds", {}).get("all"), step.get("pop"),
            step.get("rain", {}).get("3h"), weather.get("main"), weather.get("description"),
        ))
    return rows


def air_row(location_id: str, body: dict, fetched_at: datetime) -> tuple | None:
    if not body.get("list"):
        return None
    item = body["list"][0]
    c = item.get("components", {})
    return (
        location_id, ts(item["dt"]), item.get("main", {}).get("aqi"), c.get("pm2_5"), c.get("pm10"),
        c.get("o3"), c.get("no2"), c.get("so2"), c.get("co"), c.get("nh3"), fetched_at,
    )


UPSERT_LOCATION = """
INSERT INTO weather.locations (location_id, name, province, region, lat, lon)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (location_id) DO UPDATE SET name = EXCLUDED.name, province = EXCLUDED.province,
    region = EXCLUDED.region, lat = EXCLUDED.lat, lon = EXCLUDED.lon, updated_at = now()
"""
UPSERT_OBSERVATION = """
INSERT INTO weather.observations VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (location_id, observed_at) DO NOTHING
"""
UPSERT_FORECAST = """
INSERT INTO weather.forecasts VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (location_id, forecast_for) DO UPDATE SET issued_at = EXCLUDED.issued_at,
    temp_c = EXCLUDED.temp_c, feels_like_c = EXCLUDED.feels_like_c, humidity_pct = EXCLUDED.humidity_pct,
    pressure_hpa = EXCLUDED.pressure_hpa, wind_speed_ms = EXCLUDED.wind_speed_ms,
    wind_gust_ms = EXCLUDED.wind_gust_ms, wind_deg = EXCLUDED.wind_deg, clouds_pct = EXCLUDED.clouds_pct,
    rain_prob = EXCLUDED.rain_prob, rain_3h_mm = EXCLUDED.rain_3h_mm, condition = EXCLUDED.condition,
    description = EXCLUDED.description
"""
UPSERT_AIR = """
INSERT INTO weather.air_quality VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (location_id, observed_at) DO NOTHING
"""


def prepare(db_url: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        with conn.cursor() as cur:
            cur.executemany(UPSERT_LOCATION, LOCATIONS)


def run_once(db_url: str, owm: OpenWeather) -> bool:
    obs, fcst, air, failures = [], [], [], []
    for location_id, name, _province, _region, lat, lon in LOCATIONS:
        fetched_at = datetime.now(timezone.utc)
        try:
            obs.append(observation_row(location_id, owm.get("weather", lat, lon), fetched_at))
            fcst.extend(forecast_rows(location_id, owm.get("forecast", lat, lon), fetched_at))
            row = air_row(location_id, owm.get("air_pollution", lat, lon), fetched_at)
            if row:
                air.append(row)
        except Exception as exc:  # one city failing must not lose the others
            failures.append(f"{name}: {exc}")

    with psycopg.connect(db_url) as conn, conn.cursor() as cur:
        cur.executemany(UPSERT_OBSERVATION, obs)
        cur.executemany(UPSERT_FORECAST, fcst)
        cur.executemany(UPSERT_AIR, air)

    log(f"{len(obs)} observations, {len(fcst)} forecast steps, {len(air)} air readings"
        f" for {len(LOCATIONS)} cities" + (f"; {len(failures)} failed" if failures else ""))
    for failure in failures:
        log(f"  {failure}")
    return not failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--every", type=int, metavar="SECONDS",
                        help="repeat at this interval instead of running once")
    args = parser.parse_args()

    db_url = os.environ.get("TIMESCALE_URL")
    if not db_url:
        log("TIMESCALE_URL is not set")
        return 2
    key = os.environ.get("OPENWEATHER_API_KEY", "").strip()
    if not key:
        log("OPENWEATHER_API_KEY is not set: add it to .env, then `docker compose up -d itoolbox-ingest`")
        # Idle rather than exit, so the compose service does not restart in a loop.
        if args.every:
            while True:
                time.sleep(3600)
        return 2

    prepare(db_url)
    owm = OpenWeather(key)
    if not args.every:
        return 0 if run_once(db_url, owm) else 1
    while True:
        started = time.monotonic()
        try:
            run_once(db_url, owm)
        except Exception as exc:  # a database hiccup: log it and try again next round
            log(f"run failed: {exc}")
        time.sleep(max(60, args.every - (time.monotonic() - started)))


if __name__ == "__main__":
    sys.exit(main())
