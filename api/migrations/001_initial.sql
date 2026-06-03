-- 001_initial.sql — Naik initial Postgres schema (Block 2, Xinyue)
--
-- Three tables backing the pipeline:
--   personas      one row per (synthetic or demo) user; full DiagnosticInput as JSONB
--   transactions  a user's anonymised Shopee ledger; one row per Transaction, JSONB
--   eval_runs     one row per pipeline run over a persona; agent outputs + eval scores
--
-- Design notes:
--   * UUID primary keys via gen_random_uuid() (built into Postgres 13+; Render's
--     managed Postgres supports it without a CREATE EXTENSION step).
--   * JSONB (not JSON) so payloads are binary-packed, de-duplicated, and indexable.
--   * GIN indexes on the JSONB columns so eval queries can filter on nested keys
--     (e.g. data @> '{"is_gig_worker": true}') without a full scan.
--   * Foreign keys ON DELETE CASCADE: removing a persona removes its transactions
--     and eval_runs — appropriate for regenerable synthetic data.
--   * created_at is timestamptz DEFAULT now() to match the app's UTC convention.
--   * Idempotent: CREATE TABLE IF NOT EXISTS, so re-running is safe.
--
-- Run from the repo root with DATABASE_URL set (see api/run_migration.py):
--   python api/run_migration.py

BEGIN;

-- pgcrypto provides gen_random_uuid() on older Postgres; harmless if already core.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. personas --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS personas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. transactions ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS transactions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id  UUID NOT NULL REFERENCES personas (id) ON DELETE CASCADE,
    data        JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. eval_runs -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eval_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id      UUID NOT NULL REFERENCES personas (id) ON DELETE CASCADE,
    agent_outputs   JSONB NOT NULL,
    scores          JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes ------------------------------------------------------------------
-- Foreign-key lookups (join eval_runs/transactions back to a persona).
CREATE INDEX IF NOT EXISTS idx_transactions_persona_id ON transactions (persona_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_persona_id    ON eval_runs (persona_id);

-- JSONB containment queries (filter personas/eval results on nested keys).
CREATE INDEX IF NOT EXISTS idx_personas_data_gin        ON personas      USING GIN (data);
CREATE INDEX IF NOT EXISTS idx_transactions_data_gin    ON transactions  USING GIN (data);
CREATE INDEX IF NOT EXISTS idx_eval_runs_scores_gin     ON eval_runs     USING GIN (scores);

COMMIT;
