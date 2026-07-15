"""Staff accounts (admin / teacher) for dashboard access."""
from __future__ import annotations
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    # "admin" manages students + accounts; "teacher" views/exports attendance.
    role = db.Column(db.String(16), nullable=False, default="teacher")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password: str) -> None:
        # PBKDF2 explicitly: werkzeug's scrypt default is unavailable on
        # Python builds linked against LibreSSL (e.g. macOS system Python).
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256:600000")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} ({self.role})>"
