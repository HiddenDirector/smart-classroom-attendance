"""Dashboard pages + the JSON APIs that keep them live."""
from __future__ import annotations
from datetime import date

from flask import Blueprint, jsonify, render_template
from flask_login import login_required

from app.models.attendance import Attendance
from app.services.attendance_service import AttendanceService

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    return render_template("dashboard.html", stats=AttendanceService.stats_for_date(date.today()))


@dashboard_bp.route("/analytics")
@login_required
def analytics():
    return render_template("analytics.html")


# --------------------------------------------------------------------- JSON APIs
@dashboard_bp.route("/api/stats/today")
@login_required
def api_stats_today():
    return jsonify(AttendanceService.stats_for_date(date.today()))


@dashboard_bp.route("/api/attendance/today")
@login_required
def api_attendance_today():
    records = (
        Attendance.query.filter_by(date=date.today())
        .order_by(Attendance.time.desc())
        .all()
    )
    return jsonify([r.to_dict() for r in records])


@dashboard_bp.route("/api/analytics")
@dashboard_bp.route("/api/analytics/<int:days>")
@login_required
def api_analytics(days: int = 14):
    days = max(1, min(days, 90))  # sane bounds
    return jsonify(AttendanceService.analytics(days=days))
