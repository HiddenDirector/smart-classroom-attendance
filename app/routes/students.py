"""Student management: list, register (with webcam capture), edit, delete.

Registration flow: the browser captures N webcam frames (static/js/capture.js)
and POSTs them as base64 JSON. The server encodes faces, validates that
enough captures contained a face, and stores the encoding matrix. The
running pipeline is then told to reload its known-faces cache.
"""
from __future__ import annotations
import logging

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required

from app.camera.pipeline import pipeline
from app.extensions import db
from app.face_engine.encoder import EncodingError, build_student_encodings
from app.models.student import Student
from app.utils.decorators import role_required

students_bp = Blueprint("students", __name__, url_prefix="/students")
log = logging.getLogger(__name__)


def _validate_fields(data: dict, student_id: int | None = None) -> tuple[dict | None, str | None]:
    """Validate/normalise student fields. Returns (clean, error)."""
    full_name = (data.get("full_name") or "").strip()
    roll_number = (data.get("roll_number") or "").strip()
    department = (data.get("department") or "").strip()
    try:
        year = int(data.get("year") or 0)
    except (TypeError, ValueError):
        year = 0

    if not full_name or not roll_number or not department:
        return None, "Full name, roll number and department are required."
    if not 1 <= year <= 8:
        return None, "Year must be between 1 and 8."

    duplicate = Student.query.filter_by(roll_number=roll_number).first()
    if duplicate and duplicate.student_id != student_id:
        return None, f"Roll number '{roll_number}' is already registered."

    return {
        "full_name": full_name,
        "roll_number": roll_number,
        "department": department,
        "year": year,
    }, None


@students_bp.route("/")
@login_required
def list_students():
    students = Student.query.order_by(Student.roll_number).all()
    return render_template("students/list.html", students=students)


@students_bp.route("/register")
@login_required
@role_required("admin")
def register_page():
    return render_template(
        "students/register.html",
        target_images=current_app.config["REGISTRATION_TARGET_IMAGES"],
        student=None,
    )


@students_bp.route("/register", methods=["POST"])
@login_required
@role_required("admin")
def register_submit():
    """JSON endpoint: create student from form fields + captured images."""
    data = request.get_json(silent=True) or {}
    clean, error = _validate_fields(data)
    if error:
        return jsonify({"ok": False, "error": error}), 400

    images = data.get("images") or []
    if not images:
        return jsonify({"ok": False, "error": "No captured images received."}), 400

    try:
        encodings = build_student_encodings(
            images, current_app.config["REGISTRATION_MIN_ENCODINGS"]
        )
    except EncodingError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:  # face_recognition/OpenCV not installed
        log.error("Encoding backend unavailable: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 503

    student = Student(**clean)
    student.set_encodings(encodings)
    db.session.add(student)
    db.session.commit()
    pipeline.request_encoding_reload()

    log.info("Registered student %s (%d encodings)", clean["roll_number"], len(encodings))
    return jsonify({
        "ok": True,
        "student": student.to_dict(),
        "encodings": len(encodings),
        "redirect": url_for("students.list_students"),
    })


@students_bp.route("/<int:student_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit(student_id: int):
    student = db.get_or_404(Student, student_id)

    if request.method == "POST":
        clean, error = _validate_fields(request.form, student_id=student_id)
        if error:
            flash(error, "danger")
        else:
            for key, value in clean.items():
                setattr(student, key, value)
            db.session.commit()
            pipeline.request_encoding_reload()  # name may appear in overlays
            flash("Student updated.", "success")
            return redirect(url_for("students.list_students"))

    return render_template("students/edit.html", student=student)


@students_bp.route("/<int:student_id>/recapture")
@login_required
@role_required("admin")
def recapture_page(student_id: int):
    """Reuse the capture UI to replace an existing student's encodings."""
    student = db.get_or_404(Student, student_id)
    return render_template(
        "students/register.html",
        target_images=current_app.config["REGISTRATION_TARGET_IMAGES"],
        student=student,
    )


@students_bp.route("/<int:student_id>/recapture", methods=["POST"])
@login_required
@role_required("admin")
def recapture_submit(student_id: int):
    student = db.get_or_404(Student, student_id)
    data = request.get_json(silent=True) or {}
    images = data.get("images") or []
    if not images:
        return jsonify({"ok": False, "error": "No captured images received."}), 400

    try:
        encodings = build_student_encodings(
            images, current_app.config["REGISTRATION_MIN_ENCODINGS"]
        )
    except EncodingError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503

    student.set_encodings(encodings)
    db.session.commit()
    pipeline.request_encoding_reload()
    return jsonify({"ok": True, "encodings": len(encodings),
                    "redirect": url_for("students.list_students")})


@students_bp.route("/<int:student_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete(student_id: int):
    student = db.get_or_404(Student, student_id)
    name = student.full_name
    db.session.delete(student)  # attendance rows cascade
    db.session.commit()
    pipeline.request_encoding_reload()
    flash(f"Deleted {name} and their attendance history.", "info")
    return redirect(url_for("students.list_students"))
