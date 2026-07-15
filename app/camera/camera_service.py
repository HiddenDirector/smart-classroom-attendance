"""Threaded webcam capture.

A single background thread owns the cv2.VideoCapture and continuously
overwrites the latest frame; every consumer (pipeline, MJPEG viewers) reads
that shared frame instead of competing for the device. Designed as a module
singleton (``camera``) because a physical camera is inherently a singleton.

Extending to multiple cameras: instantiate one CameraService per device
index and one pipeline per camera — nothing here is index-specific.
"""
from __future__ import annotations
import logging
import threading
import time

import numpy as np

from app.face_engine import load_cv2

log = logging.getLogger(__name__)


class CameraError(RuntimeError):
    pass


class CameraService:
    def __init__(self):
        self._capture = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._consecutive_failures = 0

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, source: int | str = 0, width: int = 1280, height: int = 720) -> None:
        """Open a local device (int index) or a network stream (URL string)."""
        with self._lock:
            if self._running:
                return
            cv2 = load_cv2()
            self._capture = cv2.VideoCapture(source)
            if not self._capture.isOpened():
                self._capture.release()
                self._capture = None
                hint = (
                    "Check that the phone/IP camera app is running and the URL "
                    "is reachable from this machine."
                    if isinstance(source, str)
                    else "Check CAMERA_SOURCE and that no other application is "
                    "using the webcam."
                )
                raise CameraError(f"Could not open camera source {source!r}. {hint}")
            if isinstance(source, int):
                # Resolution hints only make sense for local devices; network
                # streams deliver whatever the phone app is configured to send.
                self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self._running = True
            self._consecutive_failures = 0
            self._thread = threading.Thread(
                target=self._capture_loop, name="camera-capture", daemon=True
            )
            self._thread.start()
        log.info("Camera source %r started", source)

    def stop(self) -> None:
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        if self._capture:
            self._capture.release()
            self._capture = None
        with self._lock:
            self._frame = None
        log.info("Camera stopped")

    def read(self) -> np.ndarray | None:
        """Latest frame (BGR copy) or None if nothing captured yet."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def _capture_loop(self) -> None:
        while self._running:
            ok, frame = self._capture.read() if self._capture else (False, None)
            if ok and frame is not None:
                self._consecutive_failures = 0
                with self._lock:
                    self._frame = frame
            else:
                self._consecutive_failures += 1
                if self._consecutive_failures in (30, 300):  # log sparsely
                    log.warning(
                        "Camera read failing (%d consecutive failures)",
                        self._consecutive_failures,
                    )
                time.sleep(0.1)
            time.sleep(0.005)  # yield; effective ceiling ~60fps


# Module-level singleton shared by the pipeline and the stream route.
camera = CameraService()
