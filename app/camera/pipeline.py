"""The recognition pipeline: camera -> motion gate -> face match -> attendance.

Runs in its own daemon thread. Motion detection executes on every frame
(cheap); face recognition only while motion is "active" (a hold window after
the last movement) and only every Nth frame — this is what keeps an idle
classroom entrance near-zero CPU.

The pipeline needs an app context to touch the database (it lives outside
the request cycle), so ``init_app`` stores the Flask app and DB work is
wrapped in ``self._app.app_context()``.
"""
from __future__ import annotations
import logging
import threading
import time
from collections import deque
from datetime import datetime

import numpy as np

from app.camera.camera_service import CameraError, camera
from app.face_engine import load_cv2
from app.face_engine.recognizer import FaceRecognizer, RecognitionResult
from app.motion_detection.motion_detector import MotionDetector

log = logging.getLogger(__name__)

# Colours (BGR) for frame annotations.
_GREEN = (80, 200, 60)
_RED = (60, 60, 220)
_YELLOW = (60, 200, 240)
# Keep drawing the last recognition boxes this long so the overlay doesn't
# flicker between recognition frames.
_OVERLAY_TTL = 1.5


class RecognitionPipeline:
    def __init__(self):
        self._app = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._state_lock = threading.Lock()

        self._detector: MotionDetector | None = None
        self._recognizer: FaceRecognizer | None = None
        self._reload_requested = threading.Event()

        self._annotated_jpeg: bytes | None = None
        self._motion_active = False
        self._last_motion_ts: float | None = None
        self._last_results: list[RecognitionResult] = []
        self._last_results_ts = 0.0

        # student_id -> monotonic time of last handling (avoids hammering the
        # DB for someone standing in front of the camera).
        self._cooldowns: dict[int, float] = {}
        # Recent events surfaced on the dashboard.
        self._events: deque[dict] = deque(maxlen=30)
        self._started_at: datetime | None = None
        self._last_error: str | None = None

    def init_app(self, app) -> None:
        self._app = app

    # ------------------------------------------------------------------ control
    def start(self) -> bool:
        """Open the camera and launch the worker thread. Returns False if
        already running. Raises CameraError/RuntimeError on hardware issues."""
        if self._running:
            return False
        cfg = self._app.config
        camera.start(cfg["CAMERA_INDEX"], cfg["FRAME_WIDTH"], cfg["FRAME_HEIGHT"])

        self._detector = MotionDetector(
            min_area=cfg["MOTION_MIN_AREA"],
            analysis_width=cfg["MOTION_ANALYSIS_WIDTH"],
            warmup_frames=cfg["MOTION_WARMUP_FRAMES"],
        )
        self._recognizer = FaceRecognizer(
            confidence_threshold=cfg["RECOGNITION_CONFIDENCE_THRESHOLD"],
            detection_scale=cfg["RECOGNITION_DETECTION_SCALE"],
            model=cfg["RECOGNITION_MODEL"],
        )
        with self._app.app_context():
            self._recognizer.load_from_db()

        self._cooldowns.clear()
        self._last_error = None
        self._running = True
        self._started_at = datetime.now()
        self._thread = threading.Thread(
            target=self._loop, name="recognition-pipeline", daemon=True
        )
        self._thread.start()
        log.info("Recognition pipeline started")
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        camera.stop()
        with self._state_lock:
            self._annotated_jpeg = None
            self._motion_active = False
        log.info("Recognition pipeline stopped")

    def request_encoding_reload(self) -> None:
        """Called by student routes after add/edit/delete; picked up by the
        worker on its next iteration (thread-safe, non-blocking)."""
        self._reload_requested.set()

    # ------------------------------------------------------------------- status
    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict:
        with self._state_lock:
            return {
                "running": self._running,
                "camera_running": camera.is_running,
                "motion_active": self._motion_active,
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "last_error": self._last_error,
                "events": list(self._events),
            }

    def get_annotated_jpeg(self) -> bytes | None:
        with self._state_lock:
            return self._annotated_jpeg

    # -------------------------------------------------------------------- worker
    def _loop(self) -> None:
        cfg = self._app.config
        hold = cfg["MOTION_ACTIVE_HOLD_SECONDS"]
        interval = max(cfg["RECOGNITION_FRAME_INTERVAL"], 1)
        frame_idx = 0

        while self._running:
            frame = camera.read()
            if frame is None:
                time.sleep(0.05)
                continue
            frame_idx += 1

            if self._reload_requested.is_set():
                self._reload_requested.clear()
                try:
                    with self._app.app_context():
                        self._recognizer.load_from_db()
                except Exception:
                    log.exception("Failed to reload encodings")

            # --- Motion gate (every frame) ------------------------------
            try:
                motion = self._detector.detect(frame)
            except Exception:
                log.exception("Motion detection error")
                motion = None
            now = time.monotonic()
            if motion and motion.detected:
                self._last_motion_ts = now
            active = (
                self._last_motion_ts is not None
                and now - self._last_motion_ts <= hold
            )

            # --- Recognition (only while active, every Nth frame) --------
            results: list[RecognitionResult] = []
            if active and frame_idx % interval == 0:
                try:
                    results = self._recognizer.recognize(frame)
                except RuntimeError as exc:  # missing dependency
                    self._last_error = str(exc)
                    log.error("%s — stopping pipeline", exc)
                    self._running = False
                    break
                except Exception:
                    log.exception("Recognition error")
                for result in results:
                    if result.is_match:
                        self._handle_match(result, cfg)
                self._last_results = results
                self._last_results_ts = now

            # --- Annotated preview for the dashboard stream ---------------
            try:
                self._publish_frame(frame, active, now)
            except Exception:
                log.exception("Frame annotation error")

            with self._state_lock:
                self._motion_active = active
            time.sleep(0.01)

    def _handle_match(self, result: RecognitionResult, cfg) -> None:
        """Mark attendance for a confident match, respecting the cooldown."""
        now = time.monotonic()
        last = self._cooldowns.get(result.student_id)
        if last is not None and now - last < cfg["RECOGNITION_REMARK_COOLDOWN"]:
            return
        self._cooldowns[result.student_id] = now

        from app.services.attendance_service import AttendanceService

        try:
            with self._app.app_context():
                record, created = AttendanceService.mark(
                    result.student_id, confidence=result.confidence
                )
                self._push_event(
                    kind="marked" if created else "duplicate",
                    message=(
                        f"{result.name} marked {record.status} "
                        f"({result.confidence:.0%})"
                        if created
                        else f"{result.name} already marked today"
                    ),
                )
        except Exception:
            log.exception("Failed to mark attendance for student %s", result.student_id)

    def _push_event(self, kind: str, message: str) -> None:
        with self._state_lock:
            self._events.appendleft({
                "time": datetime.now().strftime("%H:%M:%S"),
                "kind": kind,
                "message": message,
            })
        log.info("[pipeline] %s", message)

    def _publish_frame(self, frame: np.ndarray, active: bool, now: float) -> None:
        cv2 = load_cv2()
        annotated = frame  # camera.read() already returned a copy

        # Recognition boxes persist briefly so the overlay reads smoothly.
        if now - self._last_results_ts <= _OVERLAY_TTL:
            for r in self._last_results:
                top, right, bottom, left = r.box
                color = _GREEN if r.is_match else _RED
                label = (
                    f"{r.name} {r.confidence:.0%}" if r.is_match
                    else f"Unknown {r.confidence:.0%}"
                )
                cv2.rectangle(annotated, (left, top), (right, bottom), color, 2)
                cv2.rectangle(annotated, (left, bottom), (right, bottom + 24), color, -1)
                cv2.putText(annotated, label, (left + 4, bottom + 17),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        status_text = "MOTION - RECOGNIZING" if active else "IDLE - watching for motion"
        cv2.putText(annotated, status_text, (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    _YELLOW if active else _GREEN, 2)
        cv2.putText(annotated, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    (10, annotated.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        ok, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self._state_lock:
                self._annotated_jpeg = buffer.tobytes()


# Module-level singleton — one pipeline per process (see run.py for the
# single-process deployment note).
pipeline = RecognitionPipeline()
