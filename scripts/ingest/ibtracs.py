"""IBTrACS West Pacific best tracks: every storm that entered PAR since 1951.

Downloads the basin file (about 115 MB), keeps storms with a track point inside
PAR, and reloads storms, track points and each city's closest passes in one
transaction. NCEI refreshes the file weekly.
"""
from __future__ import annotations

import tempfile

import numpy as np
import pandas as pd

from ingest.cities import LOCATIONS
from ingest.common import Context, in_polygon

NAME = "ibtracs"
EVERY = 7 * 86400
SCHEMAS = ["typhoons"]

URL = ("https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/"
       "v04r01/access/csv/ibtracs.WP.list.v04r01.csv")
FROM_SEASON = 1951
PASS_KM = 300
PH_BOX = (4.5, 21.5, 116.0, 127.0)  # lat min, lat max, lon min, lon max
COLS = ["SID", "SEASON", "NAME", "ISO_TIME", "NATURE", "LAT", "LON", "WMO_WIND", "WMO_PRES", "TRACK_TYPE",
        "DIST2LAND", "USA_WIND", "USA_PRES", "USA_SSHS"]


def _num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.strip().replace("", np.nan), errors="coerce")


def _none(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v


def run(ctx: Context) -> str:
    with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
        with ctx.http.get(URL, stream=True, timeout=600) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(1 << 20):
                tmp.write(chunk)
        tmp.flush()
        # Row 2 is a units row.
        df = pd.read_csv(tmp.name, skiprows=[1], usecols=COLS, dtype=str, keep_default_na=False)

    df = df[(df.TRACK_TYPE == "main") & (_num(df.SEASON) >= FROM_SEASON)].copy()
    df["lat"], df["lon"] = _num(df.LAT), _num(df.LON)
    df["wind"] = _num(df.USA_WIND).fillna(_num(df.WMO_WIND))
    df["pres"] = _num(df.USA_PRES).fillna(_num(df.WMO_PRES))
    df["sshs"], df["d2l"] = _num(df.USA_SSHS), _num(df.DIST2LAND)
    df["t"] = pd.to_datetime(df.ISO_TIME, utc=True)
    df = df.dropna(subset=["lat", "lon"]).drop_duplicates(["SID", "t"])
    df["in_par"] = [in_polygon(lo, la) for lo, la in zip(df.lon, df.lat)]
    pts = df[df.SID.isin(set(df.loc[df.in_par, "SID"]))].copy()

    inside = pts[pts.in_par]
    lat0, lat1, lon0, lon1 = PH_BOX
    over_land = inside[(inside.d2l == 0) & inside.lat.between(lat0, lat1) & inside.lon.between(lon0, lon1)]
    agg = inside.groupby("SID").agg(entered=("t", "min"), left=("t", "max"), wind=("wind", "max"),
                                    pres=("pres", "min"), sshs=("sshs", "max"))
    first = pts.groupby("SID").first()
    storms = [(sid, int(first.at[sid, "SEASON"]), first.at[sid, "NAME"], r.entered.to_pydatetime(),
               r.left.to_pydatetime(), _none(r.wind), _none(r.pres),
               None if np.isnan(r.sshs) else int(r.sshs), sid in set(over_land.SID))
              for sid, r in agg.iterrows()]

    points = [(r.SID, r.t.to_pydatetime(), float(r.lat), float(r.lon), _none(r.wind), _none(r.pres),
               None if np.isnan(r.sshs) else int(r.sshs), r.NATURE or None, _none(r.d2l), bool(r.in_par))
              for r in pts.itertuples()]

    passes = []
    rad = np.radians
    for city in LOCATIONS:
        a = (np.sin(rad(pts.lat.values - city.lat) / 2) ** 2 + np.cos(rad(city.lat)) * np.cos(rad(pts.lat.values))
             * np.sin(rad(pts.lon.values - city.lon) / 2) ** 2)
        d = pd.Series(12742 * np.arcsin(np.sqrt(a)), index=pts.index)
        near = pts.assign(km=d)[d <= PASS_KM]
        for sid, grp in near.groupby("SID"):
            best = grp.loc[grp.km.idxmin()]
            passes.append((city.location_id, sid, round(float(best.km), 1), best.t.to_pydatetime(),
                           _none(best.wind)))

    with ctx.connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE typhoons.storms, typhoons.track_points, typhoons.city_passes")
        for table, cols, rows in [
            ("typhoons.storms", "sid, season, name, entered_par_at, left_par_at, max_wind_kt_in_par, "
             "min_pressure_hpa_in_par, max_category_in_par, over_ph_land", storms),
            ("typhoons.track_points", "sid, observed_at, lat, lon, wind_kt, pressure_hpa, category, nature, "
             "dist2land_km, in_par", points),
            ("typhoons.city_passes", "location_id, sid, closest_km, closest_at, wind_kt_then", passes),
        ]:
            with cur.copy(f"COPY {table} ({cols}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
    return f"{len(storms)} storms in PAR since {FROM_SEASON}, {len(points)} track points, {len(passes)} city passes"
