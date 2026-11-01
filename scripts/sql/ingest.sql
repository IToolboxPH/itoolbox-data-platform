-- ingest — bookkeeping for scripts/run_ingest.py. Not registered in Zetaris.

CREATE SCHEMA IF NOT EXISTS ingest;

-- One row per job: when it last succeeded, and the last failure if any. The
-- scheduler reads it on start, so a restart does not re-run a job that is not due.
CREATE TABLE IF NOT EXISTS ingest.job_runs (
    job              text PRIMARY KEY,
    last_started_at  timestamptz,
    last_success_at  timestamptz,
    last_summary     text,
    last_error_at    timestamptz,
    last_error       text
);
