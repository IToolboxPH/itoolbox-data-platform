# itoolbox-data-platform

**IToolbox's local data stack: TimescaleDB, JupyterLab and ingestion.**

BantAI's data lands here first and is governed here, locally, before anything moves
to the cloud. Load data here and explore it in notebooks. When BantAI should be able
to query it, register it as a data source in Zetaris
([itoolbox-zetaris-data-harness](https://github.com/IToolboxPH/itoolbox-zetaris-data-harness));
the agent reads data only through Zetaris.

| Repo | Contains |
| --- | --- |
| `itoolbox-backend` | FastAPI service and the BantAI agent |
| `itoolbox-frontend` | Next.js web app |
| `itoolbox-zetaris-data-harness` | Zetaris: query engine, catalog, API |
| **itoolbox-data-platform** (this) | TimescaleDB, JupyterLab and ingestion jobs |

[DATA_SOURCES.md](DATA_SOURCES.md) lists the public data BantAI can use, from PAGASA,
DOST and other agencies, LGUs, NGOs and international open data, with how to get each
and the order to add them in.

## Running it

```bash
cp .env.example .env                          # then set OPENWEATHER_API_KEY
docker compose up -d                          # TimescaleDB :5436, Jupyter :8890, hourly ingest
docker compose logs itoolbox-jupyter          # the Jupyter token, unless JUPYTER_TOKEN is set
docker compose logs -f itoolbox-ingest        # one line per ingest run
```

| Port | Service | Bound to |
| --- | --- | --- |
| 5436 | TimescaleDB (`itoolbox_db`) | 127.0.0.1 |
| 8890 | JupyterLab | 127.0.0.1 |

## Data

| Schema | Zetaris source | What | Loaded by |
| --- | --- | --- | --- |
| `weather` | `WEATHER` | Current weather, 5-day/3-hour forecast and air quality for 24 Philippine cities, from OpenWeather's free APIs | `itoolbox-ingest`, hourly: [scripts/ingest_openweather.py](scripts/ingest_openweather.py) |

The tables are defined in [scripts/sql/weather.sql](scripts/sql/weather.sql), and the
script upserts, so rerunning it never duplicates rows. To add a city, add it to
`LOCATIONS` in the script; the job picks it up on its next start. Run it once by hand
with:

```bash
docker compose run --rm --entrypoint python itoolbox-ingest /workspace/scripts/ingest_openweather.py
```

Zetaris reads each schema through `zetaris_ro`, a read-only role in this database
(`SELECT` on the registered schemas only). How it was registered is recorded in the
harness repo, under `datasources/`.

Weather data provided by [OpenWeather](https://openweathermap.org/).

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
