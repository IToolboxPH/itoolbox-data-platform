-- ═══════════════════════════════════════════════════════════════════════════
-- typhoons — tropical cyclone history inside PAR, from IBTrACS
--
-- Registered in Zetaris as TYPHOONS. Loaded by scripts/ingest/ibtracs.py, which
-- reloads every table in one transaction. IBTrACS v04r01 (NOAA NCEI): "may be
-- redistributed and used without restriction". Winds are in knots (×1.852 for
-- km/h), from the US agencies where they report, else the WMO agency (JMA).
-- Names are international names; PAGASA's local names are not in IBTrACS.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS typhoons;

-- One row per storm that entered the Philippine Area of Responsibility, 1951 on.
CREATE TABLE IF NOT EXISTS typhoons.storms (
    sid                text PRIMARY KEY,           -- IBTrACS storm id
    season             smallint NOT NULL,
    name               text,                       -- international name; 'NOT_NAMED' if none
    entered_par_at     timestamptz,
    left_par_at        timestamptz,
    max_wind_kt_in_par real,
    min_pressure_hpa_in_par real,
    max_category_in_par smallint,                  -- Saffir-Simpson, -5..5 (negatives are pre-tropical-storm stages)
    over_ph_land       boolean                     -- any PAR point over land inside the Philippines' bounding box
);

-- Every 3-hourly track point of those storms, inside or outside PAR.
CREATE TABLE IF NOT EXISTS typhoons.track_points (
    sid            text NOT NULL,
    observed_at    timestamptz NOT NULL,
    lat            double precision NOT NULL,
    lon            double precision NOT NULL,
    wind_kt        real,
    pressure_hpa   real,
    category       smallint,                       -- Saffir-Simpson where reported
    nature         text,                           -- TS tropical, ET extratropical, DS disturbance, ...
    dist2land_km   real,
    in_par         boolean NOT NULL,
    PRIMARY KEY (sid, observed_at)
);

-- Each storm's closest pass to each city in weather.locations, within 300 km.
-- "How often does Tacloban get hit" is a COUNT over this table.
CREATE TABLE IF NOT EXISTS typhoons.city_passes (
    location_id    text NOT NULL,
    sid            text NOT NULL,
    closest_km     real NOT NULL,
    closest_at     timestamptz NOT NULL,
    wind_kt_then   real,
    PRIMARY KEY (location_id, sid)
);
