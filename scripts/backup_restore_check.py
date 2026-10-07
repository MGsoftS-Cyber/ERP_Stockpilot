"""Week 11 PostgreSQL backup and optional isolated restore rehearsal.

Usage: uv --project services/erp-core run python scripts/backup_restore_check.py OUTPUT.dump
Add --rehearse to require CREATEDB privilege and verify a newly created temporary database.
The source database is never restored over or dropped. The generated backup is retained.
Use PostgreSQL 17 client tools. Separately back up private_documents, identity keys and
the private identity snapshot; a database dump alone is NOT a full application backup.
"""

import argparse
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def counts(connection):
    tables = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
    ).fetchall()
    return {
        name: connection.execute(
            sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(name))
        ).fetchone()[0]
        for (name,) in tables
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rehearse", action="store_true")
    args = parser.parse_args()
    dsn = os.environ["DATABASE_URL"]
    parameters = conninfo_to_dict(dsn)
    env = os.environ.copy()
    # Libpq environment carries credentials; do not put passwords in process arguments.
    for key, value in parameters.items():
        env["PG" + key.upper().replace("DBNAME", "DATABASE")] = value
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as output, psycopg.connect(dsn) as source:
        source.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot = source.execute("SELECT pg_export_snapshot()").fetchone()[0]
        expected = counts(source)
        subprocess.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-acl", "--snapshot", snapshot],
            env=env,
            stdout=output,
            check=True,
        )
    print("Backup created. Treat it as confidential.")
    if not args.rehearse:
        return
    scratch = "stockpilot_restore_" + uuid4().hex
    created = False
    with psycopg.connect(dsn, autocommit=True) as admin:
        try:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(scratch)))
            created = True
            restore_env = env | {"PGDATABASE": scratch}
            subprocess.run(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-acl",
                    "--dbname",
                    scratch,
                    str(args.output),
                ],
                env=restore_env,
                check=True,
            )
            with psycopg.connect(make_conninfo(dsn, dbname=scratch)) as restored:
                if counts(restored) != expected:
                    raise RuntimeError("Restored table row counts differ from backup snapshot")
            print("Restore rehearsal passed: every public table row count matches the snapshot.")
        finally:
            # Only the unique database created by this invocation can be dropped.
            if created:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(scratch)))
                print("Removed the temporary rehearsal database; the backup remains available.")


if __name__ == "__main__":
    main()
