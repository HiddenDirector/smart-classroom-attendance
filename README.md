# Smart Classroom Attendance System

AI-powered attendance that marks students automatically as they walk into the
classroom. A webcam watches the entrance; **motion detection** gates a
**face-recognition** pipeline so the CPU stays idle until someone actually
enters. Confident matches are written to SQLite — once per student per day,
with automatic Present/Late classification.

![stack](https://img.shields.io/badge/Flask-3.x-blue) ![python](https://img.shields.io/badge/Python-3.9+-green) ![license](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **Motion-gated recognition** — MOG2 background subtraction with area
  thresholds and warm-up; face recognition only runs while motion is active.
- **Face recognition** — dlib 128-d encodings via `face_recognition`;
  multi-sample enrolment (12 photos), configurable confidence threshold,
  live name + confidence overlay on the video feed.
- **Attendance rules** — one record per student per day (enforced by a DB
  UNIQUE constraint, not just app logic), automatic Present/Late based on a
  configurable class start time + grace period.
- **Student registration** — browser-webcam capture of 10–20 photos,
  server-side encoding, edit / delete / re-capture.
- **Dashboard** — live MJPEG feed with recognition overlay, today's
  Present/Late/Absent/percentage cards, recognition event feed, searchable
  attendance table, date filter, CSV/Excel export.
- **Auth** — admin + teacher roles, scrypt password hashing (werkzeug),
  session management via Flask-Login. Admin-only student management.
- **Bonus** — dark mode, responsive layout, analytics charts (incl.
  confidence trend + 30-day monthly view), manual/QR-ready backup marking,
  email reports (`flask send-report`), Docker support, unit tests.

## Quick start

```bash
# 1. System dependency for dlib (used by face_recognition)
#    macOS:          brew install cmake
#    Debian/Ubuntu:  sudo apt install build-essential cmake libopenblas-dev liblapack-dev

# 2. Python environment
git clone <this repo> && cd smart-attendance
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt        # dlib compiles — takes a few minutes

# Apple Silicon: if the dlib build fails with "'fp.h' file not found",
# use the prebuilt wheel instead:
#   pip install dlib-bin face_recognition_models "setuptools<81"
#   pip install --no-deps face_recognition

# 3. Configuration
cp .env.example .env                   # set SECRET_KEY at minimum

# 4. Database + first admin account
flask --app run.py init-db
flask --app run.py create-user         # choose role "admin"

# 5. Run (single process — the pipeline owns the webcam)
python run.py                          # http://localhost:5000
```

Log in, open **Students → Register student** to enrol faces, then press
**Start monitoring** on the dashboard.

### Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite runs without a camera and skips OpenCV-dependent tests if OpenCV
isn't installed — so business rules are testable on any machine (CI included).

## Configuration

All settings live in `config.py` and are overridable via environment / `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `CLASS_START_TIME` | `09:00` | Class start (24h `HH:MM`) |
| `LATE_AFTER_MINUTES` | `15` | Grace period; arrivals after start+grace are **Late** |
| `RECOGNITION_CONFIDENCE_THRESHOLD` | `0.55` | Min `1 − face_distance` to accept a match |
| `RECOGNITION_FRAME_INTERVAL` | `5` | Recognize every Nth frame while motion is active |
| `MOTION_MIN_AREA` | `1500` | Min foreground contour area (filters small movements) |
| `MOTION_ACTIVE_HOLD_SECONDS` | `5.0` | Recognition stays active this long after last motion |
| `CAMERA_INDEX` | `0` | OpenCV device index |
| `PIPELINE_AUTOSTART` | `false` | Start monitoring on server boot |
| `DATABASE_URL` | SQLite file | Set a PostgreSQL URL to switch engines |

Full list in [.env.example](.env.example).

## How it works

```
webcam ──► CameraService (capture thread)
                │  latest frame
                ▼
        RecognitionPipeline (worker thread)
                │
        MotionDetector (every frame, cheap)
                │  motion? ──no──► stay idle
                ▼ yes (+5s hold)
        FaceRecognizer (every Nth frame)
                │  confidence ≥ threshold?
                ▼
        AttendanceService.mark()  ──► SQLite (UNIQUE student+date)
                │
                ▼
        annotated JPEG ──► /video_feed (MJPEG) ──► dashboard
```

Details and design decisions: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Per-file walkthrough: [docs/FILE_GUIDE.md](docs/FILE_GUIDE.md).
HTTP API: [docs/API.md](docs/API.md).
Schema: [database/schema.sql](database/schema.sql).

## Database schema

- **students**(student_id, full_name, roll_number *unique*, department, year,
  face_encoding *BLOB: float64 (n,128) numpy array*, created_at, updated_at)
- **attendance**(attendance_id, student_id → students, date, time,
  status *Present|Late*, confidence_score, **UNIQUE(student_id, date)**)
- **users**(id, username *unique*, password_hash, role *admin|teacher*, created_at)

## Docker

```bash
cp .env.example .env   # set SECRET_KEY
docker compose up --build
# then create the admin account:
docker compose exec attendance flask --app run.py create-user
```

Note: webcam pass-through (`/dev/video0`) works on **Linux hosts only** —
Docker Desktop on macOS/Windows cannot access the camera, so run natively
there for development.

## Deployment notes

- Run exactly **one worker process** (`gunicorn -w 1 --threads 8 run:app`):
  the camera and pipeline are process singletons. Scale request handling with
  threads, not workers.
- Put nginx (or similar) in front for TLS; the MJPEG stream is a long-lived
  response, so disable proxy buffering for `/video_feed`.
- Set `FLASK_ENV=production` and a strong `SECRET_KEY`.
- For PostgreSQL: `pip install psycopg2-binary`, set `DATABASE_URL` — the
  models and the encoding BLOBs are portable as-is.

## Extending

- **More cameras**: instantiate one `CameraService` + `RecognitionPipeline`
  per device index (nothing in either class is index-specific).
- **Class sessions instead of days**: add a `class_sessions` table and swap
  the `UNIQUE(student_id, date)` constraint for `(student_id, session_id)` —
  the service layer is the only other place that touches the rule.
- **QR backup attendance**: point a scanner at `POST /attendance/manual`
  with the roll number; it shares the same marking rules.
- **MediaPipe instead of dlib**: implement `face_engine/recognizer.py`'s
  interface (`load_from_db`, `recognize -> list[RecognitionResult]`) with a
  MediaPipe/FaceNet backend; nothing else changes.

## Security notes

- Passwords are hashed with werkzeug's scrypt; no plaintext ever stored.
- All routes (including the video stream and JSON APIs) require login;
  student management additionally requires the admin role.
- Login `next=` redirects are restricted to relative paths.
- Face encodings are biometric data — restrict database file access and
  check local regulations (GDPR etc.) before production use.
- For internet-facing deployments add CSRF protection (Flask-WTF) and rate
  limiting on `/login` (Flask-Limiter); both drop in without refactoring.

## License

MIT — free to use, modify, and distribute for any purpose. See [LICENSE](LICENSE).
