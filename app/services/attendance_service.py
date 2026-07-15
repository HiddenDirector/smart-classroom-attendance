"""Attendance business rules: once-per-day marking and Present/Late status.

Kept free of Flask request objects so it can be called from HTTP routes,
the recognition pipeline thread, the CLI, and unit tests alike. ``now`` is
injectable everywhere for deterministic testing.
"""
from __future__ import annotations
import logging
from datetime import date as date_cls
from datetime import datetime, time as time_cls, timedelta

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.attendance import Attendance
from app.models.class_session import ClassSession
from app.models.student import Student

log = logging.getLogger(__name__)


class AttendanceService:
    @staticmethod
    def determine_status(arrival: time_cls, session: ClassSession) -> str:
        cutoff = session.late_cutoff(current_app.config)
        return (
            Attendance.STATUS_PRESENT if arrival <= cutoff else Attendance.STATUS_LATE
        )

    @classmethod
    def mark(
        cls,
        student_id: int,
        confidence: float | None = None,
        now: datetime | None = None,
        session: ClassSession | None = None,
    ) -> tuple[Attendance, bool]:
        """Mark a student present for the class session covering ``now``.

        The session is resolved from the time of day (falling back to the
        whole-day default), so a student entering during Period 2 gets a
        Period 2 record even if they were already marked in Period 1.

        Returns ``(record, created)`` — ``created`` is False when the student
        was already marked for this session, and the existing record is
        returned untouched.
        """
        now = now or datetime.now()
        today = now.date()
        session = session or ClassSession.resolve(now.time())

        existing = Attendance.query.filter_by(
            student_id=student_id, date=today, session_id=session.session_id
        ).first()
        if existing:
            return existing, False

        record = Attendance(
            student_id=student_id,
            session_id=session.session_id,
            date=today,
            time=now.time().replace(microsecond=0),
            status=cls.determine_status(now.time(), session),
            confidence_score=confidence,
        )
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError:
            # Two recognition events raced past the fast-path check; the
            # UNIQUE constraint wins and we return the surviving row.
            db.session.rollback()
            existing = Attendance.query.filter_by(
                student_id=student_id, date=today, session_id=session.session_id
            ).first()
            return existing, False

        log.info(
            "Attendance marked: student=%s session=%s status=%s confidence=%s",
            student_id, session.name, record.status, confidence,
        )
        return record, True

    @staticmethod
    def _day_counts(records: list[Attendance], total: int) -> dict:
        """Distinct-student Present/Late/Absent for a day's records.

        With multiple sessions a student can have several records per day;
        counting rows would double-count them. A student is Present if they
        were on time to at least one session, Late if marked but never on
        time, Absent if never marked at all.
        """
        by_student: dict[int, bool] = {}  # student -> was present somewhere
        for r in records:
            on_time = r.status == Attendance.STATUS_PRESENT
            by_student[r.student_id] = by_student.get(r.student_id, False) or on_time
        marked = len(by_student)
        present = sum(1 for on_time in by_student.values() if on_time)
        return {
            "present": present,
            "late": marked - present,
            "marked": marked,
            "absent": max(total - marked, 0),
        }

    @classmethod
    def stats_for_date(cls, target: date_cls) -> dict:
        """Present/Late/Absent counts + percentage for the dashboard cards."""
        total = Student.query.count()
        records = Attendance.query.filter_by(date=target).all()
        counts = cls._day_counts(records, total)
        return {
            "date": target.isoformat(),
            "total_students": total,
            **counts,
            "attendance_percentage": (
                round(counts["marked"] / total * 100, 1) if total else 0.0
            ),
        }

    @classmethod
    def analytics(cls, days: int = 14, end: date_cls | None = None) -> list[dict]:
        """Per-day counts + mean confidence for the analytics charts."""
        end = end or date_cls.today()
        total = Student.query.count()
        out = []
        for offset in range(days - 1, -1, -1):
            day = end - timedelta(days=offset)
            records = Attendance.query.filter_by(date=day).all()
            confidences = [r.confidence_score for r in records if r.confidence_score]
            counts = cls._day_counts(records, total)
            out.append({
                "date": day.isoformat(),
                "present": counts["present"],
                "late": counts["late"],
                "absent": counts["absent"],
                "avg_confidence": (
                    round(sum(confidences) / len(confidences), 3) if confidences else None
                ),
            })
        return out
