"""Student records, including stored face encodings.

Encodings are a float64 array of shape (n_samples, 128) — one row per
registration photo. Keeping every sample (instead of averaging) lets the
recognizer match against the closest sample, which is noticeably more robust
to pose/lighting variation. They are serialised with ``numpy.save`` into a
BLOB: self-describing (dtype + shape embedded) and portable to PostgreSQL.
"""
from __future__ import annotations
import io
from datetime import datetime, timezone

import numpy as np

from app.extensions import db


class Student(db.Model):
    __tablename__ = "students"

    student_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    roll_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    department = db.Column(db.String(80), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    face_encoding = db.Column(db.LargeBinary, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    attendance_records = db.relationship(
        "Attendance", backref="student", cascade="all, delete-orphan", lazy="dynamic"
    )

    # --- Encoding (de)serialisation ---------------------------------------
    def set_encodings(self, encodings: np.ndarray) -> None:
        arr = np.asarray(encodings, dtype=np.float64)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        buf = io.BytesIO()
        np.save(buf, arr)
        self.face_encoding = buf.getvalue()

    def get_encodings(self) -> np.ndarray | None:
        if not self.face_encoding:
            return None
        return np.load(io.BytesIO(self.face_encoding))

    @property
    def has_encoding(self) -> bool:
        return self.face_encoding is not None

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "full_name": self.full_name,
            "roll_number": self.roll_number,
            "department": self.department,
            "year": self.year,
            "has_encoding": self.has_encoding,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Student {self.roll_number} {self.full_name}>"
