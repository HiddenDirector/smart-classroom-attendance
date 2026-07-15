"""Shared pytest fixtures — in-memory SQLite, no camera, no CV libraries."""
import pytest

from app import create_app
from app.extensions import db as _db
from app.models.student import Student
from app.models.user import User


@pytest.fixture
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(db):
    user = User(username="admin", role="admin")
    user.set_password("secret123")
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def logged_in_client(client, admin):
    client.post("/login", data={"username": "admin", "password": "secret123"})
    return client


@pytest.fixture
def student(db):
    s = Student(full_name="Ada Lovelace", roll_number="CS-001",
                department="Computer Science", year=2)
    db.session.add(s)
    db.session.commit()
    return s
