"""Attendance history, filtering, export, and manual (backup) marking."""
from __future__ import annotations
import logging
from datetime import date, datetime

from flask import Blueprint, Response, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.models.attendance import Attendance
from app.models.student import Student
from app.services.attendance_service import AttendanceService
from app.utils.export import attendance_to_csv, attendance_to_xlsx

attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")
log = logging.getLogger(__name__)


def _parse_date(value: str | None) -> date:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()


def _query(target: date, q: str):
    """Shared filtered query for the history page and both exports."""
    query = (
        Attendance.query.join(Student)
        .filter(Attendance.date == target)
        .order_by(Attendance.time.asc())
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            Student.full_name.ilike(like) | Student.roll_number.ilike(like)
        )
    return query


@attendance_bp.route("/")
@login_required
def history():
    target = _parse_date(request.args.get("date"))
    q = (request.args.get("q") or "").strip()
    records = _query(target, q).all()
    return render_template(
        "attendance/history.html",
        records=records,
        target_date=target,
        q=q,
        stats=AttendanceService.stats_for_date(target),
    )


@attendance_bp.route("/export.csv")
@login_required
def export_csv():
    target = _parse_date(request.args.get("date"))
    q = (request.args.get("q") or "").strip()
    csv_text = attendance_to_csv(_query(target, q).all())
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=attendance_{target}.csv"},
    )


@attendance_bp.route("/export.xlsx")
@login_required
def export_xlsx():
    target = _parse_date(request.args.get("date"))
    q = (request.args.get("q") or "").strip()
    try:
        payload = attendance_to_xlsx(_query(target, q).all())
    except RuntimeError as exc:  # openpyxl missing
        flash(str(exc), "warning")
        return redirect(url_for("attendance.history", date=target.isoformat(), q=q))
    return Response(
        payload,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=attendance_{target}.xlsx"},
    )


@attendance_bp.route("/manual", methods=["POST"])
@login_required
def manual_mark():
    """Backup path when recognition can't run (camera fault, new student).

    Also the integration point for QR-code attendance: a QR scanner posting
    the roll number here gets identical once-per-day/late semantics.
    """
    roll = (request.form.get("roll_number") or "").strip()
    student = Student.query.filter_by(roll_number=roll).first()
    if not student:
        flash(f"No student with roll number '{roll}'.", "danger")
    else:
        record, created = AttendanceService.mark(student.student_id, confidence=None)
        if created:
            flash(f"{student.full_name} manually marked {record.status}.", "success")
            log.info("Manual attendance: %s (%s)", student.full_name, roll)
        else:
            flash(f"{student.full_name} was already marked today.", "info")
    return redirect(request.referrer or url_for("dashboard.index"))
