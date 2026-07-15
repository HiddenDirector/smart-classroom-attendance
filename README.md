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
- **Attendance rules** — one record per student per class session (enforced
  by a DB UNIQUE constraint, not just app logic), automatic Present/Late
  based on each session's start time + grace period.
- **Class sessions** — define periods ("Period 1", 09:00–10:30) with
  per-session late cutoffs; students are marked once in each period they
  attend. A whole-day default session covers times outside every window.
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
| `RECOGNITION_LONG_RANGE` | `true` | Extra high-res detection pass for far-away/small faces |
| `RECOGNITION_LONG_RANGE_SCALE` | `0.5` | Long-range pass resolution (raise to `1.0` for max range) |
| `RECOGNITION_LONG_RANGE_INTERVAL` | `2` | Run long-range pass every Nth tick even when near faces are present |
| `MOTION_MIN_AREA` | `1500` | Min foreground contour area (filters small movements) |
| `MOTION_ACTIVE_HOLD_SECONDS` | `5.0` | Recognition stays active this long after last motion |
| `CAMERA_SOURCE` | `0` | Device index (`0`, `1`, …) **or** phone/IP-camera stream URL (e.g. DroidCam `http://<phone-ip>:4747/video`) |
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
- **Weekly timetables**: sessions currently apply every day; adding a
  weekday mask to `ClassSession` and filtering in `resolve()` is the next
  step for schools whose periods differ by day.
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

## Known limitations

- **No liveness detection** — a printed photo held to the camera can be
  recognized. Don't use this where spoofing matters without adding an
  anti-spoofing layer.
- **Recognition accuracy degrades** with backlighting, heavy occlusion
  (masks), and very similar faces (identical twins will cross-match).
- **No schema migrations** — the session feature changed the attendance
  table; existing databases from older versions must be recreated (or
  migrated by hand) until Alembic lands.
- **Single process, one camera per process** — by design (see deployment
  notes); horizontal scaling requires one instance per camera.
- **SQLite write concurrency** is modest; fine for a classroom, switch to
  PostgreSQL for campus-scale deployments.

## Roadmap

Realistic next steps, in rough priority order:

- [x] Class-session model (multiple periods per day) replacing date-unique marking
- [ ] Liveness/anti-spoofing check (blink detection or depth heuristics)
- [ ] Alembic migrations instead of `create_all`
- [ ] CSRF protection + login rate limiting for internet-facing deployments
- [ ] Multi-camera orchestration (one pipeline per source in a single dashboard)
- [ ] QR-code fallback UI on top of the existing `/attendance/manual` endpoint

Contributions welcome — the [architecture doc](docs/ARCHITECTURE.md) and
[file guide](docs/FILE_GUIDE.md) are the fastest way in.

## License

MIT — free to use, modify, and distribute for any purpose. See [LICENSE](LICENSE).
