-- ═══════════════════════════════════════════════════════════════════════════
-- weather — OpenWeather data for Philippine cities, for BantAI
--
-- Loaded by scripts/ingest_openweather.py, which runs this file on every start:
-- every statement is idempotent. Registered in Zetaris as the WEATHER data source,
-- read-only, through the zetaris_ro role.
--
-- Times are timestamptz (UTC in storage); Philippine time is UTC+8.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS weather;

-- The cities the job polls. scripts/ingest_openweather.py owns the list and
-- upserts it on start, so edit it there.
CREATE TABLE IF NOT EXISTS weather.locations (
    location_id  text PRIMARY KEY,              -- slug, e.g. 'tacloban'
    name         text NOT NULL,
    province     text NOT NULL,                 -- 'Metro Manila' for NCR cities
    region       text NOT NULL,                 -- e.g. 'Region VIII (Eastern Visayas)'
    lat          double precision NOT NULL,
    lon          double precision NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Current weather, one row per location per OpenWeather observation time. OpenWeather
-- refreshes about every 10 minutes; the job polls hourly.
CREATE TABLE IF NOT EXISTS weather.observations (
    location_id   text NOT NULL REFERENCES weather.locations,
    observed_at   timestamptz NOT NULL,         -- OpenWeather's dt
    temp_c        real,
    feels_like_c  real,
    humidity_pct  smallint,
    pressure_hpa  smallint,                     -- sea level
    wind_speed_ms real,
    wind_gust_ms  real,
    wind_deg      smallint,                     -- direction the wind blows FROM
    clouds_pct    smallint,
    visibility_m  integer,                      -- capped at 10000
    rain_1h_mm    real,                         -- NULL when it has not rained
    rain_3h_mm    real,
    condition     text,                         -- e.g. 'Rain', 'Clouds', 'Thunderstorm'
    description   text,                         -- e.g. 'moderate rain'
    fetched_at    timestamptz NOT NULL,
    PRIMARY KEY (location_id, observed_at)
);
SELECT create_hypertable('weather.observations', 'observed_at', if_not_exists => TRUE);

-- The 5-day forecast in 3-hour steps. Each run overwrites the steps it returns, so a
-- step in the future is the latest forecast and a step in the past is the last
-- forecast made before it: compare with weather.observations to see how it verified.
CREATE TABLE IF NOT EXISTS weather.forecasts (
    location_id   text NOT NULL REFERENCES weather.locations,
    forecast_for  timestamptz NOT NULL,         -- the step's time (OpenWeather's dt)
    issued_at     timestamptz NOT NULL,         -- when the job fetched this forecast
    temp_c        real,
    feels_like_c  real,
    humidity_pct  smallint,
    pressure_hpa  smallint,
    wind_speed_ms real,
    wind_gust_ms  real,
    wind_deg      smallint,
    clouds_pct    smallint,
    rain_prob     real,                         -- probability of precipitation, 0 to 1
    rain_3h_mm    real,                         -- rain in the 3 hours up to forecast_for
    condition     text,
    description   text,
    PRIMARY KEY (location_id, forecast_for)
);
SELECT create_hypertable('weather.forecasts', 'forecast_for', if_not_exists => TRUE);

-- Air pollution, one row per location per observation. aqi is OpenWeather's index:
-- 1 good, 2 fair, 3 moderate, 4 poor, 5 very poor. Concentrations in µg/m³.
CREATE TABLE IF NOT EXISTS weather.air_quality (
    location_id   text NOT NULL REFERENCES weather.locations,
    observed_at   timestamptz NOT NULL,
    aqi           smallint,
    pm2_5         real,
    pm10          real,
    o3            real,
    no2           real,
    so2           real,
    co            real,
    nh3           real,
    fetched_at    timestamptz NOT NULL,
    PRIMARY KEY (location_id, observed_at)
);
SELECT create_hypertable('weather.air_quality', 'observed_at', if_not_exists => TRUE);
