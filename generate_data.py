
import argparse
import random
import sqlite3
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path


DEFAULT_SEED = 20261022
BASE_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = BASE_DIR / "schema_v2.sql"


def make_id(prefix, number, width=5):
    return f"{prefix}{number:0{width}d}"


def generate_database(
    output_path,
    seed=DEFAULT_SEED,
    students=5000,
    exams=300,
    rooms=100,
    invigilators=200,
):
    if min(students, exams, rooms, invigilators) < 1:
        raise ValueError("All record counts must be positive.")

    if exams < 5:
        raise ValueError("Use at least 5 exams for this dataset.")

    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(f"Missing schema: {SCHEMA_FILE}")

    output_path = Path(output_path).resolve()

    if output_path == (BASE_DIR / "exam_scheduling.db").resolve():
        raise ValueError("Cannot overwrite the existing project database.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        output_path.unlink()

    rng = random.Random(seed)
    connection = sqlite3.connect(output_path)
    connection.execute("PRAGMA foreign_keys = ON")

    try:
        schema = SCHEMA_FILE.read_text(encoding="utf-8")
        connection.executescript(schema)

        cursor = connection.cursor()

        # 1. Students
        student_ids = [
            make_id("STU", i)
            for i in range(1, students + 1)
        ]

        cursor.executemany(
            "INSERT INTO Student VALUES (?, ?, ?)",
            [
                (sid, f"Synthetic Student {i:05d}", "ACTIVE")
                for i, sid in enumerate(student_ids, start=1)
            ],
        )

        # 2. Courses and exams: one exam per course
        course_ids = [
            make_id("CRS", i)
            for i in range(1, exams + 1)
        ]

        departments = [
            "Computer Science",
            "Mathematics",
            "Physics",
            "Electronics",
            "Management",
        ]

        cursor.executemany(
            "INSERT INTO Course VALUES (?, ?, ?, ?)",
            [
                (
                    cid,
                    f"Synthetic Course {i:03d}",
                    departments[(i - 1) % len(departments)],
                    "ACTIVE",
                )
                for i, cid in enumerate(course_ids, start=1)
            ],
        )

        # 3. Enroll students in 4 or 5 distinct courses where possible.
        # Use course-to-student sets to derive conflicts accurately.
        course_students = defaultdict(set)
        enrollment_rows = []
        enrollment_number = 1

        for student_number, sid in enumerate(student_ids):
            course_count = min(
                len(course_ids),
                4 + rng.randint(0, 1),
            )
            selected_courses = rng.sample(course_ids, course_count)

            for cid in selected_courses:
                enrollment_rows.append(
                    (
                        make_id("ENR", enrollment_number),
                        sid,
                        cid,
                        "2026-08-01",
                        "ACTIVE",
                    )
                )
                course_students[cid].add(sid)
                enrollment_number += 1

        cursor.executemany(
            "INSERT INTO Enrollment VALUES (?, ?, ?, ?, ?)",
            enrollment_rows,
        )

        # 4. Exams and their requirements
        exam_rows = []
        requirement_rows = []

        for i, cid in enumerate(course_ids, start=1):
            exam_id = make_id("EXM", i)
            enrolled_count = len(course_students[cid])
            base_duration = rng.choice([90, 120])
            extra_time = rng.choice([0, 30, 60])

            exam_rows.append(
                (
                    exam_id,
                    cid,
                    f"Synthetic Exam {i:03d}",
                    base_duration,
                    enrolled_count,
                    "PLANNED",
                )
            )

            requirement_rows.append(
                (
                    make_id("REQ", i),
                    exam_id,
                    extra_time,
                    base_duration + extra_time,
                    int(rng.random() < 0.15),
                    int(rng.random() < 0.20),
                    max(1, enrolled_count),
                )
            )

        cursor.executemany(
            "INSERT INTO Exam VALUES (?, ?, ?, ?, ?, ?)",
            exam_rows,
        )
        cursor.executemany(
            "INSERT INTO ExamRequirement VALUES (?, ?, ?, ?, ?, ?, ?)",
            requirement_rows,
        )

        # 5. Rooms and effective-dated capacity
        room_ids = [
            make_id("ROM", i)
            for i in range(1, rooms + 1)
        ]

        room_rows = []
        capacity_rows = []

        for i, rid in enumerate(room_ids, start=1):
            room_status = (
                "MAINTENANCE" if i % 25 == 0 else "ACTIVE"
            )
            capacity = rng.randint(120, 200)

            room_rows.append(
                (
                    rid,
                    f"Synthetic Room {i:03d}",
                    int(i % 3 != 0),
                    int(i % 4 != 0),
                    room_status,
                )
            )

            capacity_rows.append(
                (
                    make_id("CAP", i),
                    rid,
                    capacity,
                    "2026-11-01",
                    None,
                )
            )

        cursor.executemany(
            "INSERT INTO Room VALUES (?, ?, ?, ?, ?)",
            room_rows,
        )
        cursor.executemany(
            "INSERT INTO RoomCapacity VALUES (?, ?, ?, ?, ?)",
            capacity_rows,
        )

        # 6. Invigilators
        invigilator_ids = [
            make_id("INV", i)
            for i in range(1, invigilators + 1)
        ]

        cursor.executemany(
            "INSERT INTO Invigilator VALUES (?, ?, ?)",
            [
                (
                    iid,
                    f"Synthetic Invigilator {i:03d}",
                    "ON_LEAVE" if i % 30 == 0 else "ACTIVE",
                )
                for i, iid in enumerate(invigilator_ids, start=1)
            ],
        )

        # 7. Ninety three-hour time slots: 3 slots per day for 30 days
        slot_rows = []
        slot_number = 1
        first_day = date(2026, 11, 2)
        start_times = [time(8, 0), time(12, 0), time(16, 0)]

        for day_offset in range(30):
            slot_day = first_day + timedelta(days=day_offset)

            for start_time in start_times:
                start_dt = datetime.combine(slot_day, start_time)
                end_dt = start_dt + timedelta(minutes=180)

                slot_rows.append(
                    (
                        make_id("SLT", slot_number),
                        start_dt.isoformat(timespec="seconds"),
                        end_dt.isoformat(timespec="seconds"),
                        slot_day.isoformat(),
                        180,
                    )
                )
                slot_number += 1

        cursor.executemany(
            "INSERT INTO TimeSlot VALUES (?, ?, ?, ?, ?)",
            slot_rows,
        )

        # 8. Resource availability for every resource and every slot
        availability_rows = []
        availability_number = 1

        for resource_type, resource_ids in [
            ("ROOM", room_ids),
            ("INVIGILATOR", invigilator_ids),
        ]:
            for resource_id in resource_ids:
                for slot in slot_rows:
                    unavailable = rng.random() < 0.02

                    if resource_type == "ROOM":
                        unavailable = (
                            unavailable
                            or (
                                next(
                                    r[4]
                                    for r in room_rows
                                    if r[0] == resource_id
                                )
                                != "ACTIVE"
                            )
                        )
                    else:
                        unavailable = (
                            unavailable
                            or (
                                next(
                                    r[2]
                                    for r in [
                                        (
                                            iid,
                                            f"Synthetic Invigilator {i:03d}",
                                            "ON_LEAVE" if i % 30 == 0 else "ACTIVE",
                                        )
                                        for i, iid in enumerate(
                                            invigilator_ids, start=1
                                        )
                                    ]
                                    if r[0] == resource_id
                                )
                                != "ACTIVE"
                            )
                        )

                    status = "UNAVAILABLE" if unavailable else "AVAILABLE"
                    reason = (
                        "SYNTHETIC_UNAVAILABILITY"
                        if unavailable
                        else None
                    )

                    availability_rows.append(
                        (
                            make_id("AVL", availability_number),
                            resource_type,
                            resource_id,
                            slot[0],
                            slot[1],
                            slot[2],
                            status,
                            reason,
                        )
                    )
                    availability_number += 1

        cursor.executemany(
            """
            INSERT INTO Availability
            (availability_id, resource_type, resource_id, slot_id,
             start_datetime, end_datetime, status, reason_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            availability_rows,
        )

        # 9. Synthetic accommodations with effective dates
        accommodation_rows = []
        accommodation_number = 1
        accommodation_count = round(students * 0.15)

        for sid in rng.sample(
            student_ids,
            min(accommodation_count, len(student_ids)),
        ):
            needs_accessible = int(rng.random() < 0.35)
            extra_time = rng.choice([30, 60])

            accommodation_rows.append(
                (
                    make_id("ACC", accommodation_number),
                    sid,
                    needs_accessible,
                    extra_time,
                    "2026-08-01",
                    None,
                    "ACTIVE",
                )
            )
            accommodation_number += 1

        cursor.executemany(
            "INSERT INTO Accommodation VALUES (?, ?, ?, ?, ?, ?, ?)",
            accommodation_rows,
        )

        # 10. Conflict graph derived from shared enrolled students
        conflict_rows = []

        for i, course_1 in enumerate(course_ids):
            for course_2 in course_ids[i + 1:]:
                shared = len(
                    course_students[course_1]
                    & course_students[course_2]
                )

                if shared:
                    conflict_rows.append(
                        (
                            make_id("EXM", i + 1),
                            make_id("EXM", course_ids.index(course_2) + 1),
                            shared,
                        )
                    )

        cursor.executemany(
            "INSERT INTO ConflictGraph VALUES (?, ?, ?)",
            conflict_rows,
        )

        # 11. Documented ground-truth cases
        ground_truth_rows = [
            (
                "TEST-001",
                "STUDENT_OVERLAPPING_EXAMS",
                "REJECT_CONFLICTING_SLOT",
                "Two exams sharing a student must not overlap.",
            ),
            (
                "TEST-002",
                "ROOM_CAPACITY_EXCEEDED",
                "REJECT_ROOM",
                "An assignment must not exceed effective room capacity.",
            ),
            (
                "TEST-003",
                "INVIGILATOR_DOUBLE_BOOKED",
                "REJECT_DOUBLE_BOOKING",
                "An invigilator cannot supervise overlapping exams.",
            ),
            (
                "TEST-004",
                "ACCOMMODATION_IGNORED",
                "REJECT_ASSIGNMENT",
                "Accessibility and extra-time requirements must be respected.",
            ),
            (
                "TEST-005",
                "EXAM_OUTSIDE_ROOM_AVAILABILITY",
                "REJECT_CLOSED_ROOM",
                "An exam cannot use a room during an unavailable slot.",
            ),
        ]

        cursor.executemany(
            "INSERT INTO GroundTruth VALUES (?, ?, ?, ?)",
            ground_truth_rows,
        )

        # 12. Build the data dictionary from the actual database schema
        dictionary_rows = []

        table_names = [
            row[0]
            for row in cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table'
                  AND name NOT LIKE 'sqlite_%'
                  AND name != 'DataDictionary'
                ORDER BY name
                """
            )
        ]

        for table_name in table_names:
            columns = cursor.execute(
                f'PRAGMA table_info("{table_name}")'
            ).fetchall()

            for column in columns:
                _, field, data_type, not_null, _, primary_key = column
                required = "Yes" if not_null or primary_key else "No"
                unique = "Yes" if primary_key else "See schema constraints"

                dictionary_rows.append(
                    (
                        table_name,
                        field,
                        data_type or "TEXT",
                        required,
                        "See schema_v2.sql CHECK constraints",
                        unique,
                        "See schema_v2.sql",
                    )
                )

        cursor.executemany(
            """
            INSERT INTO DataDictionary
            ("table", field, data_type, required,
             allowed_values_or_units, "unique", validation_rule)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            dictionary_rows,
        )

        # Validate database integrity before finishing
        fk_errors = cursor.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        if fk_errors:
            raise RuntimeError(
                f"Foreign-key validation failed: {fk_errors[:5]}"
            )

        integrity = cursor.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")

        connection.commit()

        print("Synthetic database created successfully.")
        print(f"Output: {output_path}")
        print(f"Seed: {seed}")

        for table_name in table_names:
            count = cursor.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
            print(f"{table_name}: {count}")

        print(f"DataDictionary: {len(dictionary_rows)}")
        print("Foreign-key check: PASS")
        print("SQLite integrity check: PASS")

    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate a reproducible synthetic exam scheduling database."
    )
    parser.add_argument(
        "--output",
        default="generated_exam_scheduling.db",
        help="Output database path (default: generated_exam_scheduling.db)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--students", type=int, default=5000)
    parser.add_argument("--exams", type=int, default=300)
    parser.add_argument("--rooms", type=int, default=100)
    parser.add_argument("--invigilators", type=int, default=200)

    args = parser.parse_args()

    generate_database(
        output_path=args.output,
        seed=args.seed,
        students=args.students,
        exams=args.exams,
        rooms=args.rooms,
        invigilators=args.invigilators,
    )


if __name__ == "__main__":
    main()
