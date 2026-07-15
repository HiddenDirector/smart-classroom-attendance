"""Real-time face recognizer.

Holds all known encodings in one (N, 128) matrix so a frame's faces are
matched with a single vectorised distance computation. Confidence is
``1 - face_distance``; with dlib's metric, ~0.4 distance (0.6 confidence)
is a solid same-person match, so the default threshold of 0.55 is strict
enough to avoid false positives without rejecting real students.
"""
from __future__ import annotations
import logging
import threading
from dataclasses import dataclass

import numpy as np

from app.face_engine import load_cv2, load_face_recognition
from app.models.student import Student

log = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    """One detected face in a frame (matched or unknown)."""

    box: tuple[int, int, int, int]  # top, right, bottom, left (full-frame px)
    is_match: bool
    student_id: int | None = None
    name: str | None = None
    confidence: float = 0.0


def _center_inside(inner: tuple, outer: tuple) -> bool:
    """True if the centre of box ``inner`` lies within box ``outer``.

    Boxes are (top, right, bottom, left). Used to dedupe the same face found
    by both detection passes — cheaper than IoU and just as reliable here,
    since duplicate detections of one face always share a centre.
    """
    top, right, bottom, left = inner
    cy, cx = (top + bottom) / 2, (left + right) / 2
    o_top, o_right, o_bottom, o_left = outer
    return o_top <= cy <= o_bottom and o_left <= cx <= o_right


class FaceRecognizer:
    """Two-pass detection for mixed distances:

    * **near pass** — every call, at ``detection_scale`` (default 0.25).
      Fast; sees faces roughly > 3m-from-camera-lens sized at 720p.
    * **long-range pass** — at ``long_range_scale`` (default 0.5) with dlib
      upsampling, which finds faces several times smaller/farther. ~16x the
      cost of the near pass, so it runs only when the near pass found nothing
      OR every ``long_range_interval``-th call — that keeps far people
      detectable even while someone is standing close to the camera.

    Results from both passes are merged; duplicates (same face centre) keep
    the near-pass box. Every face in a frame is encoded and matched in one
    vectorised batch, so groups of people cost one matrix op, not N.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.55,
        detection_scale: float = 0.25,
        model: str = "hog",
        long_range: bool = True,
        long_range_scale: float = 0.5,
        long_range_upsample: int = 1,
        long_range_interval: int = 2,
    ):
        self.confidence_threshold = confidence_threshold
        self.detection_scale = detection_scale
        self.model = model
        self.long_range = long_range
        self.long_range_scale = long_range_scale
        self.long_range_upsample = long_range_upsample
        self.long_range_interval = max(long_range_interval, 1)
        self._tick = 0
        self._lock = threading.Lock()
        self._known = np.empty((0, 128))
        self._owners: list[tuple[int, str]] = []  # row i -> (student_id, name)

    # --- Known-face management ---------------------------------------------
    def load_from_db(self) -> int:
        """(Re)load every student's encodings. Must run in an app context."""
        rows: list[np.ndarray] = []
        owners: list[tuple[int, str]] = []
        for student in Student.query.filter(Student.face_encoding.isnot(None)).all():
            encodings = student.get_encodings()
            if encodings is None:
                continue
            for row in np.atleast_2d(encodings):
                rows.append(row)
                owners.append((student.student_id, student.full_name))

        with self._lock:
            self._known = np.vstack(rows) if rows else np.empty((0, 128))
            self._owners = owners
        log.info("Loaded %d encodings for %d rows", len(rows), len(owners))
        return len(rows)

    # --- Recognition ----------------------------------------------------------
    def _detect(
        self, frame_bgr: np.ndarray, scale: float, upsample: int
    ) -> list[tuple[tuple, np.ndarray]]:
        """One detection pass. Returns [(full-frame box, encoding), ...]."""
        fr = load_face_recognition()
        cv2 = load_cv2()
        small = cv2.resize(frame_bgr, (0, 0), fx=scale, fy=scale)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        locations = fr.face_locations(
            rgb, number_of_times_to_upsample=upsample, model=self.model
        )
        if not locations:
            return []
        encodings = fr.face_encodings(rgb, locations)
        return [
            (tuple(int(v / scale) for v in loc), enc)
            for loc, enc in zip(locations, encodings)
        ]

    def recognize(self, frame_bgr: np.ndarray) -> list[RecognitionResult]:
        """Detect + identify every face in a BGR frame (near + far)."""
        fr = load_face_recognition()

        # Near pass: cheap, every call.
        pairs = self._detect(frame_bgr, self.detection_scale, 0)

        # Long-range pass: when the near pass saw nothing, or periodically so
        # far-away people are still found while someone stands close.
        self._tick += 1
        if self.long_range and (
            not pairs or self._tick % self.long_range_interval == 0
        ):
            for box, enc in self._detect(
                frame_bgr, self.long_range_scale, self.long_range_upsample
            ):
                duplicate = any(
                    _center_inside(box, near_box) or _center_inside(near_box, box)
                    for near_box, _ in pairs
                )
                if not duplicate:
                    pairs.append((box, enc))

        if not pairs:
            return []

        with self._lock:
            known = self._known
            owners = self._owners

        results: list[RecognitionResult] = []
        for box, encoding in pairs:
            if known.shape[0] == 0:
                results.append(RecognitionResult(box=box, is_match=False))
                continue

            distances = fr.face_distance(known, encoding)
            best = int(np.argmin(distances))
            confidence = float(1.0 - distances[best])
            if confidence >= self.confidence_threshold:
                student_id, name = owners[best]
                results.append(RecognitionResult(
                    box=box, is_match=True,
                    student_id=student_id, name=name, confidence=confidence,
                ))
            else:
                results.append(RecognitionResult(box=box, is_match=False,
                                                 confidence=confidence))
        return results
