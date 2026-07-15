"""Motion detector tests with synthetic frames (skipped if OpenCV missing)."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from app.motion_detection.motion_detector import MotionDetector


def _static_frame() -> np.ndarray:
    frame = np.full((480, 640, 3), 40, dtype=np.uint8)
    cv2.rectangle(frame, (100, 100), (500, 400), (90, 90, 90), -1)
    return frame


def _warm_up(detector: MotionDetector, frames: int = 40) -> None:
    for _ in range(frames):
        detector.detect(_static_frame())


def test_no_motion_on_static_scene():
    detector = MotionDetector(min_area=800, warmup_frames=30)
    _warm_up(detector)
    assert not detector.detect(_static_frame()).detected


def test_detects_large_moving_object():
    detector = MotionDetector(min_area=800, warmup_frames=30)
    _warm_up(detector)

    frame = _static_frame()
    cv2.rectangle(frame, (200, 120), (360, 420), (230, 230, 230), -1)  # a "person"
    assert detector.detect(frame).detected


def test_ignores_small_movement():
    detector = MotionDetector(min_area=800, warmup_frames=30)
    _warm_up(detector)

    frame = _static_frame()
    cv2.rectangle(frame, (300, 300), (308, 308), (230, 230, 230), -1)  # tiny blob
    assert not detector.detect(frame).detected


def test_warmup_suppresses_motion():
    detector = MotionDetector(min_area=800, warmup_frames=30)
    frame = _static_frame()
    cv2.rectangle(frame, (200, 120), (360, 420), (230, 230, 230), -1)
    # First frame: huge "change" from an empty model, but still warming up.
    assert not detector.detect(frame).detected
