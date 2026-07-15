"""Face encoding + recognition.

Named ``face_engine`` (not ``face_recognition``) deliberately: a package
named after the pip dependency invites import-shadowing bugs the moment
anything manipulates sys.path. The pip library is imported lazily via
``_load_face_recognition`` so the web app runs on hosts without dlib.
"""


def load_face_recognition():
    """Import the face_recognition library with a helpful failure message."""
    try:
        import face_recognition
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The 'face_recognition' package is not installed. "
            "Install cmake + a C++ toolchain, then `pip install face_recognition`."
        ) from exc
    return face_recognition


def load_cv2():
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "OpenCV is not installed. Run `pip install opencv-python`."
        ) from exc
    return cv2
