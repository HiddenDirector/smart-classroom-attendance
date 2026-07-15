"""Daily attendance summary over SMTP (bonus feature).

Run manually or from cron:  ``flask send-report``
Requires SMTP_* and REPORT_RECIPIENTS in the environment / .env.
"""
from __future__ import annotations
import logging
import smtplib
from datetime import date
from email.message import EmailMessage

from flask import current_app

from app.models.attendance import Attendance
from app.services.attendance_service import AttendanceService
from app.utils.export import attendance_to_csv

log = logging.getLogger(__name__)


def send_daily_report(target: date | None = None) -> None:
    cfg = current_app.config
    if not cfg["SMTP_HOST"] or not cfg["REPORT_RECIPIENTS"]:
        raise RuntimeError("SMTP_HOST and REPORT_RECIPIENTS must be configured.")

    target = target or date.today()
    stats = AttendanceService.stats_for_date(target)
    records = (
        Attendance.query.filter_by(date=target).order_by(Attendance.time).all()
    )

    msg = EmailMessage()
    msg["Subject"] = f"Attendance report — {target.isoformat()}"
    msg["From"] = cfg["SMTP_USERNAME"]
    msg["To"] = ", ".join(cfg["REPORT_RECIPIENTS"])
    msg.set_content(
        f"Attendance summary for {target.isoformat()}\n\n"
        f"  Present : {stats['present']}\n"
        f"  Late    : {stats['late']}\n"
        f"  Absent  : {stats['absent']}\n"
        f"  Rate    : {stats['attendance_percentage']}%\n\n"
        "Full record attached as CSV."
    )
    msg.add_attachment(
        attendance_to_csv(records).encode(),
        maintype="text", subtype="csv",
        filename=f"attendance_{target.isoformat()}.csv",
    )

    with smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"]) as server:
        server.starttls()
        server.login(cfg["SMTP_USERNAME"], cfg["SMTP_PASSWORD"])
        server.send_message(msg)
    log.info("Daily report for %s sent to %d recipients",
             target, len(cfg["REPORT_RECIPIENTS"]))
