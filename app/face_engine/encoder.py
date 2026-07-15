"""Turn registration photos into stored face encodings."""
from __future__ import annotations
import base64
import logging

import numpy as np

from app.face_engine import load_cv2, load_face_recognition

log = logging.getLogger(__name__)


class EncodingError(ValueError):
    """Raised when a capture set cannot produce enough usable encodings."""


def decode_base64_image(data_url: str) -> np.ndarray | None:
    """Decode a browser dataURL (or bare base64) JPEG/PNG into a BGR array."""
    cv2 = load_cv2()
    try:
        payload = data_url.split(",", 1)[1] if "," in data_url else data_url
        raw = np.frombuffer(base64.b64decode(payload), dtype=np.uint8)
        return cv2.imdecode(raw, cv2.IMREAD_COLOR)
    except Exception:
        log.warning("Failed to decode uploaded image", exc_info=True)
        return None


def encode_face(image_bgr: np.ndarray) -> np.ndarray | None:
    """Return the 128-d encoding of the LARGEST face in the image, or None.

    Largest-face selection means registration still works if someone walks
    through the background of a capture frame.
    """
    fr = load_face_recognition()
    cv2 = load_cv2()
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    locations = fr.face_locations(rgb, model="hog")
    if not locations:
        return None
    largest = max(locations, key=lambda b: (b[2] - b[0]) * (b[1] - b[3]))
    encodings = fr.face_encodings(rgb, [largest])
    return encodings[0] if encodings else None


def build_student_encodings(images_b64: list[str], min_encodings: int) -> np.ndarray:
    """Encode a batch of captured images; raise EncodingError if too few faces.

    Returns an (n, 128) array — every usable sample is kept (see Student
    model docstring for why we don't average).
    """
    encodings: list[np.ndarray] = []
    for i, data_url in enumerate(images_b64):
        image = decode_base64_image(data_url)
        if image is None:
            continue
        enc = encode_face(image)
        if enc is not None:
            encodings.append(enc)
        else:
            log.debug("No face found in capture %d", i)

    if len(encodings) < min_encodings:
        raise EncodingError(
            f"Only {len(encodings)} of {len(images_b64)} captures contained a "
            f"detectable face (need at least {min_encodings}). Improve lighting, "
            "face the camera directly, and try again."
        )
    return np.vstack(encodings)
