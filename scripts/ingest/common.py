"""What every ingestion job shares: logging, the database, HTTP, geography."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg
import requests

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
# Sent with every request, so a provider can see who is calling and why.
USER_AGENT = "BantAI-ingest/1.0 (IToolbox; +https://github.com/IToolboxPH)"


def log(job: str, msg: str) -> None:
    print(f"[ingest {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%SZ}] {job}: {msg}", flush=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Context:
    db_url: str
    env: dict[str, str]
    http: requests.Session = field(default_factory=lambda: _session())

    def connect(self, **kwargs: Any) -> psycopg.Connection:
        return psycopg.connect(self.db_url, **kwargs)

    def apply_schema(self, name: str) -> None:
        """Run scripts/sql/<name>.sql; every statement there is idempotent."""
        with self.connect(autocommit=True) as conn:
            conn.execute((SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"))


def _session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def get(http: requests.Session, url: str, *, params: dict | None = None, timeout: float = 60,
        attempts: int = 4, headers: dict | None = None) -> requests.Response:
    """GET with backoff on 429, 5xx and network errors; raises on anything else."""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = http.get(url, params=params, timeout=timeout, headers=headers)
        except requests.RequestException as exc:  # timeouts, resets
            last = exc
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last = RuntimeError(f"HTTP {resp.status_code} from {url.split('?')[0]}")
            elif resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code} from {url.split('?')[0]}: {resp.text[:200]}")
            else:
                return resp
        time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"still failing after {attempts} attempts: {last}")


def upsert(conn: psycopg.Connection, table: str, columns: Sequence[str], rows: Iterable[Sequence[Any]],
           key: Sequence[str], update: bool = True) -> int:
    """INSERT ... ON CONFLICT (key) DO UPDATE every other column (or DO NOTHING)."""
    rows = list(rows)
    if not rows:
        return 0
    cols = ", ".join(columns)
    marks = ", ".join(["%s"] * len(columns))
    others = [c for c in columns if c not in key]
    action = (
        "DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in others)
        if update and others else "DO NOTHING"
    )
    sql = f"INSERT INTO {table} ({cols}) VALUES ({marks}) ON CONFLICT ({', '.join(key)}) {action}"
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    return len(rows)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * math.asin(math.sqrt(a))


# PAGASA's Philippine Area of Responsibility, corner by corner (lon, lat).
PAR = [(120, 25), (135, 25), (135, 5), (115, 5), (115, 15), (120, 21), (120, 25)]


def in_polygon(lon: float, lat: float, polygon: Sequence[tuple[float, float]] = PAR) -> bool:
    """Ray casting; the polygon is closed (first point repeated last)."""
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:]):
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def number(value: Any) -> float | None:
    """A float, or None for blanks and sentinels (IBTrACS ' ', NASA POWER -999)."""
    if value is None:
        return None
    try:
        f = float(str(value).strip())
    except ValueError:
        return None
    return None if f <= -999 or math.isnan(f) else f
