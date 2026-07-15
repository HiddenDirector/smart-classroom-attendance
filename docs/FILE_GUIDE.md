# File-by-file guide

What every file does and why it exists. Paths are relative to the repo root.

## Root

| File | Purpose |
|---|---|
| `run.py` | Entry point. Creates the app, optionally autostarts the pipeline, runs Flask **without the reloader** (the reloader forks a second process that would fight over the webcam). |
| `config.py` | Every tunable in one place, env-overridable. `Config` base + `Development/Production/Testing` variants; `get_config()` resolves from `FLASK_ENV`. |
| `requirements.txt` / `requirements-dev.txt` | Runtime deps / + pytest. |
| `.env.example` | Documented template for local configuration. |
| `Dockerfile` / `docker-compose.yml` | Single-container deployment; compose maps the webcam device and persists `database/` + `logs/`. |
| `database/schema.sql` | Reference DDL (the app auto-creates tables via SQLAlchemy; this documents the schema and enables manual creation). |

## `app/` — application package

| File | Purpose |
|---|---|
| `__init__.py` | **Application factory.** Wires config, logging (console + rotating file), extensions, blueprints, the pipeline's `init_app`, table creation, and CLI commands (`init-db`, `create-user`, `send-report`). |
| `extensions.py` | Unbound `db`/`login_manager` singletons — importable from anywhere without circular imports. |

### `app/models/`

| File | Purpose |
|---|---|
| `user.py` | Staff accounts. `set_password`/`check_password` wrap werkzeug's scrypt hashing; `role` is `admin` or `teacher`. |
| `student.py` | Student record + face-encoding storage. Encodings are a float64 `(n_samples, 128)` numpy array serialised with `np.save` into a BLOB — self-describing and PostgreSQL-portable. All samples are kept (not averaged) for more robust matching. |
| `attendance.py` | Attendance rows. `UNIQUE(student_id, date)` is the hard duplicate-prevention guarantee. `confidence_score` is NULL for manual entries. |

### `app/services/`

| File | Purpose |
|---|---|
| `attendance_service.py` | **All attendance business rules**: once-per-day marking (with `IntegrityError` race resolution), Present/Late from `CLASS_START_TIME + LATE_AFTER_MINUTES`, dashboard stats, analytics series. Framework-light and `now`-injectable, so the pipeline thread, HTTP routes, CLI and tests all share identical behaviour. |

### `app/camera/`

| File | Purpose |
|---|---|
| `camera_service.py` | Threaded webcam owner. One capture thread overwrites a lock-guarded "latest frame"; consumers copy it instead of competing for the device. Handles open failures (`CameraError`) and mid-run read failures with sparse logging + retry. |
| `pipeline.py` | **The core loop**: frame → motion gate → (every Nth frame) recognition → attendance marking → annotated JPEG for the stream. Runs as a daemon thread with an app context for DB work. Also: per-student cooldown, recent-events feed, thread-safe encoding reload requested by student routes, per-stage exception isolation. |

### `app/motion_detection/`

| File | Purpose |
|---|---|
| `motion_detector.py` | MOG2 background subtraction on a downscaled blurred frame. Shadow removal, dilation, contour-area threshold (`MOTION_MIN_AREA`) to ignore small movements, warm-up period before motion is trusted. |

### `app/face_engine/`

*(Named `face_engine`, not `face_recognition`, to avoid shadowing the pip package.)*

| File | Purpose |
|---|---|
| `__init__.py` | Lazy importers for `face_recognition`/`cv2` with actionable error messages when missing. |
| `encoder.py` | Registration-side: base64 → image, largest-face 128-d encoding, batch builder that raises `EncodingError` when too few captures contain a face. |
| `recognizer.py` | Runtime-side: all known encodings in one matrix, quarter-scale HOG detection, single vectorised distance computation per face, confidence = `1 − distance`, threshold-gated `RecognitionResult`s. Thread-safe reload from DB. |

### `app/routes/`

| File | Purpose |
|---|---|
| `auth.py` | Login/logout, failed-attempt logging, open-redirect-safe `next` handling. |
| `dashboard.py` | Dashboard + analytics pages, and the JSON APIs (`/api/stats/today`, `/api/attendance/today`, `/api/analytics/<days>`). |
| `students.py` | List / register (JSON capture endpoint) / edit / re-capture / delete, all admin-gated; each mutation asks the pipeline to reload encodings. Shared field validation in `_validate_fields`. |
| `attendance.py` | History with date+search filters, CSV/Excel export (shared query helper), manual backup marking (`POST /attendance/manual` — also the QR integration point). |
| `camera.py` | MJPEG `/video_feed` generator + pipeline start/stop/status API. |

### `app/utils/`

| File | Purpose |
|---|---|
| `decorators.py` | `role_required(*roles)` → 403 for wrong role. |
| `export.py` | CSV (stdlib) and Excel (optional openpyxl) export from the same row generator. |
| `email_report.py` | Daily SMTP summary with CSV attachment (`flask send-report`; cron-able). |

### `app/templates/`

| File | Purpose |
|---|---|
| `base.html` | Layout: navbar, flash messages, dark-mode pre-paint script, Bootstrap 5.3 + icons. |
| `login.html` | Centered sign-in card. |
| `dashboard.html` | Stat cards, live feed with motion badge, pipeline toggle, event feed, manual-mark form, today's table. |
| `analytics.html` | Chart canvases + range selector (7/14/30 days). |
| `students/list.html` | Table with client-side filter, enrolment status badges, admin actions. |
| `students/register.html` | Two-step registration: details + webcam capture UI (also reused for re-capture). |
| `students/edit.html` | Plain edit form with link to re-capture. |
| `attendance/history.html` | Date/search filter form, stats line, records table, export buttons. |

### `app/static/`

| File | Purpose |
|---|---|
| `css/style.css` | Thin layer over Bootstrap: 16:9 feed boxes, capture thumbnails, event accents. |
| `js/theme.js` | Dark/light toggle persisted in localStorage. |
| `js/dashboard.js` | Polls status (2s) + stats/table (5s), starts/stops the pipeline, manages the MJPEG `<img>`, renders events, HTML-escapes all API strings. |
| `js/capture.js` | `getUserMedia` preview, timed auto-capture of N JPEG frames with thumbnails/progress, JSON submit with server-side error display. Drives both register and re-capture modes via `data-*` attributes. |
| `js/analytics.js` | Chart.js stacked daily bar + confidence line, re-fetches on range change. |

## `tests/`

| File | Purpose |
|---|---|
| `conftest.py` | App factory in testing mode (in-memory SQLite), client, admin, student fixtures. |
| `test_models.py` | Password hashing, encoding BLOB round-trip, delete cascade. |
| `test_attendance_rules.py` | Present/Late cutoff (incl. boundary), duplicate prevention, next-day reset, stats math. |
| `test_routes.py` | Login-required everywhere, auth flow, role gating (teacher ≠ admin), stats API, CSV export, manual marking, registration validation. |
| `test_motion.py` | Synthetic-frame tests: static scene, large object, small movement ignored, warm-up suppression. Auto-skips without OpenCV. |
