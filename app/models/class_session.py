"""Class sessions (periods): multiple attendance windows per day.

A session is a named time window ("Period 1", 09:00–10:30) with its own late
grace. Attendance uniqueness is per student per day **per session**, so a
student can be marked once in each period.

A seeded whole-day "General" session (NULL start/end) preserves the original
single-session behaviour and doubles as the fallback when a recognition
happens outside every defined window. It exists so ``session_id`` can be
NOT NULL — SQLite treats NULLs as distinct in UNIQUE constraints, which
would silently break duplicate prevention.
"""
from __future__ import annotations
from datetime import datetime, time, timedelta, timezone

from app.extensions import db


class ClassSession(db.Model):
    __tablename__ = "class_sessions"

    DEFAULT_NAME = "General"

    session_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    # NULL start/end = whole-day window (only the default session uses this).
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    # NULL -> fall back to the global LATE_AFTER_MINUTES config.
    late_after_minutes = db.Column(db.Integer, nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    attendance_records = db.relationship("Attendance", backref="session", lazy="dynamic")

    # --- Resolution -----------------------------------------------------------
    @classmethod
    def get_or_create_default(cls) -> ClassSession:
        session = cls.query.filter_by(is_default=True).first()
        if session is None:
            session = cls(name=cls.DEFAULT_NAME, is_default=True)
            db.session.add(session)
            db.session.commit()
        return session

    @classmethod
    def resolve(cls, at: time) -> ClassSession:
        """The session whose window contains ``at``.

        On overlapping windows the most recently started one wins (a 2nd
        period starting inside a long 1st period is the more specific match).
        Outside every window, the whole-day default applies.
        """
        match = (
            cls.query.filter(
                cls.start_time.isnot(None),
                cls.end_time.isnot(None),
                cls.start_time <= at,
                cls.end_time >= at,
            )
            .order_by(cls.start_time.desc())
            .first()
        )
        return match or cls.get_or_create_default()

    # --- Rules ---------------------------------------------------------------
    def late_cutoff(self, config) -> time:
        """Arrivals after this time-of-day are marked Late for this session."""
        start = self.start_time
        if start is None:  # whole-day default: use the global class start
            start = datetime.strptime(config["CLASS_START_TIME"], "%H:%M").time()
        grace = self.late_after_minutes
        if grace is None:
            grace = config["LATE_AFTER_MINUTES"]
        anchor = datetime.combine(datetime(2000, 1, 1), start)
        return (anchor + timedelta(minutes=grace)).time()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "start_time": self.start_time.strftime("%H:%M") if self.start_time else None,
            "end_time": self.end_time.strftime("%H:%M") if self.end_time else None,
            "late_after_minutes": self.late_after_minutes,
            "is_default": self.is_default,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ClassSession {self.name}>"
