"""Model-level behaviour: password hashing, encoding round-trip, cascades."""
import numpy as np

from app.models.attendance import Attendance
from app.models.student import Student
from app.models.user import User


def test_password_is_hashed_and_verifiable(db):
    user = User(username="teacher1", role="teacher")
    user.set_password("s3cret!")
    assert user.password_hash != "s3cret!"
    assert user.check_password("s3cret!")
    assert not user.check_password("wrong")


def test_encoding_roundtrip(db, student):
    encodings = np.random.default_rng(42).random((5, 128))
    student.set_encodings(encodings)
    db.session.commit()

    restored = db.session.get(Student, student.student_id).get_encodings()
    assert restored.shape == (5, 128)
    assert np.allclose(restored, encodings)


def test_single_encoding_is_promoted_to_matrix(student):
    student.set_encodings(np.zeros(128))
    assert student.get_encodings().shape == (1, 128)


def test_deleting_student_cascades_attendance(db, student):
    from datetime import date, time

    from app.models.class_session import ClassSession

    session = ClassSession.get_or_create_default()
    db.session.add(Attendance(student_id=student.student_id,
                              session_id=session.session_id, date=date(2026, 7, 1),
                              time=time(9, 0), status="Present", confidence_score=0.9))
    db.session.commit()
    assert Attendance.query.count() == 1

    db.session.delete(student)
    db.session.commit()
    assert Attendance.query.count() == 0
