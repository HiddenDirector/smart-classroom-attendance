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
from app.models.student import Student

log = logging.getLogger(__name__)


class AttendanceService:
    @staticmethod
    def _late_cutoff() -> time_cls:
        """CLASS_START_TIME + LATE_AFTER_MINUTES as a time-of-day."""
        start_str = current_app.config["CLASS_START_TIME"]
        grace = current_app.config["LATE_AFTER_MINUTES"]
        start = datetime.strptime(start_str, "%H:%M")
        return (start + timedelta(minutes=grace)).time()

    @classmethod
    def determine_status(cls, arrival: time_cls) -> str:
        return (
            Attendance.STATUS_PRESENT
            if arrival <= cls._late_cutoff()
            else Attendance.STATUS_LATE
        )

    @classmethod
    def mark(
        cls,
        student_id: int,
        confidence: float | None = None,
        now: datetime | None = None,
    ) -> tuple[Attendance, bool]:
        """Mark a student present for today's session.

        Returns ``(record, created)`` — ``created`` is False when the student
        was already marked, and the existing record is returned untouched.
        """
        now = now or datetime.now()
        today = now.date()

        existing = Attendance.query.filter_by(student_id=student_id, date=today).first()
        if existing:
            return existing, False

        record = Attendance(
            student_id=student_id,
            date=today,
            time=now.time().replace(microsecond=0),
            status=cls.determine_status(now.time()),
            confidence_score=confidence,
        )
        db.session.add(record)
        try:
            db.session.commit()
        except IntegrityError:
            # Two recognition events raced past the fast-path check; the
            # UNIQUE constraint wins and we return the surviving row.
            db.session.rollback()
            existing = Attendance.query.filter_by(student_id=student_id, date=today).first()
            return existing, False

        log.info(
            "Attendance marked: student=%s status=%s confidence=%s",
            student_id, record.status, confidence,
        )
        return record, True

    @staticmethod
    def stats_for_date(target: date_cls) -> dict:
        """Present/Late/Absent counts + percentage for the dashboard cards."""
        total = Student.query.count()
        records = Attendance.query.filter_by(date=target).all()
        present = sum(1 for r in records if r.status == Attendance.STATUS_PRESENT)
        late = sum(1 for r in records if r.status == Attendance.STATUS_LATE)
        marked = len(records)
        return {
            "date": target.isoformat(),
            "total_students": total,
            "present": present,
            "late": late,
            "marked": marked,
            "absent": max(total - marked, 0),
            "attendance_percentage": round(marked / total * 100, 1) if total else 0.0,
        }

    @staticmethod
    def analytics(days: int = 14, end: date_cls | None = None) -> list[dict]:
        """Per-day counts + mean confidence for the analytics charts."""
        end = end or date_cls.today()
        total = Student.query.count()
        out = []
        for offset in range(days - 1, -1, -1):
            day = end - timedelta(days=offset)
            records = Attendance.query.filter_by(date=day).all()
            confidences = [r.confidence_score for r in records if r.confidence_score]
            present = sum(1 for r in records if r.status == Attendance.STATUS_PRESENT)
            late = sum(1 for r in records if r.status == Attendance.STATUS_LATE)
            out.append({
                "date": day.isoformat(),
                "present": present,
                "late": late,
                "absent": max(total - len(records), 0),
                "avg_confidence": (
                    round(sum(confidences) / len(confidences), 3) if confidences else None
                ),
            })
        return out
