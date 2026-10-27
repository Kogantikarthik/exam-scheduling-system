# Exam Scheduling and Room Allocation System
## Live Demo

Try the deployed application: https://exam-scheduling-system.streamlit.app/

## 1. Project Overview

The Exam Scheduling and Room Allocation System is a Python-based application that generates exam schedules while considering student enrollment, room capacity, room availability, accessibility requirements, exam duration, and invigilator availability.

The application uses SQLite for data storage and Streamlit for the interactive dashboard. It also maintains scheduling event history and provides CSV, JSON, and SQL exports.

**Dataset:** Synthetic demonstration data only.

## 2. Key Features

- Automated exam and room scheduling.
- Student examination conflict detection.
- Room capacity and availability validation.
- Accessibility and equipment requirement checks.
- Invigilator availability and double-booking prevention.
- Reason-coded unscheduled exams.
- Append-only scheduling event history.
- Interactive Streamlit dashboard with filters and downloads.
- CSV, JSON, and SQL data exports.
- Reproducible synthetic data generation using a fixed random seed.
- Data dictionary and GroundTruth test cases.

## 3. Technology Stack

- Python
- SQLite
- Streamlit
- Pandas
- SQL
- CSV and JSON

## 4. Project Setup

Run the following commands in Windows Command Prompt from the project directory.

Create and activate a virtual environment if one does not already exist:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```cmd
python -m pip install -r requirements.txt
```

## 5. Generate the Dataset

Generate the default synthetic dataset:

```cmd
python generate_data.py
```

The default configuration uses seed `20261022` and generates 5,000 students, 300 exams, 100 rooms, and 200 invigilators.

The generator creates `generated_exam_scheduling.db`.

## 6. Generate and Validate the Schedule

Select the generated database:

```cmd
set "EXAM_SCHEDULING_DB=%CD%\generated_exam_scheduling.db"
```

Run the scheduler:

```cmd
python scheduler.py
```

Validate the generated schedule:

```cmd
python validator.py
```

Review `validation_report.json` for validation results.

## 7. Launch the Dashboard

```cmd
python -m streamlit run app.py
```

Open the local URL displayed in the terminal, normally `http://localhost:8501`.

The dashboard provides a scheduling overview, exam schedule, unscheduled exams, audit history, and data overview.

## 8. Export Data

Run:

```cmd
python export_data.py
```

Exports are written to the `exports` directory, including CSV and JSON table files, a SQLite snapshot, an SQL dump, and a manifest containing export metadata and checksums.

## 9. Reproducibility

To generate a second database using the same seed:

```cmd
python generate_data.py --output reproducibility_test.db --seed 20261022
python check_reproducibility.py
```

The reproducibility checker compares the generated database with the reference database.

## 10. GroundTruth Scenarios

The dataset includes five documented negative scenarios:

1. Overlapping examinations for a student.
2. Room capacity exceeded.
3. Invigilator double-booking.
4. Required accommodation ignored.
5. Examination scheduled outside room availability.

These scenarios represent expected rejection conditions and support validation of scheduling rules.

## 11. Data and Integrity

The SQLite schema defines primary keys, foreign keys, uniqueness constraints, validation checks, lifecycle states, and effective dates where applicable. Scheduling changes are recorded as events to preserve audit history.

Synthetic records are generated for demonstration and testing. The system should be validated against institutional policies and real operational requirements before deployment.

## 12. Limitations

This is a demonstration project using synthetic data. Scheduling outcomes depend on the implemented rules and available generated resources. A successful validation report indicates that the implemented checks passed; it does not guarantee suitability for every real-world institution.
