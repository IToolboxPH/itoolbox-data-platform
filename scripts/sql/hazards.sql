-- ═══════════════════════════════════════════════════════════════════════════
-- hazards — earthquakes, disaster alerts and Project NOAH hazard per city
--
-- Registered in Zetaris as HAZARDS. Loaded by scripts/ingest/usgs.py, gdacs.py
-- and noah.py. Idempotent: run on every start.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE SCHEMA IF NOT EXISTS hazards;

-- USGS earthquake catalogue, magnitude 3+ in a box around the Philippines
-- (4-22°N, 116-128°E) since 2000. US public domain.
CREATE TABLE IF NOT EXISTS hazards.earthquakes (
    event_id             text PRIMARY KEY,         -- USGS id, e.g. 'us7000abcd'
    occurred_at          timestamptz NOT NULL,
    lat                  double precision NOT NULL,
    lon                  double precision NOT NULL,
    depth_km             real,
    magnitude            real,
    mag_type             text,                     -- e.g. 'mb', 'mww'
    place                text,                     -- USGS's description, e.g. '12 km SE of Davao'
    felt_reports         integer,                  -- "Did You Feel It?" responses
    max_intensity_mmi    real,                     -- ShakeMap modified Mercalli intensity
    pager_alert          text,                     -- green / yellow / orange / red
    tsunami_flag         boolean,
    significance         integer,                  -- USGS 0-1000+ composite
    nearest_location_id  text,                     -- the closest of weather.locations
    nearest_km           real,
    url                  text,
    updated_at           timestamptz
);
CREATE INDEX IF NOT EXISTS earthquakes_occurred_at ON hazards.earthquakes (occurred_at DESC);

-- GDACS (EC JRC and UN) alerts for events touching the Philippines, since 2015.
-- One row per event, holding its latest episode. Syndication allowed with credit.
CREATE TABLE IF NOT EXISTS hazards.disaster_alerts (
    event_type     text NOT NULL,                  -- TC cyclone, EQ earthquake, FL flood, VO volcano, DR drought, WF fire
    event_id       bigint NOT NULL,
    episode_id     bigint,
    name           text,                           -- e.g. 'CHAMPI-26'
    alert_level    text,                           -- Green / Orange / Red
    alert_score    real,
    severity       real,
    severity_unit  text,
    severity_text  text,
    from_date      timestamptz,
    to_date        timestamptz,
    is_current     boolean,
    countries      text,                           -- every affected country, comma-separated
    lat            double precision,
    lon            double precision,
    report_url     text,
    fetched_at     timestamptz NOT NULL,
    PRIMARY KEY (event_type, event_id)
);

-- Project NOAH hazard around each city in weather.locations, precomputed from
-- NOAH's zoom-14 vector tiles (UP NOAH Center, ODbL). Levels: 0 none, 1 low,
-- 2 medium, 3 high. Flood scenarios are rainfall return periods; storm surge
-- scenarios are advisory levels SSA 1 (2-3 m storm tide) to SSA 4 (above 5 m).
-- NOAH has gaps, and a layer missing for a province reads as 0: Tacloban's SSA 2
-- is empty although its SSA 1, 3 and 4 are not.
CREATE TABLE IF NOT EXISTS hazards.city_hazard (
    location_id          text NOT NULL,
    hazard               text NOT NULL,            -- flood, landslide, debris_flow, storm_surge
    scenario             text NOT NULL,            -- 5yr, 25yr, 100yr, ssa1..ssa4, or 'any'
    level_at_center      smallint NOT NULL,        -- at the city's centre point
    max_level_1km        smallint NOT NULL,        -- highest level within 1 km
    pct_medium_high_2km  real NOT NULL,            -- % of the 2 km disc at level 2 or 3
    pct_high_2km         real NOT NULL,            -- % of the 2 km disc at level 3
    computed_at          timestamptz NOT NULL,
    PRIMARY KEY (location_id, hazard, scenario)
);
