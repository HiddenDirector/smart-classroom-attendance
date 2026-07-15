"""Attendance records.

The UNIQUE (student_id, date) constraint is the hard guarantee against
duplicate marking — application-level checks are a fast path, the constraint
is the source of truth (recognition threads could otherwise race).
"""
from __future__ import annotations
from app.extensions import db


class Attendance(db.Model):
    __tablename__ = "attendance"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "date", "session_id",
            name="uq_attendance_student_date_session",
        ),
    )

    STATUS_PRESENT = "Present"
    STATUS_LATE = "Late"

    attendance_id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(
        db.Integer, db.ForeignKey("students.student_id"), nullable=False, index=True
    )
    session_id = db.Column(
        db.Integer, db.ForeignKey("class_sessions.session_id"),
        nullable=False, index=True,
    )
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(16), nullable=False)
    # 1 - face_distance at the moment of marking; NULL for manual entries.
    confidence_score = db.Column(db.Float, nullable=True)

    def to_dict(self) -> dict:
        return {
            "attendance_id": self.attendance_id,
            "student_id": self.student_id,
            "session": self.session.name,
            "full_name": self.student.full_name,
            "roll_number": self.student.roll_number,
            "department": self.student.department,
            "year": self.student.year,
            "date": self.date.isoformat(),
            "time": self.time.strftime("%H:%M:%S"),
            "status": self.status,
            "confidence_score": (
                round(self.confidence_score, 3) if self.confidence_score is not None else None
            ),
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Attendance student={self.student_id} {self.date} {self.status}>"
