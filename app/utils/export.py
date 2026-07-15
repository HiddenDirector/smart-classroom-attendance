"""Attendance export helpers (CSV built-in, Excel via optional openpyxl)."""
from __future__ import annotations
import csv
import io

from app.models.attendance import Attendance

_HEADERS = ["Date", "Session", "Time", "Roll Number", "Full Name", "Department",
            "Year", "Status", "Confidence"]


def _rows(records: list[Attendance]):
    for r in records:
        yield [
            r.date.isoformat(),
            r.session.name,
            r.time.strftime("%H:%M:%S"),
            r.student.roll_number,
            r.student.full_name,
            r.student.department,
            r.student.year,
            r.status,
            f"{r.confidence_score:.3f}" if r.confidence_score is not None else "manual",
        ]


def attendance_to_csv(records: list[Attendance]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_HEADERS)
    writer.writerows(_rows(records))
    return buf.getvalue()


def attendance_to_xlsx(records: list[Attendance]) -> bytes:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError as exc:
        raise RuntimeError(
            "Excel export requires openpyxl (`pip install openpyxl`). "
            "CSV export works without it."
        ) from exc

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in _rows(records):
        ws.append(row)
    for column_cells in ws.columns:
        width = max(len(str(c.value or "")) for c in column_cells) + 2
        ws.column_dimensions[column_cells[0].column_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
