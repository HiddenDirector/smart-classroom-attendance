"""Route-level tests: auth flow, role gating, APIs, CSV export."""
from datetime import datetime

from app.services.attendance_service import AttendanceService


def test_pages_require_login(client):
    for path in ("/", "/students/", "/attendance/", "/api/stats/today", "/video_feed"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"]


def test_login_logout_flow(client, admin):
    response = client.post("/login", data={"username": "admin", "password": "secret123"},
                           follow_redirects=True)
    assert response.status_code == 200

    assert client.get("/").status_code == 200
    client.get("/logout")
    assert client.get("/").status_code == 302


def test_bad_credentials_rejected(client, admin):
    client.post("/login", data={"username": "admin", "password": "nope"})
    assert client.get("/").status_code == 302


def test_teacher_cannot_register_students(client, db):
    from app.models.user import User

    teacher = User(username="teacher", role="teacher")
    teacher.set_password("pw12345")
    db.session.add(teacher)
    db.session.commit()

    client.post("/login", data={"username": "teacher", "password": "pw12345"})
    assert client.get("/students/register").status_code == 403


def test_stats_api(logged_in_client, student):
    with logged_in_client.application.app_context():
        AttendanceService.mark(student.student_id, confidence=0.91)
    data = logged_in_client.get("/api/stats/today").get_json()
    assert data["marked"] == 1
    assert data["total_students"] == 1


def test_csv_export(logged_in_client, student):
    with logged_in_client.application.app_context():
        AttendanceService.mark(student.student_id, confidence=0.91,
                               now=datetime.now())
    response = logged_in_client.get("/attendance/export.csv")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "CS-001" in body and "Ada Lovelace" in body


def test_manual_mark(logged_in_client, student):
    response = logged_in_client.post("/attendance/manual",
                                     data={"roll_number": "CS-001"},
                                     follow_redirects=True)
    assert response.status_code == 200
    data = logged_in_client.get("/api/attendance/today").get_json()
    assert len(data) == 1
    assert data[0]["confidence_score"] is None  # manual entries have no score


def test_register_rejects_missing_fields(logged_in_client, admin):
    response = logged_in_client.post("/students/register",
                                     json={"full_name": "", "images": []})
    assert response.status_code == 400
