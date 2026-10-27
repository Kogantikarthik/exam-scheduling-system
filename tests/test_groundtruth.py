import sqlite3
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "exam_scheduling.db"


EXPECTED_CASES = {
    "TEST-001": (
        "STUDENT_OVERLAPPING_EXAMS",
        "REJECT_CONFLICTING_SLOT",
    ),
    "TEST-002": (
        "ROOM_CAPACITY_EXCEEDED",
        "REJECT_ROOM",
    ),
    "TEST-003": (
        "INVIGILATOR_DOUBLE_BOOKED",
        "REJECT_DOUBLE_BOOKING",
    ),
    "TEST-004": (
        "ACCOMMODATION_IGNORED",
        "REJECT_ASSIGNMENT",
    ),
    "TEST-005": (
        "EXAM_OUTSIDE_ROOM_AVAILABILITY",
        "REJECT_CLOSED_ROOM",
    ),
}


class GroundTruthTests(unittest.TestCase):

    def setUp(self):
        if not DB_PATH.exists():
            self.fail(f"Database not found: {DB_PATH}")

        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row

    def tearDown(self):
        self.conn.close()

    def test_all_five_groundtruth_cases_exist(self):
        rows = self.conn.execute(
            "SELECT * FROM GroundTruth"
        ).fetchall()

        actual_ids = {row["test_id"] for row in rows}

        self.assertEqual(
            actual_ids,
            set(EXPECTED_CASES.keys()),
            "GroundTruth must contain exactly the five expected test IDs.",
        )

    def test_issue_types_and_expected_results(self):
        for test_id, expected in EXPECTED_CASES.items():
            row = self.conn.execute(
                """
                SELECT issue_type, expected_result
                FROM GroundTruth
                WHERE test_id = ?
                """,
                (test_id,),
            ).fetchone()

            self.assertIsNotNone(
                row,
                f"{test_id} is missing from GroundTruth.",
            )

            self.assertEqual(
                (row["issue_type"], row["expected_result"]),
                expected,
                f"{test_id} has an incorrect label or expected result.",
            )

    def test_every_case_has_a_description(self):
        rows = self.conn.execute(
            "SELECT test_id, description FROM GroundTruth"
        ).fetchall()

        for row in rows:
            self.assertTrue(
                row["description"]
                and row["description"].strip(),
                f"{row['test_id']} has no description.",
            )


if __name__ == "__main__":
    unittest.main()