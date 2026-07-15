"""ORM models. Importing the package registers all tables with SQLAlchemy."""
from app.models.user import User
from app.models.student import Student
from app.models.attendance import Attendance
from app.models.class_session import ClassSession

__all__ = ["User", "Student", "Attendance", "ClassSession"]
