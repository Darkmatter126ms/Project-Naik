"""Apply the Naik SQL migrations and confirm the resulting schema.

Runs every ``NNN_*.sql`` file in ``api/migrations/`` in filename order against
the database in ``DATABASE_URL``, then verifies that the expected tables,
columns, and foreign keys exist — so "run the migration and confirm the tables"
is a single command.

Usage (from the repo root, with DATABASE_URL pointing at Render Postgres):

    # PowerShell
    $env:DATABASE_URL="postgresql://user:pass@host/naik"; python api/run_migration.py

    # bash
    DATABASE_URL="postgresql://user:pass@host/naik" python api/run_migration.py

Render's connection string may use the legacy ``postgres://`` scheme; this script
reuses ``api.db.normalize_database_url`` to rewrite it to ``postgresql://`` so
SQLAlchemy's default driver is selected.

Exit code 0 = migration applied and all expected objects confirmed; 1 = failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

# Reuse the app's URL normaliser so Render's postgres:// is handled identically.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.db import normalize_database_url  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# What we expect to exist after migrating, used for confirmation.
EXPECTED = {
    "personas": {"id", "data", "created_at"},
    "transactions": {"id", "persona_id", "data", "created_at"},
    "eval_runs": {"id", "persona_id", "agent_outputs", "scores", "created_at"},
}
EXPECTED_FKS = {
    ("transactions", "persona_id", "personas"),
    ("eval_runs", "persona_id", "personas"),
}


def _engine():
    url = normalize_database_url(os.environ.get("DATABASE_URL"))
    if url is None:
        print("ERROR: DATABASE_URL is not set. Point it at your Render Postgres.")
        sys.exit(1)
    return create_engine(url, future=True)


def apply_migrations(engine) -> None:
    """Execute each migration file in order, inside its own transaction."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print(f"ERROR: no .sql files found in {MIGRATIONS_DIR}")
        sys.exit(1)
    for path in files:
        sql = path.read_text(encoding="utf-8")
        print(f"applying {path.name} ...")
        # The .sql wraps its own BEGIN/COMMIT; exec_driver_sql runs the script
        # without SQLAlchemy adding a second transaction layer.
        with engine.connect() as conn:
            conn.exec_driver_sql(sql)
            conn.commit()
    print("migrations applied.\n")


def confirm_schema(engine) -> bool:
    """Verify expected tables, columns, and FKs exist. Returns True if all good."""
    ok = True
    with engine.connect() as conn:
        # tables + columns
        rows = conn.execute(text(
            """
            SELECT table_name, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('personas', 'transactions', 'eval_runs')
            ORDER BY table_name, ordinal_position
            """
        )).fetchall()

        found: dict[str, dict[str, str]] = {}
        for table, col, dtype in rows:
            found.setdefault(table, {})[col] = dtype

        print("=== tables & columns ===")
        for table, cols in EXPECTED.items():
            if table not in found:
                print(f"  MISSING TABLE: {table}")
                ok = False
                continue
            present = set(found[table])
            missing = cols - present
            mark = "OK" if not missing else "MISSING"
            print(f"  [{mark}] {table}: {', '.join(f'{c}:{found[table][c]}' for c in found[table])}")
            if missing:
                print(f"        missing columns: {missing}")
                ok = False

        # foreign keys
        fk_rows = conn.execute(text(
            """
            SELECT tc.table_name, kcu.column_name, ccu.table_name AS ref_table
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            """
        )).fetchall()
        found_fks = {(t, c, r) for t, c, r in fk_rows}

        print("\n=== foreign keys ===")
        for fk in EXPECTED_FKS:
            mark = "OK" if fk in found_fks else "MISSING"
            print(f"  [{mark}] {fk[0]}.{fk[1]} -> {fk[2]}")
            if fk not in found_fks:
                ok = False

        # indexes (informational)
        idx_rows = conn.execute(text(
            """
            SELECT tablename, indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename IN ('personas', 'transactions', 'eval_runs')
            ORDER BY tablename, indexname
            """
        )).fetchall()
        print("\n=== indexes ===")
        for table, idx in idx_rows:
            print(f"  {table}: {idx}")

    return ok


def main() -> int:
    engine = _engine()
    apply_migrations(engine)
    ok = confirm_schema(engine)
    print("\n" + ("RESULT: schema confirmed ✓" if ok else "RESULT: schema INCOMPLETE ✗"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
