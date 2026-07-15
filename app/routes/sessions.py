"""Class-session management (admin): define the periods of the school day."""
from __future__ import annotations
import logging
from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models.class_session import ClassSession
from app.utils.decorators import role_required

sessions_bp = Blueprint("sessions", __name__, url_prefix="/sessions")
log = logging.getLogger(__name__)


def _parse_time(value: str):
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except (ValueError, AttributeError):
        return None


@sessions_bp.route("/")
@login_required
@role_required("admin")
def list_sessions():
    ClassSession.get_or_create_default()  # make the fallback visible in the UI
    sessions = ClassSession.query.order_by(
        ClassSession.is_default.desc(), ClassSession.start_time
    ).all()
    return render_template("sessions/list.html", sessions=sessions)


@sessions_bp.route("/", methods=["POST"])
@login_required
@role_required("admin")
def create_session():
    name = (request.form.get("name") or "").strip()
    start = _parse_time(request.form.get("start_time", ""))
    end = _parse_time(request.form.get("end_time", ""))
    grace_raw = (request.form.get("late_after_minutes") or "").strip()

    if not name:
        flash("Session name is required.", "danger")
    elif ClassSession.query.filter_by(name=name).first():
        flash(f"A session named '{name}' already exists.", "danger")
    elif start is None or end is None:
        flash("Start and end times are required (HH:MM).", "danger")
    elif end <= start:
        flash("End time must be after start time.", "danger")
    elif grace_raw and not grace_raw.isdigit():
        flash("Late grace must be a number of minutes.", "danger")
    else:
        session = ClassSession(
            name=name, start_time=start, end_time=end,
            late_after_minutes=int(grace_raw) if grace_raw else None,
        )
        db.session.add(session)
        db.session.commit()
        log.info("Class session created: %s %s-%s", name, start, end)
        flash(f"Session '{name}' created.", "success")
    return redirect(url_for("sessions.list_sessions"))


@sessions_bp.route("/<int:session_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_session(session_id: int):
    session = db.get_or_404(ClassSession, session_id)
    if session.is_default:
        flash("The default whole-day session cannot be deleted.", "warning")
    elif session.attendance_records.first() is not None:
        # Deleting would orphan history; sessions with records are permanent.
        flash(
            f"'{session.name}' has attendance records and cannot be deleted.",
            "warning",
        )
    else:
        db.session.delete(session)
        db.session.commit()
        flash(f"Session '{session.name}' deleted.", "info")
    return redirect(url_for("sessions.list_sessions"))
