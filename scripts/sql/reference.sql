-- ═══════════════════════════════════════════════════════════════════════════
-- reference — places, population and facilities
--
-- Registered in Zetaris as REFERENCE. Loaded by scripts/ingest/reference.py
-- (PSGC, population) and osm.py (facilities). PSGC codes are PSA's 9-digit codes,
-- the same ones weather.locations.psgc_code holds.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS reference;

-- Philippine Standard Geographic Code (PSA), via psgc.gitlab.io.
CREATE TABLE IF NOT EXISTS reference.regions (
    psgc_code      text PRIMARY KEY,
    psgc10_code    text,                           -- the 10-digit code PSA has used since 2023
    name           text NOT NULL,                  -- e.g. 'Region VIII (Eastern Visayas)'
    short_name     text                            -- e.g. 'Eastern Visayas'
);
CREATE TABLE IF NOT EXISTS reference.provinces (
    psgc_code      text PRIMARY KEY,
    psgc10_code    text,
    name           text NOT NULL,
    region_code    text NOT NULL
);
CREATE TABLE IF NOT EXISTS reference.cities_municipalities (
    psgc_code      text PRIMARY KEY,
    psgc10_code    text,
    name           text NOT NULL,                  -- e.g. 'City of Tacloban'
    is_city        boolean NOT NULL,
    is_capital     boolean NOT NULL,               -- capital of its province
    province_code  text,                           -- NULL in Metro Manila
    region_code    text NOT NULL
);

-- PSA population projections, per province (and Metro Manila district) and year,
-- from OCHA's COD-PS on HDX (CC BY-IGO). Boundaries and names follow that dataset,
-- so a few are older than PSGC's (e.g. ARMM rather than BARMM).
CREATE TABLE IF NOT EXISTS reference.province_population (
    psgc_code      text NOT NULL,                  -- ADM2_PCODE without its 'PH' prefix
    name           text NOT NULL,
    region_name    text,
    year           smallint NOT NULL,
    population     integer NOT NULL,
    female         integer,
    male           integer,
    age_0_14       integer,
    age_65_plus    integer,
    PRIMARY KEY (psgc_code, year)
);

-- Hospitals, clinics, schools (often evacuation centres), fire and police stations
-- and assembly points within 5 km of each city in weather.locations, from
-- OpenStreetMap (© OpenStreetMap contributors, ODbL).
CREATE TABLE IF NOT EXISTS reference.facilities (
    osm_id         text NOT NULL,                  -- e.g. 'node/123', 'way/456'
    location_id    text NOT NULL,
    kind           text NOT NULL,                  -- hospital, clinic, school, fire_station, police, assembly_point
    name           text,
    lat            double precision NOT NULL,
    lon            double precision NOT NULL,
    distance_km    real NOT NULL,
    fetched_at     timestamptz NOT NULL,
    PRIMARY KEY (osm_id, location_id)
);
