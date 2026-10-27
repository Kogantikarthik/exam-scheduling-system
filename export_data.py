
import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from database import DB_PATH, get_connection


BASE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = BASE_DIR / "exports"

CSV_DIR = EXPORT_DIR / "csv"
JSON_DIR = EXPORT_DIR / "json"


def sha256_file(path):
    """Calculate the SHA-256 hash of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def quote_identifier(name):
    """Safely quote an SQLite identifier."""
    return '"' + name.replace('"', '""') + '"'


def main():
    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}"
        )

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    exported_files = []
    table_summary = {}

    # Use the database configured in database.py.
    with get_connection() as source:
        # 1. Check database integrity.
        integrity = source.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                f"Database integrity check failed: {integrity}"
            )

        # 2. Check foreign-key relationships.
        foreign_key_errors = source.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if foreign_key_errors:
            raise RuntimeError(
                f"Database has {len(foreign_key_errors)} "
                "foreign-key violations."
            )

        # 3. Find all user-created tables.
        tables = [
            row[0]
            for row in source.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]

        # 4. Export ordinary tables to CSV and JSON.
        for table in tables:
            if table == "GroundTruth":
                continue

            quoted_table = quote_identifier(table)

            cursor = source.execute(
                f"SELECT * FROM {quoted_table}"
            )

            columns = [
                item[0] for item in cursor.description
            ]

            csv_path = CSV_DIR / f"{table}.csv"
            json_path = JSON_DIR / f"{table}.json"

            row_count = 0

            with (
                csv_path.open(
                    "w", newline="", encoding="utf-8-sig"
                ) as csv_file,
                json_path.open(
                    "w", encoding="utf-8"
                ) as json_file,
            ):
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow(columns)

                json_file.write("[\n")
                first_record = True

                while True:
                    rows = cursor.fetchmany(1000)

                    if not rows:
                        break

                    for row in rows:
                        csv_writer.writerow([
                            row[column] for column in columns
                        ])

                        if not first_record:
                            json_file.write(",\n")

                        json_file.write(
                            json.dumps(
                                dict(row),
                                ensure_ascii=False,
                                default=str,
                            )
                        )

                        first_record = False
                        row_count += 1

                json_file.write("\n]\n")

            table_summary[table] = {
                "row_count": row_count,
                "columns": columns,
            }

            exported_files.extend([
                csv_path,
                json_path,
            ])

            print(
                f"Exported {table}: {row_count} rows "
                "to CSV and JSON"
            )

        # 5. Export GroundTruth separately.
        if "GroundTruth" not in tables:
            raise RuntimeError(
                "GroundTruth table does not exist in the database."
            )

        ground_truth_columns = [
            "test_id",
            "issue_type",
            "expected_result",
            "description",
        ]

        ground_truth_rows = source.execute(
            """
            SELECT test_id, issue_type,
                   expected_result, description
            FROM GroundTruth
            ORDER BY test_id
            """
        ).fetchall()

        ground_truth_csv = EXPORT_DIR / "ground_truth.csv"
        ground_truth_json = EXPORT_DIR / "ground_truth.json"

        with ground_truth_csv.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.writer(file)
            writer.writerow(ground_truth_columns)

            for row in ground_truth_rows:
                writer.writerow([
                    row[column]
                    for column in ground_truth_columns
                ])

        with ground_truth_json.open(
            "w", encoding="utf-8"
        ) as file:
            json.dump(
                [dict(row) for row in ground_truth_rows],
                file,
                indent=2,
                ensure_ascii=False,
            )

        exported_files.extend([
            ground_truth_csv,
            ground_truth_json,
        ])

        print(
            "Exported separate ground truth: "
            f"{len(ground_truth_rows)} cases"
        )

        # 6. Create a consistent SQLite snapshot.
        snapshot_path = (
            EXPORT_DIR / "exam_scheduling_export.db"
        )

        destination = sqlite3.connect(snapshot_path)

        try:
            source.backup(destination)
        finally:
            destination.close()

        exported_files.append(snapshot_path)

        # 7. Create a portable SQL dump.
        sql_path = EXPORT_DIR / "exam_scheduling_export.sql"

        with sql_path.open(
            "w", encoding="utf-8"
        ) as sql_file:
            for statement in source.iterdump():
                sql_file.write(statement + "\n")

        exported_files.append(sql_path)

    # 8. Generate the manifest after closing the source connection.
    manifest = {
        "exported_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_database": DB_PATH.name,
        "source_database_path": str(DB_PATH),
        "integrity_check": "ok",
        "foreign_key_violations": 0,
        "table_count": len(table_summary),
        "tables": table_summary,
        "files": {},
    }

    for path in exported_files:
        manifest["files"][
            str(path.relative_to(EXPORT_DIR))
        ] = {
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    manifest_path = EXPORT_DIR / "manifest.json"

    with manifest_path.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            manifest,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print("\nExport completed successfully.")
    print("Source database:", DB_PATH)
    print("Tables exported:", len(table_summary))
    print("Output folder:", EXPORT_DIR)
    print("Manifest:", manifest_path)
    print("SQL dump:", sql_path)
    print("SQLite snapshot:", snapshot_path)


if __name__ == "__main__":
    main()
