# Architecture

## System overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Browser (per user)                          │
│  Dashboard ── Students ── Attendance ── Analytics        Registration    │
│   │  ▲ poll /api/* every 2–5s                              │ getUserMedia│
│   │  └─ <img src=/video_feed> (MJPEG)                      │ 12 photos   │
└───┼─────────────────────────────────────────────────────────┼────────────┘
    │ HTTP (Flask-Login session)                              │ POST base64
┌───▼──────────────────────────────────────────────────────────▼───────────┐
│                            Flask app (1 process)                          │
│                                                                           │
│  routes/ ──► services/AttendanceService ──► SQLAlchemy ──► SQLite         │
│     │                 ▲                                                    │
│     │ start/stop      │ mark(student, confidence)                          │
│  ┌──▼─────────────────┴───────────────────────────┐                        │
│  │ RecognitionPipeline (daemon thread)             │                        │
│  │   loop: frame ─ MotionDetector ─ FaceRecognizer │                        │
│  │         └── annotate ──► latest JPEG (stream)   │                        │
│  └──▲──────────────────────────────────────────────┘                        │
│  ┌──┴───────────────────────────┐                                          │
│  │ CameraService (daemon thread)│ ◄── cv2.VideoCapture(webcam)             │
│  └──────────────────────────────┘                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

## The processing pipeline

1. **CameraService** — one thread owns the webcam and continuously
   overwrites a shared "latest frame". Consumers never block the device.
2. **MotionDetector** (every frame, ~1ms) — MOG2 background subtraction on a
   downscaled, blurred frame. Shadow pixels discarded, foreground contours
   summed; total area must exceed `MOTION_MIN_AREA`. A warm-up period keeps
   the first seconds from false-triggering while the background model learns.
3. **Motion hold** — once motion fires, recognition stays enabled for
   `MOTION_ACTIVE_HOLD_SECONDS` so a person who pauses mid-doorway is still
   recognized.
4. **FaceRecognizer** (every Nth frame while active) — detects faces on a
   quarter-scale frame (HOG), computes 128-d encodings, and matches against
   ALL stored samples of every student in one vectorised `face_distance`
   call. Confidence = `1 − distance`; matches under the threshold render as
   "Unknown" and are never written to the DB.
5. **AttendanceService.mark()** — checks for an existing record (fast path),
   determines Present/Late from `CLASS_START_TIME + LATE_AFTER_MINUTES`, and
   inserts. The `UNIQUE(student_id, date)` constraint is the real guarantee;
   an `IntegrityError` from a race resolves to the surviving row.
6. **Annotation** — every frame gets boxes/labels/status text and is encoded
   to JPEG once; `/video_feed` fans that single buffer out to all viewers.

## Key design decisions

**Why motion gating?** Face detection is the expensive step (HOG scan of the
frame). An empty entrance produces zero recognition work — the pipeline costs
one background-subtraction pass (~1ms) per frame while idle.

**Why store every enrolment encoding instead of an average?** Averaging
blurs pose/lighting variation into a centroid that matches nothing well.
Matching against all samples and taking the minimum distance is what the
dlib author recommends and measurably reduces false rejections. The cost is
negligible: matching is one vectorised numpy op over an (N·samples, 128)
matrix.

**Why is duplicate prevention a DB constraint?** The pipeline thread and the
manual-marking route can both mark simultaneously. An application-level
check alone is a TOCTOU race; the UNIQUE constraint makes the database the
arbiter and the service resolves `IntegrityError` gracefully.

**Why browser-side capture for registration?** The admin's machine is rarely
the machine wired to the classroom camera. Capturing via `getUserMedia` and
POSTing base64 frames lets enrolment happen from any laptop/phone, while the
server remains the only place encodings are computed and stored.

**Why `face_engine/` and not `face_recognition/`?** A package named after
the pip dependency it imports is an import-shadowing bug waiting to happen.
The folder is `face_engine`; the library is imported lazily through one
helper with a clear error message when dlib isn't installed.

**Why lazy CV imports?** `cv2` and `face_recognition` are imported inside
functions, never at module top level. The web app, CLI, and the whole test
suite run on machines without them — only starting the pipeline or encoding
a registration actually requires them.

**Why one process?** A webcam is a hardware singleton. The camera thread,
pipeline thread, and Flask request threads share one process; deployment
scales request concurrency with gunicorn *threads*, never workers.

**Why MJPEG over WebRTC?** MJPEG is a plain HTTP response — no signalling
servers, TURN, or JS frameworks — and latency (~100ms) is irrelevant for a
monitoring view. The annotated JPEG is encoded once per frame regardless of
viewer count.

## Threading model

| Thread | Owns | Talks to |
|---|---|---|
| camera-capture | `cv2.VideoCapture` | writes latest frame (lock) |
| recognition-pipeline | detector, recognizer, annotated JPEG | reads frame; DB via `app.app_context()` |
| Flask request threads | HTTP | read JPEG/status (lock); DB via request context |

Shared state is confined to `CameraService._frame`, the pipeline's annotated
JPEG/status/events (all lock-guarded), and the database (session-per-context).
Routes never touch the recognizer directly — they set a reload flag
(`threading.Event`) the worker picks up, so encoding reloads are race-free.

## Error handling strategy

- Camera can't open → `CameraError` surfaces as a JSON 500 on
  `/api/pipeline/start` and an alert on the dashboard; nothing crashes.
- Camera read failures mid-run → logged sparsely, loop keeps retrying.
- Missing dlib/OpenCV → helpful `RuntimeError` messages at the exact feature
  that needs them (pipeline start / registration), HTTP 503 for API callers.
- Per-frame exceptions (motion, recognition, annotation) are caught and
  logged individually — one bad frame never kills the pipeline.
- All logs go to console + `logs/attendance.log` (rotating, 5×1MB).
