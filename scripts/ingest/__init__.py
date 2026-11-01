"""BantAI's ingestion jobs. scripts/run_ingest.py schedules them; each module
exposes NAME, EVERY (seconds between successful runs), SCHEMAS (scripts/sql files
it needs) and run(ctx) -> one-line summary."""
