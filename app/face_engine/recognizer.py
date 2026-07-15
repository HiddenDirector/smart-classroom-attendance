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


class FaceRecognizer:
    def __init__(
        self,
        confidence_threshold: float = 0.55,
        detection_scale: float = 0.25,
        model: str = "hog",
    ):
        self.confidence_threshold = confidence_threshold
        self.detection_scale = detection_scale
        self.model = model
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
    def recognize(self, frame_bgr: np.ndarray) -> list[RecognitionResult]:
        """Detect + identify every face in a BGR frame."""
        fr = load_face_recognition()
        cv2 = load_cv2()
        scale = self.detection_scale

        small = cv2.resize(frame_bgr, (0, 0), fx=scale, fy=scale)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        locations = fr.face_locations(rgb, model=self.model)
        if not locations:
            return []
        encodings = fr.face_encodings(rgb, locations)

        with self._lock:
            known = self._known
            owners = self._owners

        results: list[RecognitionResult] = []
        for (top, right, bottom, left), encoding in zip(locations, encodings):
            box = tuple(int(v / scale) for v in (top, right, bottom, left))
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
