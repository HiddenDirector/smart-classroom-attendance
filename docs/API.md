# HTTP API Reference

All endpoints require an authenticated session (cookie set by `/login`).
Unauthenticated requests are redirected (302) to `/login`.
Roles: **admin** = full access; **teacher** = everything except student
management and account creation.

## Authentication

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/login` | — | Login page |
| POST | `/login` | form: `username`, `password` | Create session; redirects to `/` |
| GET | `/logout` | — | Destroy session |

Accounts are created from the CLI: `flask --app run.py create-user`.

## Pages

| Path | Description |
|---|---|
| `/` | Dashboard (live feed, stats, events, today's table) |
| `/analytics` | Charts (daily attendance, confidence trend) |
| `/students/` | Student list |
| `/students/register` | Registration page with webcam capture *(admin)* |
| `/students/<id>/edit` | Edit form *(admin)* |
| `/students/<id>/recapture` | Re-capture face photos *(admin)* |
| `/attendance/` | History with `?date=YYYY-MM-DD&q=<search>` filters |

## Camera / pipeline

### `GET /video_feed`
MJPEG stream (`multipart/x-mixed-replace`) of annotated frames.
Returns **503** if the pipeline is not running.

### `GET /api/pipeline/status`
```json
{
  "running": true,
  "camera_running": true,
  "motion_active": false,
  "started_at": "2026-07-15T08:45:12",
  "last_error": null,
  "events": [
    {"time": "08:59:02", "kind": "marked", "message": "Ada Lovelace marked Present (87%)"}
  ]
}
```

### `POST /api/pipeline/start`
Starts camera + recognition. `200 {"ok": true}` or
`500 {"ok": false, "error": "Could not open camera index 0. ..."}`.

### `POST /api/pipeline/stop`
Stops the pipeline and releases the camera. Always `200 {"ok": true}`.

## Dashboard data

### `GET /api/stats/today`
```json
{
  "date": "2026-07-15", "total_students": 42, "present": 30, "late": 4,
  "marked": 34, "absent": 8, "attendance_percentage": 81.0
}
```

### `GET /api/attendance/today`
Array of today's records (newest first):
```json
[{
  "attendance_id": 7, "student_id": 3, "full_name": "Ada Lovelace",
  "roll_number": "CS-001", "department": "Computer Science", "year": 2,
  "date": "2026-07-15", "time": "08:59:02", "status": "Present",
  "confidence_score": 0.874
}]
```

### `GET /api/analytics/<days>`
Per-day series for the last `days` (1–90, default 14) days:
```json
[{"date": "2026-07-14", "present": 30, "late": 4, "absent": 8, "avg_confidence": 0.86}]
```

## Students (admin)

### `POST /students/register`
```json
{
  "full_name": "Ada Lovelace", "roll_number": "CS-001",
  "department": "Computer Science", "year": 2,
  "images": ["data:image/jpeg;base64,...", "..."]
}
```
Responses:
- `200 {"ok": true, "student": {...}, "encodings": 11, "redirect": "/students/"}`
- `400 {"ok": false, "error": "Only 3 of 12 captures contained a detectable face..."}`
- `503` if the face-recognition backend is not installed.

### `POST /students/<id>/recapture`
Same body with `images` only; replaces the stored encodings.

### `POST /students/<id>/edit` — form fields `full_name`, `roll_number`, `department`, `year`.
### `POST /students/<id>/delete` — deletes student + attendance (cascade).

## Class sessions (admin)

| Method | Path | Body | Description |
|---|---|---|---|
| GET | `/sessions/` | — | Session list + add form |
| POST | `/sessions/` | form: `name`, `start_time` (HH:MM), `end_time`, `late_after_minutes` (optional) | Create a period |
| POST | `/sessions/<id>/delete` | — | Delete (blocked for the default session and any session with attendance records) |

Attendance marking resolves the session covering the current time of day;
outside every window the whole-day "General" default applies. Attendance
JSON/exports include the session name.

## Attendance

### `POST /attendance/manual`
Form field `roll_number`. Backup marking path (camera outage / QR scanner
integration); applies identical once-per-day and Present/Late rules, with
`confidence_score = null`.

### `GET /attendance/export.csv` / `GET /attendance/export.xlsx`
Query params `date` (default today) and `q` (search filter) — the same
filters as the history page. Returns a file download.
