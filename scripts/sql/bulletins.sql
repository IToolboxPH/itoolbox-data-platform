-- ═══════════════════════════════════════════════════════════════════════════
-- bulletins — PAGASA tropical cyclone bulletins and rainfall advisories
--
-- Registered in Zetaris as BULLETINS. Loaded by scripts/ingest/bagyo.py from the
-- self-hosted BagyoAPI, which parses PAGASA's public bulletins (DOST-PAGASA is
-- the source; BagyoAPI is unofficial and may lag or misparse). Rows accumulate:
-- a bulletin is never deleted, so the history stays queryable after a storm.
-- Locations are PSA 9-digit PSGC codes, joinable to reference.* and
-- weather.locations.psgc_code.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS bulletins;

CREATE TABLE IF NOT EXISTS bulletins.cyclones (
    cyclone_id          text PRIMARY KEY,          -- BagyoAPI id
    pagasa_name         text,                      -- local name, e.g. 'FRANCISCO'
    international_name  text,                      -- e.g. 'MEKKHALA'; joins to typhoons.storms.name
    category            text,                      -- TD, TS, STS, TY, STY
    category_label      text,
    status              text,                      -- e.g. ACTIVE, DISSIPATED, EXITED_PAR
    season_year         smallint,
    first_bulletin_at   timestamptz,
    last_bulletin_at    timestamptz,
    bulletin_count      integer,
    fetched_at          timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS bulletins.bulletins (
    bulletin_id         text PRIMARY KEY,
    cyclone_id          text NOT NULL,
    bulletin_number     integer,
    is_final            boolean,
    issued_at           timestamptz NOT NULL,
    next_bulletin_at    timestamptz,
    center_lat          double precision,          -- the storm's centre when issued
    center_lon          double precision,
    max_winds_kph       real,
    gustiness_kph       real,
    pressure_hpa        real,
    movement_direction  text,
    movement_speed_kph  real,
    source_url          text,                      -- the PAGASA document it was parsed from
    fetched_at          timestamptz NOT NULL
);

-- Tropical Cyclone Wind Signals raised by a bulletin: one row per area and level.
CREATE TABLE IF NOT EXISTS bulletins.wind_signals (
    bulletin_id         text NOT NULL,
    signal_level        smallint NOT NULL,         -- 1 to 5
    location_name       text NOT NULL,
    psgc_code           text,                      -- NULL when the area name could not be resolved
    location_type       text,                      -- PROVINCE, CITY, MUNICIPALITY, ...
    partial_descriptor  text,                      -- e.g. 'northern portion', when only part is under signal
    PRIMARY KEY (bulletin_id, signal_level, location_name)
);

-- Rainfall advisories (yellow, orange, red), kept after they expire.
CREATE TABLE IF NOT EXISTS bulletins.rainfall_advisories (
    advisory_id         text PRIMARY KEY,
    issued_at           timestamptz,
    expires_at          timestamptz,
    region              text,
    level               text,                      -- YELLOW, ORANGE, RED
    fetched_at          timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS bulletins.rainfall_areas (
    advisory_id         text NOT NULL,
    area_name           text NOT NULL,
    psgc_code           text,
    PRIMARY KEY (advisory_id, area_name)
);
