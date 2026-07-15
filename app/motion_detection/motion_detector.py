"""Motion detection via MOG2 background subtraction.

MOG2 was chosen over simple frame differencing because it adapts to gradual
lighting change (clouds, projector on/off) instead of flagging it as motion,
and its shadow labelling lets us drop shadows explicitly.

False-positive controls:
* frames are analysed at reduced width (also ~6x faster),
* Gaussian blur suppresses sensor noise,
* shadow pixels (value 127 in the MOG2 mask) are thresholded away,
* total foreground contour area must exceed ``min_area``,
* a warm-up period lets the background model settle before motion is trusted.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np

from app.face_engine import load_cv2


@dataclass
class MotionResult:
    detected: bool
    area: float  # total foreground contour area (analysis-frame px)


class MotionDetector:
    def __init__(
        self,
        min_area: int = 1500,
        analysis_width: int = 500,
        warmup_frames: int = 30,
        history: int = 300,
        var_threshold: int = 25,
    ):
        self.min_area = min_area
        self.analysis_width = analysis_width
        self.warmup_frames = warmup_frames
        self._history = history
        self._var_threshold = var_threshold
        self._subtractor = None  # built lazily so importing needs no cv2
        self._frames_seen = 0

    def _get_subtractor(self):
        if self._subtractor is None:
            cv2 = load_cv2()
            self._subtractor = cv2.createBackgroundSubtractorMOG2(
                history=self._history,
                varThreshold=self._var_threshold,
                detectShadows=True,
            )
        return self._subtractor

    def reset(self) -> None:
        """Discard the learned background (e.g. after the camera restarts)."""
        self._subtractor = None
        self._frames_seen = 0

    def detect(self, frame_bgr: np.ndarray) -> MotionResult:
        cv2 = load_cv2()
        subtractor = self._get_subtractor()

        # Downscale + blur: cheaper and less noise-sensitive.
        h, w = frame_bgr.shape[:2]
        scale = self.analysis_width / float(w)
        small = cv2.resize(frame_bgr, (self.analysis_width, max(int(h * scale), 1)))
        blurred = cv2.GaussianBlur(small, (11, 11), 0)

        mask = subtractor.apply(blurred)
        self._frames_seen += 1

        # Foreground = 255, shadows = 127 -> keep only certain foreground.
        _, mask = cv2.threshold(mask, 200, 255, cv2.THRESH_BINARY)
        mask = cv2.dilate(mask, None, iterations=2)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        area = float(sum(cv2.contourArea(c) for c in contours))

        if self._frames_seen <= self.warmup_frames:
            return MotionResult(detected=False, area=area)
        return MotionResult(detected=area >= self.min_area, area=area)
