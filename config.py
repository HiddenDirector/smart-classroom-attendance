"""Application configuration.

Every tunable lives here and can be overridden with an environment variable
(see .env.example), so deployments never require code edits. Config objects
are plain classes consumed by ``app.config.from_object``.
"""
from __future__ import annotations
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _parse_camera_source(value: str) -> int | str:
    """Digits -> local device index; anything else -> stream URL."""
    value = value.strip()
    return int(value) if value.isdigit() else value


class Config:
    """Base configuration shared by all environments."""

    # --- Flask / security -------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # --- Database ----------------------------------------------------------
    # SQLite by default; point DATABASE_URL at PostgreSQL to swap engines.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'database' / 'attendance.db'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Camera ------------------------------------------------------------
    # CAMERA_SOURCE accepts either a local device index ("0", "1", ...) or a
    # network stream URL — e.g. a phone running an IP-camera app:
    #   DroidCam:  http://<phone-ip>:4747/video
    #   IP Webcam: http://<phone-ip>:8080/video
    #   RTSP:      rtsp://<phone-ip>:8554/live
    # (CAMERA_INDEX is still honoured for backwards compatibility.)
    CAMERA_SOURCE = _parse_camera_source(
        os.environ.get("CAMERA_SOURCE", os.environ.get("CAMERA_INDEX", "0"))
    )
    FRAME_WIDTH = int(os.environ.get("FRAME_WIDTH", 1280))
    FRAME_HEIGHT = int(os.environ.get("FRAME_HEIGHT", 720))

    # --- Motion detection ----------------------------------------------------
    # Contour area (px, measured on the downscaled analysis frame) below which
    # movement is ignored — filters flickering light / small objects.
    MOTION_MIN_AREA = int(os.environ.get("MOTION_MIN_AREA", 1500))
    # Width the frame is resized to before background subtraction (speed).
    MOTION_ANALYSIS_WIDTH = int(os.environ.get("MOTION_ANALYSIS_WIDTH", 500))
    # Frames fed to the background model before motion is trusted.
    MOTION_WARMUP_FRAMES = int(os.environ.get("MOTION_WARMUP_FRAMES", 30))
    # Seconds recognition stays active after the last detected movement.
    MOTION_ACTIVE_HOLD_SECONDS = float(os.environ.get("MOTION_ACTIVE_HOLD_SECONDS", 5.0))

    # --- Face recognition ----------------------------------------------------
    # Run recognition on every Nth frame while motion is active (CPU relief).
    RECOGNITION_FRAME_INTERVAL = int(os.environ.get("RECOGNITION_FRAME_INTERVAL", 5))
    # Matches below this confidence (1 - face_distance) are rejected.
    RECOGNITION_CONFIDENCE_THRESHOLD = float(
        os.environ.get("RECOGNITION_CONFIDENCE_THRESHOLD", 0.55)
    )
    # Detection frame downscale factor (0.25 = quarter size, ~16x faster).
    RECOGNITION_DETECTION_SCALE = float(os.environ.get("RECOGNITION_DETECTION_SCALE", 0.25))
    # "hog" = CPU friendly, "cnn" = accurate but needs a GPU-built dlib.
    RECOGNITION_MODEL = os.environ.get("RECOGNITION_MODEL", "hog")
    # --- Long-range / multi-person detection ---
    # Second detection pass at higher resolution + dlib upsampling to find
    # small (far-away) faces the fast pass misses. It runs when the fast pass
    # finds nothing, or every Nth recognition tick so distant people are still
    # detected while someone stands near the camera.
    RECOGNITION_LONG_RANGE = _env_bool("RECOGNITION_LONG_RANGE", True)
    RECOGNITION_LONG_RANGE_SCALE = float(os.environ.get("RECOGNITION_LONG_RANGE_SCALE", 0.5))
    RECOGNITION_LONG_RANGE_UPSAMPLE = int(os.environ.get("RECOGNITION_LONG_RANGE_UPSAMPLE", 1))
    RECOGNITION_LONG_RANGE_INTERVAL = int(os.environ.get("RECOGNITION_LONG_RANGE_INTERVAL", 2))
    # Seconds before the pipeline will re-process the same student again.
    RECOGNITION_REMARK_COOLDOWN = float(os.environ.get("RECOGNITION_REMARK_COOLDOWN", 120.0))
    # Minimum usable face encodings a registration capture must yield.
    REGISTRATION_MIN_ENCODINGS = int(os.environ.get("REGISTRATION_MIN_ENCODINGS", 5))
    # Number of images the registration page captures from the webcam.
    REGISTRATION_TARGET_IMAGES = int(os.environ.get("REGISTRATION_TARGET_IMAGES", 12))

    # --- Attendance rules -----------------------------------------------------
    CLASS_START_TIME = os.environ.get("CLASS_START_TIME", "09:00")  # HH:MM (24h)
    LATE_AFTER_MINUTES = int(os.environ.get("LATE_AFTER_MINUTES", 15))

    # --- Pipeline ----------------------------------------------------------
    # Start camera + recognition automatically when the server boots.
    PIPELINE_AUTOSTART = _env_bool("PIPELINE_AUTOSTART", False)

    # --- Email reports (optional) -------------------------------------------
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    REPORT_RECIPIENTS = [
        addr.strip()
        for addr in os.environ.get("REPORT_RECIPIENTS", "").split(",")
        if addr.strip()
    ]


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # in-memory
    SECRET_KEY = "testing"
    PIPELINE_AUTOSTART = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None) -> type[Config]:
    """Resolve a config class from an explicit name or FLASK_ENV."""
    name = name or os.environ.get("FLASK_ENV", "development")
    return _CONFIGS.get(name, DevelopmentConfig)
