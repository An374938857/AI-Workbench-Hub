#!/usr/bin/env python3
"""Fail-fast schema gate for release critical tables."""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, inspect


REQUIRED_TABLES = [
    "conversation_compression_logs",
    "custom_commands",
    "model_fallback_configs",
    "model_fallback_logs",
    "model_comparisons",
]


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("schema_check failed: DATABASE_URL is not configured", file=sys.stderr)
        return 1

    engine = create_engine(database_url)
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = [name for name in REQUIRED_TABLES if name not in existing]

    if not missing:
        print("schema_check passed: required release tables are present")
        return 0

    print("schema_check failed: missing required tables:", file=sys.stderr)
    for table in missing:
        print(f"  - {table}", file=sys.stderr)

    print("\nFix command:", file=sys.stderr)
    print("  docker compose run --rm backend alembic upgrade head", file=sys.stderr)
    print("\nDiagnosis SQL:", file=sys.stderr)
    print(
        "  SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = DATABASE() "
        "AND table_name IN ("
        + ", ".join(f"'{name}'" for name in REQUIRED_TABLES)
        + ");",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
