
import sqlite3
import sys
from pathlib import Path


def read_database(path):
    connection = sqlite3.connect(path)

    try:
        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]

        snapshot = {}

        for table in tables:
            columns = [
                row[1]
                for row in connection.execute(
                    f'PRAGMA table_info("{table}")'
                )
            ]

            quoted_columns = ", ".join(
                f'"{column}"' for column in columns
            )

            rows = connection.execute(
                f'SELECT {quoted_columns} FROM "{table}"'
            ).fetchall()

            snapshot[table] = (
                columns,
                sorted(rows, key=repr),
            )

        return snapshot
    finally:
        connection.close()


first_path = Path("generated_exam_scheduling.db")
second_path = Path("reproducibility_test.db")

if not first_path.exists() or not second_path.exists():
    sys.exit("FAIL: One or both database files are missing.")

first = read_database(first_path)
second = read_database(second_path)

if first == second:
    print("PASS: Both databases have identical tables and data.")
    print("Seed: 20261022")
    print(f"Tables compared: {len(first)}")
else:
    print("FAIL: The databases differ.")

    for table in sorted(set(first) | set(second)):
        if first.get(table) != second.get(table):
            print(f"Different table: {table}")

    sys.exit(1)
