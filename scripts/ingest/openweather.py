"""OpenWeather: current weather, 5-day/3-hour forecast and air pollution per city.

Free-plan APIs only (One Call needs a separate subscription). Three calls per city
per run; the free tier allows 60 a minute, so calls are paced.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ingest.cities import LOCATIONS, upsert_locations
from ingest.common import Context, get, upsert, utcnow

NAME = "openweather"
EVERY = 3600
SCHEMAS = ["weather"]

API = "https://api.openweathermap.org/data/2.5"
CALL_INTERVAL_S = 1.1


def _ts(unix: int) -> datetime:
    return datetime.fromtimestamp(unix, tz=timezone.utc)


def _observation(location_id: str, body: dict, fetched_at: datetime) -> tuple:
    main, wind, w = body.get("main", {}), body.get("wind", {}), (body.get("weather") or [{}])[0]
    rain = body.get("rain", {})
    return (location_id, _ts(body["dt"]), main.get("temp"), main.get("feels_like"), main.get("humidity"),
            main.get("pressure"), wind.get("speed"), wind.get("gust"), wind.get("deg"),
            body.get("clouds", {}).get("all"), body.get("visibility"), rain.get("1h"), rain.get("3h"),
            w.get("main"), w.get("description"), fetched_at)


def _forecast(location_id: str, body: dict, issued_at: datetime) -> list[tuple]:
    rows = []
    for step in body.get("list", []):
        main, wind, w = step.get("main", {}), step.get("wind", {}), (step.get("weather") or [{}])[0]
        rows.append((location_id, _ts(step["dt"]), issued_at, main.get("temp"), main.get("feels_like"),
                     main.get("humidity"), main.get("pressure"), wind.get("speed"), wind.get("gust"),
                     wind.get("deg"), step.get("clouds", {}).get("all"), step.get("pop"),
                     step.get("rain", {}).get("3h"), w.get("main"), w.get("description")))
    return rows


def _air(location_id: str, body: dict, fetched_at: datetime) -> tuple | None:
    if not body.get("list"):
        return None
    item = body["list"][0]
    c = item.get("components", {})
    return (location_id, _ts(item["dt"]), item.get("main", {}).get("aqi"), c.get("pm2_5"), c.get("pm10"),
            c.get("o3"), c.get("no2"), c.get("so2"), c.get("co"), c.get("nh3"), fetched_at)


OBS_COLS = ["location_id", "observed_at", "temp_c", "feels_like_c", "humidity_pct", "pressure_hpa",
            "wind_speed_ms", "wind_gust_ms", "wind_deg", "clouds_pct", "visibility_m", "rain_1h_mm",
            "rain_3h_mm", "condition", "description", "fetched_at"]
FCST_COLS = ["location_id", "forecast_for", "issued_at", "temp_c", "feels_like_c", "humidity_pct",
             "pressure_hpa", "wind_speed_ms", "wind_gust_ms", "wind_deg", "clouds_pct", "rain_prob",
             "rain_3h_mm", "condition", "description"]
AIR_COLS = ["location_id", "observed_at", "aqi", "pm2_5", "pm10", "o3", "no2", "so2", "co", "nh3", "fetched_at"]


def run(ctx: Context) -> str:
    key = ctx.env.get("OPENWEATHER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENWEATHER_API_KEY is not set: add it to .env, then `docker compose up -d itoolbox-ingest`")

    def call(path: str, lat: float, lon: float) -> dict:
        time.sleep(CALL_INTERVAL_S)
        return get(ctx.http, f"{API}/{path}",
                   params={"lat": lat, "lon": lon, "units": "metric", "appid": key}).json()

    obs, fcst, air, failed = [], [], [], []
    for city in LOCATIONS:
        fetched_at = utcnow()
        try:
            obs.append(_observation(city.location_id, call("weather", city.lat, city.lon), fetched_at))
            fcst.extend(_forecast(city.location_id, call("forecast", city.lat, city.lon), fetched_at))
            row = _air(city.location_id, call("air_pollution", city.lat, city.lon), fetched_at)
            if row:
                air.append(row)
        except Exception as exc:  # one city failing must not lose the others
            failed.append(f"{city.name} ({exc})")

    with ctx.connect() as conn:
        upsert_locations(conn)
        upsert(conn, "weather.observations", OBS_COLS, obs, key=["location_id", "observed_at"], update=False)
        upsert(conn, "weather.forecasts", FCST_COLS, fcst, key=["location_id", "forecast_for"])
        upsert(conn, "weather.air_quality", AIR_COLS, air, key=["location_id", "observed_at"], update=False)
    summary = f"{len(obs)} observations, {len(fcst)} forecast steps, {len(air)} air readings"
    if failed:
        summary += f"; failed: {', '.join(failed)}"
    if not obs:
        raise RuntimeError(summary)
    return summary
