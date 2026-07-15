"""Class-session behaviour: resolution, per-session marking, day stats."""
from __future__ import annotations
from datetime import datetime, time

import pytest

from app.extensions import db as _db
from app.models.attendance import Attendance
from app.models.class_session import ClassSession
from app.services.attendance_service import AttendanceService


@pytest.fixture
def periods(db):
    p1 = ClassSession(name="Period 1", start_time=time(9, 0), end_time=time(10, 30))
    p2 = ClassSession(name="Period 2", start_time=time(10, 45), end_time=time(12, 15),
                      late_after_minutes=5)
    db.session.add_all([p1, p2])
    db.session.commit()
    return p1, p2


def test_resolve_picks_matching_window(app, periods):
    p1, p2 = periods
    assert ClassSession.resolve(time(9, 30)).session_id == p1.session_id
    assert ClassSession.resolve(time(11, 0)).session_id == p2.session_id


def test_resolve_falls_back_to_default(app, periods):
    session = ClassSession.resolve(time(14, 0))  # outside both windows
    assert session.is_default
    assert session.name == ClassSession.DEFAULT_NAME


def test_overlap_prefers_later_start(app, db):
    long_block = ClassSession(name="Block", start_time=time(9, 0), end_time=time(12, 0))
    nested = ClassSession(name="Lab", start_time=time(10, 0), end_time=time(11, 0))
    db.session.add_all([long_block, nested])
    db.session.commit()
    assert ClassSession.resolve(time(10, 30)).name == "Lab"
    assert ClassSession.resolve(time(9, 30)).name == "Block"


def test_student_marked_once_per_session(app, student, periods):
    first, created1 = AttendanceService.mark(
        student.student_id, now=datetime(2026, 7, 15, 9, 5))
    dup, created2 = AttendanceService.mark(
        student.student_id, now=datetime(2026, 7, 15, 9, 50))
    assert created1 and not created2
    assert dup.attendance_id == first.attendance_id


def test_student_marked_in_each_session(app, student, periods):
    p1, p2 = periods
    r1, c1 = AttendanceService.mark(student.student_id,
                                    now=datetime(2026, 7, 15, 9, 5))
    r2, c2 = AttendanceService.mark(student.student_id,
                                    now=datetime(2026, 7, 15, 10, 50))
    assert c1 and c2
    assert r1.session_id == p1.session_id
    assert r2.session_id == p2.session_id
    assert Attendance.query.count() == 2


def test_late_cutoff_uses_session_start_and_grace(app, student, periods):
    # Period 2 starts 10:45 with 5 min grace -> late from 10:51.
    on_time, _ = AttendanceService.mark(student.student_id,
                                        now=datetime(2026, 7, 15, 10, 49))
    assert on_time.status == Attendance.STATUS_PRESENT

    _db.session.delete(on_time)
    _db.session.commit()

    late, _ = AttendanceService.mark(student.student_id,
                                     now=datetime(2026, 7, 15, 10, 55))
    assert late.status == Attendance.STATUS_LATE


def test_day_stats_count_distinct_students(app, student, periods):
    # Present in P1, late to P2 -> one student, counted Present once.
    AttendanceService.mark(student.student_id, now=datetime(2026, 7, 15, 9, 5))
    AttendanceService.mark(student.student_id, now=datetime(2026, 7, 15, 11, 30))
    stats = AttendanceService.stats_for_date(datetime(2026, 7, 15).date())
    assert stats["marked"] == 1
    assert stats["present"] == 1
    assert stats["late"] == 0
    assert stats["attendance_percentage"] == 100.0


def test_default_session_cannot_be_deleted(logged_in_client, db):
    default = ClassSession.get_or_create_default()
    response = logged_in_client.post(f"/sessions/{default.session_id}/delete",
                                     follow_redirects=True)
    assert response.status_code == 200
    assert ClassSession.query.filter_by(is_default=True).count() == 1


def test_session_with_records_cannot_be_deleted(logged_in_client, db, student, periods):
    p1, _ = periods
    AttendanceService.mark(student.student_id, now=datetime(2026, 7, 15, 9, 5))
    logged_in_client.post(f"/sessions/{p1.session_id}/delete", follow_redirects=True)
    assert _db.session.get(ClassSession, p1.session_id) is not None


def test_create_session_via_route(logged_in_client):
    response = logged_in_client.post("/sessions/", data={
        "name": "Period 3", "start_time": "13:00", "end_time": "14:30",
        "late_after_minutes": "10",
    }, follow_redirects=True)
    assert response.status_code == 200
    created = ClassSession.query.filter_by(name="Period 3").first()
    assert created is not None
    assert created.late_after_minutes == 10
    assert created.start_time == time(13, 0)
