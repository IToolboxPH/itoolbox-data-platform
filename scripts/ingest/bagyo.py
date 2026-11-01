"""PAGASA bulletins from the self-hosted BagyoAPI (the bagyo-* compose services).

Each run reads every cyclone BagyoAPI knows, each cyclone's bulletin history and
the active rainfall advisories, and upserts them. BagyoAPI's own worker does the
PAGASA scraping on its polite schedule; this job only copies what it parsed.
"""
from __future__ import annotations

from datetime import datetime

from ingest.common import Context, get, upsert, utcnow

NAME = "bagyo_bulletins"
EVERY = 1800
SCHEMAS = ["bulletins"]


def _t(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _pages(ctx: Context, url: str, key: str) -> list[dict]:
    """Follow BagyoAPI's cursor pagination."""
    items, cursor = [], None
    while True:
        params = {"limit": 100, **({"cursor": cursor} if cursor else {})}
        data = get(ctx.http, url, params=params).json()["data"]
        items.extend(data.get(key, []))
        cursor = (data.get("pagination") or {}).get("nextCursor")
        if not cursor:
            return items


def run(ctx: Context) -> str:
    base = ctx.env.get("BAGYO_API_URL", "http://bagyo-api:3000").rstrip("/")
    fetched_at = utcnow()
    cyclones = _pages(ctx, f"{base}/v1/cyclones", "cyclones")

    cyc_rows, bul_rows, sig_rows = [], [], []
    for c in cyclones:
        detail = get(ctx.http, f"{base}/v1/cyclones/{c['id']}").json()["data"]
        detail = detail.get("cyclone", detail)
        cyc_rows.append((c["id"], c.get("pagasaName"), c.get("internationalName"), c.get("category"),
                         c.get("categoryLabel"), c.get("status"), c.get("seasonYear"), _t(c.get("firstBulletinAt")),
                         _t(c.get("lastBulletinAt")), detail.get("bulletinCount"), fetched_at))
        for b in _pages(ctx, f"{base}/v1/cyclones/{c['id']}/bulletins", "bulletins"):
            centre = b.get("center") or {}
            bul_rows.append((b["id"], c["id"], b.get("bulletinNumber"), b.get("isFinal"), _t(b["issuedAt"]),
                             _t(b.get("nextBulletinAt")), centre.get("lat"), centre.get("lng"), b.get("maxWindsKph"),
                             b.get("gustinessKph"), b.get("pressureHpa"), b.get("movementDirection"),
                             b.get("movementSpeedKph"), b.get("sourceUrl"), fetched_at))
            seen = set()
            for s in b.get("windSignals") or []:
                key = (b["id"], s["signalLevel"], s["locationName"])
                if key not in seen:
                    seen.add(key)
                    sig_rows.append((*key, s.get("psgcCode"), s.get("locationType"), s.get("partialDescriptor")))

    advisories = get(ctx.http, f"{base}/v1/rainfall/current").json()["data"].get("advisories", [])
    adv_rows = [(a["id"], _t(a.get("issuedAt")), _t(a.get("expiresAt")), a.get("region"), a.get("level"), fetched_at)
                for a in advisories]
    area_rows = list({(a["id"], ar["name"]): (a["id"], ar["name"], ar.get("psgcCode"))
                      for a in advisories for ar in a.get("areas") or []}.values())

    with ctx.connect() as conn:
        upsert(conn, "bulletins.cyclones",
               ["cyclone_id", "pagasa_name", "international_name", "category", "category_label", "status",
                "season_year", "first_bulletin_at", "last_bulletin_at", "bulletin_count", "fetched_at"],
               cyc_rows, key=["cyclone_id"])
        upsert(conn, "bulletins.bulletins",
               ["bulletin_id", "cyclone_id", "bulletin_number", "is_final", "issued_at", "next_bulletin_at",
                "center_lat", "center_lon", "max_winds_kph", "gustiness_kph", "pressure_hpa", "movement_direction",
                "movement_speed_kph", "source_url", "fetched_at"], bul_rows, key=["bulletin_id"])
        upsert(conn, "bulletins.wind_signals",
               ["bulletin_id", "signal_level", "location_name", "psgc_code", "location_type", "partial_descriptor"],
               sig_rows, key=["bulletin_id", "signal_level", "location_name"])
        upsert(conn, "bulletins.rainfall_advisories",
               ["advisory_id", "issued_at", "expires_at", "region", "level", "fetched_at"], adv_rows,
               key=["advisory_id"])
        upsert(conn, "bulletins.rainfall_areas", ["advisory_id", "area_name", "psgc_code"], area_rows,
               key=["advisory_id", "area_name"], update=False)
    return (f"{len(cyc_rows)} cyclones, {len(bul_rows)} bulletins, {len(sig_rows)} wind signals, "
            f"{len(adv_rows)} active rainfall advisories")
