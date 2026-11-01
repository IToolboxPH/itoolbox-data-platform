"""Run BantAI's ingestion jobs, each on its own schedule.

  python scripts/run_ingest.py                    # forever: run each job when it is due
  python scripts/run_ingest.py --once noah ibtracs  # run those jobs now, then exit
  python scripts/run_ingest.py --once all         # every job, now
  python scripts/run_ingest.py --status           # when each job last ran

A job is due when EVERY seconds have passed since its last success, or 15
minutes after a failure, and it isn't already running elsewhere. State lives in
ingest.job_runs, so a restart does not re-run a job that isn't due. Needs
TIMESCALE_URL; each job reads its own keys.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest import bagyo, gdacs, ibtracs, nasa_power, noah, openweather, osm, reference, usgs  # noqa: E402
from ingest.common import Context, log, utcnow  # noqa: E402

# In first-run order: cheap and live sources before the heavy one-off backfills.
JOBS = [reference, openweather, usgs, gdacs, bagyo, nasa_power, ibtracs, osm, noah]
BY_NAME = {job.NAME: job for job in JOBS}
RETRY_AFTER_FAILURE = timedelta(minutes=15)
IN_PROGRESS_FOR = timedelta(hours=2)
TICK_S = 60


def _state(ctx: Context) -> dict[str, tuple]:
    with ctx.connect() as conn:
        rows = conn.execute(
            "SELECT job, last_started_at, last_success_at, last_error_at FROM ingest.job_runs").fetchall()
    return {job: (started, ok, err) for job, started, ok, err in rows}


def _due(job, state: dict[str, tuple]) -> bool:
    started, ok, err = state.get(job.NAME, (None, None, None))
    now = utcnow()
    finished = max((t for t in (ok, err) if t), default=None)
    # Started and not finished: another run (a --once, say) has it. A run that
    # died without recording an end is assumed gone after IN_PROGRESS_FOR.
    if started and (not finished or started > finished) and now - started < IN_PROGRESS_FOR:
        return False
    if err and (not ok or err > ok) and now - err < RETRY_AFTER_FAILURE:
        return False
    return ok is None or now - ok >= timedelta(seconds=job.EVERY)


def _record(ctx: Context, job, *, started=None, summary=None, error=None) -> None:
    with ctx.connect() as conn:
        if started:
            conn.execute("INSERT INTO ingest.job_runs (job, last_started_at) VALUES (%s, %s) "
                         "ON CONFLICT (job) DO UPDATE SET last_started_at = EXCLUDED.last_started_at",
                         (job.NAME, started))
        elif error is None:
            conn.execute("UPDATE ingest.job_runs SET last_success_at = now(), last_summary = %s WHERE job = %s",
                         (summary, job.NAME))
        else:
            conn.execute("UPDATE ingest.job_runs SET last_error_at = now(), last_error = %s WHERE job = %s",
                         (error[:2000], job.NAME))


def run_job(ctx: Context, job) -> bool:
    _record(ctx, job, started=utcnow())
    started = time.monotonic()
    try:
        for schema in job.SCHEMAS:
            ctx.apply_schema(schema)
        summary = job.run(ctx)
    except Exception as exc:  # one source failing must not stop the others
        log(job.NAME, f"FAILED: {type(exc).__name__}: {exc}")
        _record(ctx, job, error=f"{type(exc).__name__}: {exc}")
        return False
    log(job.NAME, f"{summary} ({time.monotonic() - started:.0f} s)")
    _record(ctx, job, summary=summary)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", nargs="+", metavar="JOB", help=f"run now and exit: {', '.join(BY_NAME)} or all")
    parser.add_argument("--status", action="store_true", help="show when each job last ran")
    args = parser.parse_args()

    db_url = os.environ.get("TIMESCALE_URL")
    if not db_url:
        print("TIMESCALE_URL is not set", file=sys.stderr)
        return 2
    ctx = Context(db_url=db_url, env=dict(os.environ))
    ctx.apply_schema("ingest")

    if args.status:
        with ctx.connect() as conn:
            rows = dict((r[0], r[1:]) for r in conn.execute(
                "SELECT job, last_success_at, last_summary, last_error_at, last_error FROM ingest.job_runs"))
        for job in JOBS:
            ok, summary, err_at, err = rows.get(job.NAME, (None, None, None, None))
            print(f"{job.NAME:<18} every {timedelta(seconds=job.EVERY)!s:<17} last ok {ok:%Y-%m-%d %H:%M}Z  {summary}"
                  if ok else f"{job.NAME:<18} never succeeded")
            if err_at and (not ok or err_at > ok):
                print(f"{'':<18} last error {err_at:%Y-%m-%d %H:%M}Z: {err}")
        return 0

    if args.once:
        names = list(BY_NAME) if args.once == ["all"] else args.once
        unknown = [n for n in names if n not in BY_NAME]
        if unknown:
            print(f"unknown job(s): {', '.join(unknown)}; known: {', '.join(BY_NAME)}", file=sys.stderr)
            return 2
        return 0 if all([run_job(ctx, BY_NAME[n]) for n in names]) else 1

    log("scheduler", f"up; jobs: {', '.join(BY_NAME)}")
    while True:
        try:
            state = _state(ctx)
            for job in JOBS:
                if _due(job, state):
                    run_job(ctx, job)
        except Exception as exc:  # e.g. the database restarting: wait and carry on
            log("scheduler", f"tick failed: {exc}")
        time.sleep(TICK_S)


if __name__ == "__main__":
    sys.exit(main())
