# BantAI data sources

Public data BantAI can use, from PAGASA, DOST, other government agencies, LGUs, NGOs
and international open data. Researched October 2026.

Every source follows the same path: it lands in this repo's TimescaleDB first and is
governed here, locally, then gets registered in Zetaris
([itoolbox-zetaris-data-harness](https://github.com/IToolboxPH/itoolbox-zetaris-data-harness))
as one data source per Postgres schema. BantAI reads it only through Zetaris.

**The short answer on PAGASA:** there is no public PAGASA developer API.

- **Live bulletins** are public. They're on PAGASA's site, and open-source parsers turn them into data.
- **Historical station data** needs a formal request to PAGASA, as you found.
- **A token-based Ten-Day forecast API** exists, but PAGASA gives tokens only on formal request.
- **History without paperwork:** NOAA's GSOD carries PAGASA's synoptic stations. Commercial redistribution is restricted (see below).
- **Typhoon history** is fully open through IBTrACS.

## In use (November 2026)

Everything in "Open now" below except Copernicus ERA5 (it needs a free account),
plus PAGASA's bulletins through a self-hosted BagyoAPI. See the README's Data
section for the tables and schedules.

| Zetaris source | Data | From | Refresh |
| --- | --- | --- | --- |
| `WEATHER` | Current weather, 5-day/3-hour forecast and air quality for 24 cities, at least one per region and more in the typhoon belt; daily history since 1991 | OpenWeather free APIs; NASA POWER | Hourly; daily |
| `BULLETINS` | PAGASA tropical cyclone bulletins, wind signals by PSGC area, rainfall advisories | PAGASA, parsed by self-hosted BagyoAPI | Every 30 min |
| `HAZARDS` | Earthquakes M3+ since 2000; GDACS alerts since 2015; NOAH flood, landslide and storm surge around each city | USGS; GDACS; Project NOAH vector tiles | Hourly; hourly; yearly |
| `TYPHOONS` | Every storm inside PAR since 1951, its track, and its closest pass to each city | IBTrACS | Weekly |
| `REFERENCE` | PSGC places, province population 2022 to 2025, facilities near each city | PSA via psgc.gitlab.io and HDX; OpenStreetMap | Monthly |

The tables are in [scripts/sql/](scripts/sql/).

**OpenWeather's key works** for the free APIs: current weather, the 5-day forecast, air pollution and geocoding. One Call 3.0 and 4.0 return 401 until the account subscribes to **One Call by Call**:

- **What it adds:** a timeline down to 1 minute, government weather alerts, and daily history.
- **Cost:** the first 1,000 calls a day are free, then each call is billed. A payment card is required.

## Open now, no approval needed

| Source | What it gives BantAI | Access | Terms |
| --- | --- | --- | --- |
| [USGS earthquake catalogue](https://earthquake.usgs.gov/fdsnws/event/1/) | Earthquakes around the Philippines, minutes after they happen | REST (GeoJSON); query by a bounding box around the country. No key | US public domain |
| [IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive) (NOAA NCEI) | Every West Pacific tropical cyclone track, including storms inside PAR: positions, winds, pressure | CSV per basin (`v04r01`) | "May be redistributed and used without restriction" |
| [NASA POWER](https://power.larc.nasa.gov/) | Daily and hourly rain, temperature, wind and solar for any point since 1981 | REST, no key | NASA open data; attribution requested |
| [Project NOAH hazard maps](https://noah.up.edu.ph/) (UP NOAH Center) | Flood (5-, 25- and 100-year rain), landslide and storm surge (4 levels) by province | Shapefiles. Precompute a hazard row per city or site, not live GIS | ODbL: credit Project NOAH; an adapted database used publicly must also be shared under ODbL |
| [PSGC](https://psa.gov.ph/classification/psgc) (PSA) | Codes for every region, province, city, municipality and barangay. This is the join key between sources | Quarterly Excel from PSA; community JSON API at psgc.gitlab.io | Government publication |
| [HDX: Philippines boundaries](https://data.humdata.org/dataset/philippines-administrative-levels-0-to-3) and [population](https://data.humdata.org/group/phl) (OCHA with NAMRIA, PSA, UNFPA) | Boundaries down to municipality level, and population by sex and age, so BantAI can say "how many people" | Download, or the CKAN API | Licence per dataset; check each |
| [GDACS](https://www.gdacs.org/) (EC JRC and UN) | Live cyclone, flood and earthquake alerts, with the exposed population per country | RSS and GeoJSON per event | Syndication allowed with credit |
| [OpenStreetMap](https://www.openstreetmap.org/) | Hospitals, schools, roads and bridges near each city | Overpass API, or HOT exports on HDX | ODbL |
| [Copernicus ERA5](https://cds.climate.copernicus.eu/) | Hourly reanalysis weather since 1940, for backfilling history | CDS API, free account | Copernicus licence; commercial use allowed with attribution |

## Usable, with conditions

| Source | What it gives | The condition |
| --- | --- | --- |
| [Open-Meteo](https://open-meteo.com/) | Forecasts and ERA5-based history through one easy API, no key | Data is CC BY 4.0, but the free API is **non-commercial**. Fine for prototyping and backfill. Production BantAI needs their commercial plan or a self-hosted copy (AGPLv3) |
| [NOAA GSOD](https://www.ncei.noaa.gov/access/search/data-search/global-summary-of-the-day) | Daily history from PAGASA's synoptic stations, shared through the WMO: the closest thing to PAGASA station data without a request | Non-US stations carry a WMO Resolution 40 notice: **no commercial redistribution**. Internal analysis only until NCEI's current terms are confirmed. The WMO's 2021 Unified Data Policy superseded Resolution 40 |
| [ReliefWeb API](https://apidoc.reliefweb.int/) (OCHA) | Situation reports and disaster records for the Philippines | Since 1 November 2025 every app needs a **pre-approved `appname`**. Request one on the API docs site |
| OpenWeather One Call 3.0 / 4.0 | Minute-level timeline, alerts, daily history back to 1979 | The paid "One Call by Call" subscription above |

## Public, but parsed or scraped (unofficial, can break)

| Source | What it gives | How |
| --- | --- | --- |
| PAGASA tropical cyclone bulletins ([pubfiles](https://pubfiles.pagasa.dost.gov.ph/)) | Live wind signals by province, tracks, rainfall advisories: the trigger for a storm run | Self-host [BagyoAPI](https://github.com/edwardguevarra/bagyo-api) (MIT; PSGC-coded signals, webhooks; there's no public server) or use [pagasa-parser](https://github.com/pagasa-parser/pagasa-parser) (Node; bulletin PDFs). Store every bulletin we parse |
| PAGASA annual cyclone reports | Curated history of Philippine tropical cyclones | The [bagyo](https://github.com/panukatan/bagyo) R package already extracts them |
| PHIVOLCS earthquake bulletins | Local intensity reports | No API; community scrapers such as pylindol. Use USGS for the feed, PHIVOLCS for the local detail |
| [DSWD DROMIC](https://dromic.dswd.gov.ph/) and NDRRMC situation reports | Affected families, evacuation centres and damage per municipality, per event | PDFs: download them per event and extract the tables. DROMIC is moving to a digital system (DSWD MC 12, s. 2026) |
| [PANaHON](https://www.panahon.gov.ph/) (PAGASA) | Near real-time readings from PAGASA's automatic and manned stations | Web map only; no documented API |

## Needs a request or a partnership

| Source | Route |
| --- | --- |
| PAGASA historical climate data: station rainfall, temperature, wind | Climatology and Agrometeorology Division. Send a request letter (form CADS-06), the raw-data request form (CADS-01A for companies, CADS-01B for researchers) and the signed terms of use (CADS-07). The division decides whether it's free or charged, based on the purpose you state. Commercial use is charged per station and period. |
| PAGASA Ten-Day forecast API | Exists (IRRI reviewed it in 2025); its token needs a formal request. Contact: the Climate Monitoring and Prediction Section, listed on the [10-day forecast page](https://bagong.pagasa.dost.gov.ph/climate/climate-prediction/10-day-climate-forecast). The public spreadsheets stopped on 31 August 2025 |
| DOST-ASTI [PhilSensors](https://philsensors.asti.dost.gov.ph/): rain gauges, water level, weather stations | API access for government and academe only, so go through an LGU or state-university partner, or file an FOI request |
| GeoRiskPH / [HazardHunterPH](https://hazardhunter.georisk.gov.ph/) (PHIVOLCS) | Files only for agencies that sign an MOA, so go through an LGU partner |
| MGB geohazard maps | Public as JPEG; shapefiles only through FOI. Some are already released on [foi.gov.ph](https://foi.gov.ph/) |
| LGU data: evacuation centres, CBMS household data | An MOA per LGU; this belongs in the public-sector pitch. Open portals so far: Quezon City's QCitizen Data (May 2026) and Ligao City's CBMS portal |
| Any national agency dataset | [FOI portal](https://foi.gov.ph/). Search the requests already granted first: many datasets have been released before |

## Recommended order

1. **Done (November 2026):** `WEATHER`, `BULLETINS`, `HAZARDS`, `TYPHOONS` and `REFERENCE`, as above.
2. **Next, no approvals needed:**
   - More cities, or sites (a client's branches), in `scripts/ingest/cities.py`: every job follows the list.
   - Copernicus ERA5 for hourly history, once someone registers the free CDS account.
3. **Start the paperwork now, since it is slow:**
   - The PAGASA CAD request for station history. State the commercial purpose plainly and budget for the fees.
   - A ReliefWeb `appname`.
   - PhilSensors access through a partner LGU or state university.
   - Open-Meteo's commercial plan, if it stays in production.

Credit every source in the product's About page and in this repo's README: PAGASA, Project NOAH (ODbL), OpenWeather, NOAA/NCEI, NASA, USGS, OCHA/HDX, OpenStreetMap contributors (ODbL).
