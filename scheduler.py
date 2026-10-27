
from datetime import datetime
from collections import defaultdict
import json

from database import get_connection


def minutes_between(start, end):
    start_time = datetime.fromisoformat(start)
    end_time = datetime.fromisoformat(end)
    return int((end_time - start_time).total_seconds() / 60)


def next_id(conn, table, column, prefix):
    count = conn.execute(
        f'SELECT COUNT(*) FROM "{table}"'
    ).fetchone()[0]
    return f"{prefix}{count + 1:07d}"


def insert_event(
    conn, exam_id, assignment_id, event_type,
    old_status, new_status, reason_code=None, details=None
):
    event_id = next_id(conn, "ScheduleEvent", "event_id", "EVT-")

    columns = [
        "event_id", "assignment_id", "exam_id", "event_type",
        "old_status", "new_status", "event_time", "reason_code"
    ]
    values = [
        event_id, assignment_id, exam_id, event_type,
        old_status, new_status,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        reason_code
    ]

    # Support schemas that include a JSON event-details column.
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(ScheduleEvent)")
    }
    if "details_json" in existing_columns:
        columns.append("details_json")
        values.append(json.dumps(details or {}))

    sql = (
        f'INSERT INTO ScheduleEvent ({", ".join(columns)}) '
        f'VALUES ({", ".join("?" for _ in columns)})'
    )
    conn.execute(sql, values)


def generate_schedule():
    with get_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        existing = conn.execute("""
            SELECT COUNT(*) FROM ScheduleAssignment
            WHERE status = 'ASSIGNED'
        """).fetchone()[0]

        if existing:
            raise RuntimeError(
                "An active schedule already exists. "
                "Back up the database before implementing a rescheduling workflow."
            )

        exams = conn.execute("""
            SELECT
                e.exam_id,
                e.course_id,
                e.exam_name,
                e.base_duration_minutes,
                e.estimated_students,
                e.status AS exam_status,
                q.required_duration_minutes,
                q.required_seats,
                q.accessible_room_required,
                q.projector_required
            FROM Exam e
            JOIN ExamRequirement q ON q.exam_id = e.exam_id
            WHERE e.status != 'CANCELLED'
        """).fetchall()

        slots = conn.execute("""
            SELECT slot_id, start_datetime, end_datetime
            FROM TimeSlot
            ORDER BY start_datetime
        """).fetchall()

        rooms = conn.execute("""
            SELECT
                r.room_id,
                r.accessible,
                r.has_projector,
                r.status AS room_status,
                c.capacity,
                c.effective_from,
                c.effective_to
            FROM Room r
            JOIN RoomCapacity c ON c.room_id = r.room_id
            WHERE r.status = 'ACTIVE'
        """).fetchall()

        invigilators = conn.execute("""
            SELECT invigilator_id
            FROM Invigilator
            WHERE status = 'ACTIVE'
        """).fetchall()

        # Availability values must be exactly AVAILABLE.
        availability = {}
        for row in conn.execute("""
            SELECT resource_type, resource_id, slot_id, status
            FROM Availability
        """):
            availability[
                (row["resource_type"], row["resource_id"], row["slot_id"])
            ] = row["status"]

        # Construct the exam conflict graph.
        conflicts = defaultdict(set)
        for row in conn.execute("""
            SELECT exam_id_1, exam_id_2
            FROM ConflictGraph
        """):
            conflicts[row["exam_id_1"]].add(row["exam_id_2"])
            conflicts[row["exam_id_2"]].add(row["exam_id_1"])

        # Read active accommodation requirements for each exam's course.
        # The maximum extra time is used because this first version assigns
        # the whole exam to one room.
        accommodations = {}
        for exam in exams:
            result = conn.execute("""
                SELECT
                    MAX(ac.extra_time_minutes) AS extra_minutes,
                    MAX(ac.needs_accessible_room) AS needs_accessible
                FROM Enrollment en
                JOIN Accommodation ac
                  ON ac.student_id = en.student_id
                WHERE en.course_id = ?
                  AND en.status = 'ACTIVE'
                  AND ac.status = 'ACTIVE'
            """, (exam["course_id"],)).fetchone()

            accommodations[exam["exam_id"]] = {
                "extra": result["extra_minutes"] or 0,
                "accessible": bool(result["needs_accessible"])
            }

        # Track assigned exams and occupied room/invigilator intervals.
        assigned_slots = {}
        room_busy = defaultdict(list)
        invigilator_busy = defaultdict(list)
        results = []

        # Schedule more constrained exams first.
        exams = sorted(
            exams,
            key=lambda exam: (
                -len(conflicts[exam["exam_id"]]),
                -exam["estimated_students"],
                -exam["required_duration_minutes"],
                exam["exam_id"]
            )
        )

        for exam in exams:
            exam_id = exam["exam_id"]
            accommodation = accommodations[exam_id]

            duration_needed = max(
                exam["required_duration_minutes"],
                exam["base_duration_minutes"] + accommodation["extra"]
            )
            seats_needed = max(
                exam["required_seats"],
                exam["estimated_students"]
            )
            needs_accessible = (
                bool(exam["accessible_room_required"])
                or accommodation["accessible"]
            )

            selected = None
            reason = "NO_SUITABLE_ROOM"

            suitable_room_found = False
            available_room_found = False
            available_invigilator_found = False
            duration_slot_found = False
            student_conflict_found = False

            for slot in slots:
                if minutes_between(
                    slot["start_datetime"], slot["end_datetime"]
                ) < duration_needed:
                    continue

                duration_slot_found = True
                slot_date = slot["start_datetime"][:10]

                # Avoid overlapping exams that share enrolled students.
                conflict_found = False
                for other_exam, other_slot_id in assigned_slots.items():
                    if other_exam not in conflicts[exam_id]:
                        continue

                    other_slot = next(
                        s for s in slots if s["slot_id"] == other_slot_id
                    )

                    overlap = (
                        slot["start_datetime"] < other_slot["end_datetime"]
                        and other_slot["start_datetime"] < slot["end_datetime"]
                    )
                    if overlap:
                        conflict_found = True
                        break

                if conflict_found:
                    student_conflict_found = True
                    continue

                for room in rooms:
                    if room["capacity"] < seats_needed:
                        continue
                    if room["effective_from"] > slot_date:
                        continue
                    if (
                        room["effective_to"]
                        and room["effective_to"] < slot_date
                    ):
                        continue
                    if needs_accessible and not room["accessible"]:
                        continue
                    if (
                        exam["projector_required"]
                        and not room["has_projector"]
                    ):
                        continue

                    suitable_room_found = True

                    if availability.get(
                        ("ROOM", room["room_id"], slot["slot_id"])
                    ) != "AVAILABLE":
                        continue

                    available_room_found = True

                    # Room must not be occupied by another exam at this time.
                    room_overlap = any(
                        slot["start_datetime"] < end
                        and start < slot["end_datetime"]
                        for start, end in room_busy[room["room_id"]]
                    )
                    if room_overlap:
                        continue

                    for invigilator in invigilators:
                        inv_id = invigilator["invigilator_id"]

                        if availability.get(
                            ("INVIGILATOR", inv_id, slot["slot_id"])
                        ) != "AVAILABLE":
                            continue

                        available_invigilator_found = True

                        inv_overlap = any(
                            slot["start_datetime"] < end
                            and start < slot["end_datetime"]
                            for start, end
                            in invigilator_busy[inv_id]
                        )
                        if inv_overlap:
                            continue

                        selected = (slot, room, inv_id)
                        break

                    if selected:
                        break

                if selected:
                    break

            if selected is None:
                if not duration_slot_found:
                    reason = "DURATION_EXCEEDS_SLOT"
                elif student_conflict_found:
                    reason = "STUDENT_CONFLICT"
                elif not suitable_room_found:
                    reason = "INSUFFICIENT_CAPACITY"
                elif not available_room_found:
                    reason = "NO_ROOM_AVAILABLE"
                elif not available_invigilator_found:
                    reason = "NO_INVIGILATOR_AVAILABLE"
                else:
                    reason = "NO_INVIGILATOR_AVAILABLE"

                detail = (
                    f"Required duration: {duration_needed} minutes; "
                    f"required seats: {seats_needed}; "
                    f"accessible room required: {needs_accessible}."
                )

                unassigned_id = next_id(
                    conn, "UnassignedExam", "unassigned_id", "UNA-"
                )

                conn.execute("""
                    INSERT INTO UnassignedExam
                    (unassigned_id, exam_id, reason_code, detail, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (unassigned_id, exam_id, reason, detail))

                conn.execute("""
                    UPDATE Exam SET status = 'UNSCHEDULED'
                    WHERE exam_id = ?
                """, (exam_id,))

                insert_event(
                    conn, exam_id, None, "UNASSIGNED",
                    exam["exam_status"], "UNSCHEDULED",
                    reason, {"detail": detail}
                )

                results.append({
                    "exam_id": exam_id,
                    "status": "UNSCHEDULED",
                    "reason_code": reason
                })
                continue

            slot, room, inv_id = selected
            assignment_id = f"ASN-{exam_id}-{room['room_id']}"

            # Preserve history: do not overwrite or delete old assignments.
            duplicate = conn.execute("""
                SELECT 1 FROM ScheduleAssignment
                WHERE assignment_id = ?
            """, (assignment_id,)).fetchone()

            if duplicate:
                raise RuntimeError(
                    f"Assignment {assignment_id} already exists. "
                    "A rescheduling workflow is required."
                )

            conn.execute("""
                INSERT INTO ScheduleAssignment (
                    assignment_id, exam_id, room_id, slot_id,
                    invigilator_id, assigned_seats, status,
                    created_at, reason_code
                )
                VALUES (?, ?, ?, ?, ?, ?, 'ASSIGNED', datetime('now'), NULL)
            """, (
                assignment_id, exam_id, room["room_id"],
                slot["slot_id"], inv_id, seats_needed
            ))

            conn.execute("""
                UPDATE Exam SET status = 'SCHEDULED'
                WHERE exam_id = ?
            """, (exam_id,))

            insert_event(
                conn, exam_id, assignment_id, "ASSIGNED",
                exam["exam_status"], "SCHEDULED",
                details={
                    "slot_id": slot["slot_id"],
                    "room_id": room["room_id"],
                    "invigilator_id": inv_id,
                    "duration_minutes": duration_needed,
                    "assigned_seats": seats_needed
                }
            )

            assigned_slots[exam_id] = slot["slot_id"]
            room_busy[room["room_id"]].append(
                (slot["start_datetime"], slot["end_datetime"])
            )
            invigilator_busy[inv_id].append(
                (slot["start_datetime"], slot["end_datetime"])
            )

            results.append({
                "exam_id": exam_id,
                "status": "SCHEDULED",
                "slot_id": slot["slot_id"],
                "room_id": room["room_id"],
                "invigilator_id": inv_id,
                "assigned_seats": seats_needed
            })

        conn.commit()

    scheduled = sum(r["status"] == "SCHEDULED" for r in results)
    unscheduled = sum(r["status"] == "UNSCHEDULED" for r in results)

    return {
        "scheduled": scheduled,
        "unscheduled": unscheduled,
        "results": results
    }


if __name__ == "__main__":
    try:
        result = generate_schedule()
        print("Scheduling completed.")
        print("Scheduled:", result["scheduled"])
        print("Unscheduled:", result["unscheduled"])

        for item in result["results"]:
            if item["status"] == "UNSCHEDULED":
                print(item)

    except Exception as error:
        print("Scheduler error:", error)
        raise
