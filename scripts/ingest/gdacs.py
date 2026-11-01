"""GDACS disaster alerts for events touching the Philippines.

The first run backfills from 2015, a year per request; later runs re-read the last
90 days, so an event's newest episode (and alert level) replaces the older one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingest.common import Context, get, upsert, utcnow

NAME = "gdacs_alerts"
EVERY = 3600
SCHEMAS = ["hazards"]

API = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
EVENT_TYPES = "TC;FL;EQ;VO;DR;WF"
BACKFILL_FROM = 2015
PAGE = 100

COLS = ["event_type", "event_id", "episode_id", "name", "alert_level", "alert_score", "severity",
        "severity_unit", "severity_text", "from_date", "to_date", "is_current", "countries", "lat", "lon",
        "report_url", "fetched_at"]


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "")).replace(tzinfo=timezone.utc)


def _fetch(ctx: Context, start: datetime, end: datetime) -> list[tuple]:
    rows, page, fetched_at = {}, 1, utcnow()
    while True:
        resp = get(ctx.http, API, timeout=120, params={
            "eventlist": EVENT_TYPES, "country": "Philippines", "fromDate": start.date().isoformat(),
            "toDate": end.date().isoformat(), "pageSize": PAGE, "pageNumber": page,
        })
        features = resp.json().get("features", []) if resp.text.strip() else []
        for f in features:
            p = f["properties"]
            lon, lat = (f.get("geometry") or {}).get("coordinates", [None, None])[:2]
            sev = p.get("severitydata") or {}
            countries = ", ".join(c.get("countryname", "") for c in p.get("affectedcountries") or []) or p.get("country")
            key = (p["eventtype"], int(p["eventid"]))
            row = (p["eventtype"], int(p["eventid"]), p.get("episodeid"), p.get("eventname") or p.get("name"),
                   p.get("alertlevel"), p.get("alertscore"), sev.get("severity"), sev.get("severityunit"),
                   sev.get("severitytext"), _date(p.get("fromdate")), _date(p.get("todate")),
                   str(p.get("iscurrent")).lower() == "true", countries, lat, lon,
                   (p.get("url") or {}).get("report"), fetched_at)
            # A search can return several episodes of one event: keep the newest.
            if key not in rows or (row[2] or 0) >= (rows[key][2] or 0):
                rows[key] = row
        if len(features) < PAGE:
            return list(rows.values())
        page += 1


def run(ctx: Context) -> str:
    with ctx.connect() as conn:
        have = conn.execute("SELECT count(*) FROM hazards.disaster_alerts").fetchone()[0]
    now = utcnow()
    windows = ([(now - timedelta(days=90), now)] if have else
               [(datetime(y, 1, 1, tzinfo=timezone.utc), min(datetime(y, 12, 31, tzinfo=timezone.utc), now))
                for y in range(BACKFILL_FROM, now.year + 1)])
    total = 0
    with ctx.connect() as conn:
        for start, end in windows:
            total += upsert(conn, "hazards.disaster_alerts", COLS, _fetch(ctx, start, end),
                            key=["event_type", "event_id"])
            conn.commit()
    return f"{total} alerts {'(backfill since %d)' % BACKFILL_FROM if not have else 'in the last 90 days'}"
