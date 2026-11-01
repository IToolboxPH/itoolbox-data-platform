# itoolbox-data-platform

**IToolbox's local data stack: TimescaleDB, JupyterLab and ingestion.**

BantAI's data lands here first and is governed here, locally, before anything moves
to the cloud. Load data here and explore it in notebooks. When BantAI should be able
to query it, register it as a data source in Zetaris
([itoolbox-zetaris-platform](https://github.com/IToolboxPH/itoolbox-zetaris-platform));
the agent reads data only through Zetaris.

| Repo | Contains |
| --- | --- |
| `itoolbox-backend` | FastAPI service and the BantAI agent |
| `itoolbox-frontend` | Next.js web app |
| `itoolbox-zetaris-platform` | Zetaris: query engine, catalog, API |
| **itoolbox-data-platform** (this) | TimescaleDB, JupyterLab and ingestion jobs |

[DATA_SOURCES.md](DATA_SOURCES.md) lists the public data BantAI can use, from PAGASA,
DOST and other agencies, LGUs, NGOs and international open data, with how to get each
and the order to add them in.

## Running it

```bash
cp .env.example .env                          # then set OPENWEATHER_API_KEY and BAGYO_APP_SECRET
docker compose up -d --build                  # first start builds BagyoAPI from GitHub (a few minutes)
docker compose logs itoolbox-jupyter          # the Jupyter token, unless JUPYTER_TOKEN is set
docker compose logs -f itoolbox-ingest        # one line per job run
```

| Port | Service | Bound to |
| --- | --- | --- |
| 5436 | TimescaleDB (`itoolbox_db`) | 127.0.0.1 |
| 8890 | JupyterLab | 127.0.0.1 |
| 3200 | BagyoAPI (`/docs` for its API reference) | 127.0.0.1 |

## Data

Every source is public. Each schema is one Zetaris data source; BantAI reads them
only through Zetaris.

| Schema · Zetaris source | Tables | From | Refresh |
| --- | --- | --- | --- |
| `weather` · `WEATHER` | `locations`, `observations`, `forecasts`, `air_quality` | OpenWeather free APIs, 24 cities | hourly |
| | `daily_history` | NASA POWER, daily since 1991 | daily |
| `bulletins` · `BULLETINS` | `cyclones`, `bulletins`, `wind_signals`, `rainfall_advisories`, `rainfall_areas` | PAGASA, parsed by the self-hosted BagyoAPI | every 30 min |
| `hazards` · `HAZARDS` | `earthquakes` | USGS, magnitude 3+ since 2000 | hourly |
| | `disaster_alerts` | GDACS, Philippine events since 2015 | hourly |
| | `city_hazard` | Project NOAH flood, landslide and storm surge around each city | yearly |
| `typhoons` · `TYPHOONS` | `storms`, `track_points`, `city_passes` | IBTrACS, storms inside PAR since 1951 | weekly |
| `reference` · `REFERENCE` | `regions`, `provinces`, `cities_municipalities`, `province_population` | PSGC (PSA), and PSA population projections via HDX | monthly |
| | `facilities` | OpenStreetMap, within 5 km of each city | monthly |

Sources join on `location_id` (the 24 cities) and `psgc_code` (PSA's 9-digit
codes). Each table's columns are documented in [scripts/sql/](scripts/sql/).

### Ingestion

`itoolbox-ingest` runs [scripts/run_ingest.py](scripts/run_ingest.py), which runs each
job in [scripts/ingest/](scripts/ingest/) when it is due. A failing job is logged and
retried 15 minutes later; the others carry on. Jobs upsert, so a rerun never
duplicates rows. The cities are in [scripts/ingest/cities.py](scripts/ingest/cities.py):
add one there and every job picks it up on its next run.

```bash
# when each job last ran, and its last error. In Git Bash, prefix MSYS_NO_PATHCONV=1
# or it rewrites /workspace into a Windows path.
docker compose exec itoolbox-ingest python /workspace/scripts/run_ingest.py --status
# run jobs now (names from --status, or all)
docker compose run --rm --entrypoint python itoolbox-ingest /workspace/scripts/run_ingest.py --once noah usgs_earthquakes
```

### BagyoAPI

The `bagyo-*` services self-host [BagyoAPI](https://github.com/edwardguevarra/bagyo-api)
(MIT), built from the commit pinned in `compose.yaml`; none of its code lives here.
Its worker scrapes PAGASA's public bulletins on its own polite schedule. It is
unofficial and can lag or misparse, so the agent defers life-safety calls to PAGASA.
Its seed loads six real 2026 bulletins and a demo account, so keep port 3200 off any
shared network. Set `BAGYO_LIVE_SCRAPING=false` to stop live scraping.

### Zetaris

Zetaris reads each schema through `zetaris_ro`, a read-only role in this database
(`SELECT` on the registered schemas only). How the sources were registered is
recorded in the harness repo, under `datasources/`.

### Credits

Weather data provided by [OpenWeather](https://openweathermap.org/). Daily history
from NASA POWER. Bulletins from DOST-PAGASA via BagyoAPI. Earthquakes from USGS.
Alerts from GDACS (EC JRC). Hazard maps © UP NOAH Center, ODbL. Tracks from IBTrACS
(NOAA NCEI). Places and population from PSA, via psgc.gitlab.io and OCHA HDX (CC
BY-IGO). Facilities © OpenStreetMap contributors, ODbL.

## Notes

Notebooks see `notebooks/`, `data/` and `scripts/` under `/workspace`, and reach the
database at `TIMESCALE_URL` (host `itoolbox-timescaledb` inside the compose network).
`data/` is gitignored.

The Jupyter image pins its whole dependency tree in `constraints-jupyter.txt`; add
direct dependencies to `requirements-jupyter.txt`. The ingest service reuses that
image.

The compose project is `itoolbox_data-platform`; Docker Desktop lists it with the
other IToolbox stacks by the `itoolbox_` prefix. `docker compose down -v` deletes its
volume, `itoolbox_tsdata`, and with it the database.
