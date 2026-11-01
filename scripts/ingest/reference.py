"""PSGC places and PSA population projections, reloaded in one transaction.

PSGC from psgc.gitlab.io (PSA's codes as JSON). Population per province from
OCHA's COD-PS on HDX, whose CSV links are looked up through the HDX API each run,
so a new year's file is picked up without a code change.
"""
from __future__ import annotations

import csv
import io
import re

from ingest.common import Context, get

NAME = "reference"
EVERY = 30 * 86400
SCHEMAS = ["reference"]

PSGC = "https://psgc.gitlab.io/api"
HDX_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=cod-ps-phl"
POP_FILE = re.compile(r"phl_admpop_adm2_(\d{4})", re.I)


def _int(v: str | None) -> int | None:
    try:
        return int(float(v)) if v not in (None, "") else None
    except ValueError:
        return None


def _population(ctx: Context) -> list[tuple]:
    resources = get(ctx.http, HDX_PACKAGE).json()["result"]["resources"]
    by_year: dict[int, str] = {}
    for res in resources:
        m = POP_FILE.match(res.get("name", ""))
        if m and res.get("format", "").upper() == "CSV":
            by_year[int(m.group(1))] = res["url"]  # a later "_v2" upload of the same year wins
    rows = []
    for year, url in sorted(by_year.items()):
        text = get(ctx.http, url, timeout=120).content.decode("utf-8-sig")
        for r in csv.DictReader(io.StringIO(text)):
            kids = sum(_int(r.get(f"T_{a}")) or 0 for a in ("00_04", "05_09", "10_14"))
            old = sum(_int(r.get(f"T_{a}")) or 0 for a in ("65_69", "70_74", "75_79", "80Plus"))
            rows.append((r["ADM2_PCODE"].removeprefix("PH"), r["ADM2_NAME"], r.get("ADM1_NAME"), year,
                         _int(r["T_TL"]), _int(r.get("F_TL")), _int(r.get("M_TL")), kids or None, old or None))
    return rows


def run(ctx: Context) -> str:
    regions = get(ctx.http, f"{PSGC}/regions.json").json()
    provinces = get(ctx.http, f"{PSGC}/provinces.json").json()
    places = get(ctx.http, f"{PSGC}/cities-municipalities.json", timeout=120).json()
    population = _population(ctx)

    with ctx.connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE reference.regions, reference.provinces, reference.cities_municipalities, "
                    "reference.province_population")
        cur.executemany("INSERT INTO reference.regions VALUES (%s, %s, %s, %s)",
                        [(r["code"], r.get("psgc10DigitCode"), r.get("regionName") or r["name"], r["name"])
                         for r in regions])
        cur.executemany("INSERT INTO reference.provinces VALUES (%s, %s, %s, %s)",
                        [(p["code"], p.get("psgc10DigitCode"), p["name"], p["regionCode"]) for p in provinces])
        cur.executemany("INSERT INTO reference.cities_municipalities VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        [(c["code"], c.get("psgc10DigitCode"), c["name"], bool(c.get("isCity")),
                          bool(c.get("isCapital")), c.get("provinceCode") or None, c["regionCode"])
                         for c in places])
        cur.executemany("INSERT INTO reference.province_population VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT DO NOTHING", population)
    years = sorted({r[3] for r in population})
    return (f"{len(regions)} regions, {len(provinces)} provinces, {len(places)} cities and municipalities, "
            f"population for {years[0]}-{years[-1]}" if years else "no population files found")
