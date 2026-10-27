
from database import get_connection

with get_connection() as conn:
    for table in [
        "TimeSlot",
        "ScheduleEvent",
        "GroundTruth",
        "UnassignedExam",
        "ConflictGraph",
        "ScheduleAssignment",
    ]:
        print(f"\n{'=' * 60}\n{table}")

        rows = conn.execute(
            f'PRAGMA table_info("{table}")'
        ).fetchall()

        for row in rows:
            print(dict(row))

        print("CREATE TABLE:")
        result = conn.execute("""
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = ?
        """, (table,)).fetchone()
        print(result["sql"] if result else "TABLE NOT FOUND")

    print("\nTRIGGERS")
    for row in conn.execute("""
        SELECT name, tbl_name, sql
        FROM sqlite_master
        WHERE type = 'trigger'
    """):
        print(dict(row))
