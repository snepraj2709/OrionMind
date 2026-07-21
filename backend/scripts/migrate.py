from __future__ import annotations

import argparse
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg


MIGRATION_NAME = re.compile(r"^(?P<version>[0-9]{4})_[a-z0-9_]+\.sql$")
MIGRATION_LOCK_ID = 6_329_665_514_830_621_231


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    checksum: str
    sql: str


def load_migrations(directory: Path) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    seen_versions: set[int] = set()
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_NAME.fullmatch(path.name)
        if match is None:
            raise RuntimeError(f"invalid migration filename: {path.name}")
        version = int(match.group("version"))
        if version in seen_versions:
            raise RuntimeError(f"duplicate migration version: {version:04d}")
        sql = path.read_text(encoding="utf-8")
        if not sql.strip():
            raise RuntimeError(f"empty migration: {path.name}")
        seen_versions.add(version)
        migrations.append(
            Migration(
                version=version,
                name=path.name,
                checksum=hashlib.sha256(sql.encode("utf-8")).hexdigest(),
                sql=sql,
            )
        )
    if not migrations:
        raise RuntimeError("no migrations found")
    return tuple(migrations)


def apply_migrations(database_url: str, migrations: tuple[Migration, ...]) -> tuple[str, ...]:
    applied_now: list[str] = []
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("SELECT pg_catalog.pg_advisory_xact_lock(%s)", (MIGRATION_LOCK_ID,))
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS public.schema_migrations (
                    version integer PRIMARY KEY,
                    name text NOT NULL UNIQUE,
                    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
                    applied_at timestamptz NOT NULL DEFAULT pg_catalog.now()
                )
                """
            )
            rows = connection.execute(
                "SELECT version, name, checksum FROM public.schema_migrations ORDER BY version"
            ).fetchall()
            existing = {int(row[0]): (str(row[1]), str(row[2])) for row in rows}
            known_versions = {migration.version for migration in migrations}
            unknown = sorted(set(existing) - known_versions)
            if unknown:
                raise RuntimeError(f"database contains unknown migration versions: {unknown}")
            for migration in migrations:
                applied = existing.get(migration.version)
                if applied is not None:
                    if applied != (migration.name, migration.checksum):
                        raise RuntimeError(
                            f"migration checksum mismatch for version {migration.version:04d}"
                        )
                    continue
                connection.execute(migration.sql, prepare=False)
                connection.execute(
                    "INSERT INTO public.schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                    (migration.version, migration.name, migration.checksum),
                )
                applied_now.append(migration.name)
    return tuple(applied_now)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply ordered Orion PostgreSQL migrations.")
    parser.add_argument(
        "--migrations",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "migrations",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database_url = os.environ.get("ORION_MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("ORION_MIGRATION_DATABASE_URL is required")
    applied = apply_migrations(database_url, load_migrations(args.migrations))
    if applied:
        print(f"Applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        print("Schema already current")


if __name__ == "__main__":
    main()
