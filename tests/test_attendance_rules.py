"""Business rules: once-per-day, Present/Late cutoff, stats."""
from datetime import datetime

from app.models.attendance import Attendance
from app.services.attendance_service import AttendanceService


def test_marked_present_before_cutoff(app, student):
    # Config default: start 09:00 + 15 min grace -> cutoff 09:15.
    record, created = AttendanceService.mark(
        student.student_id, confidence=0.9,
        now=datetime(2026, 7, 15, 8, 55),
    )
    assert created
    assert record.status == Attendance.STATUS_PRESENT
    assert record.confidence_score == 0.9


def test_marked_late_after_cutoff(app, student):
    record, created = AttendanceService.mark(
        student.student_id, now=datetime(2026, 7, 15, 9, 30),
    )
    assert created
    assert record.status == Attendance.STATUS_LATE


def test_boundary_time_is_present(app, student):
    record, _ = AttendanceService.mark(
        student.student_id, now=datetime(2026, 7, 15, 9, 15),
    )
    assert record.status == Attendance.STATUS_PRESENT


def test_duplicate_marking_is_ignored(app, student):
    first, created_first = AttendanceService.mark(
        student.student_id, confidence=0.8, now=datetime(2026, 7, 15, 8, 50),
    )
    second, created_second = AttendanceService.mark(
        student.student_id, confidence=0.99, now=datetime(2026, 7, 15, 10, 0),
    )
    assert created_first and not created_second
    assert second.attendance_id == first.attendance_id
    assert Attendance.query.count() == 1
    # Original record untouched by the second sighting.
    assert second.status == Attendance.STATUS_PRESENT
    assert second.confidence_score == 0.8


def test_same_student_next_day_is_new_record(app, student):
    AttendanceService.mark(student.student_id, now=datetime(2026, 7, 15, 9, 0))
    _, created = AttendanceService.mark(student.student_id,
                                        now=datetime(2026, 7, 16, 9, 0))
    assert created
    assert Attendance.query.count() == 2


def test_stats_for_date(app, db, student):
    from app.models.student import Student

    other = Student(full_name="Grace Hopper", roll_number="CS-002",
                    department="Computer Science", year=2)
    db.session.add(other)
    db.session.commit()

    AttendanceService.mark(student.student_id, now=datetime(2026, 7, 15, 8, 50))
    stats = AttendanceService.stats_for_date(datetime(2026, 7, 15).date())
    assert stats["total_students"] == 2
    assert stats["present"] == 1
    assert stats["late"] == 0
    assert stats["absent"] == 1
    assert stats["attendance_percentage"] == 50.0
