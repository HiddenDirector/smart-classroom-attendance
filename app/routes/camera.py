"""Live MJPEG stream + pipeline start/stop/status API."""
from __future__ import annotations
import logging
import time

from flask import Blueprint, Response, jsonify
from flask_login import login_required

from app.camera.camera_service import CameraError
from app.camera.pipeline import pipeline

camera_bp = Blueprint("camera", __name__)
log = logging.getLogger(__name__)

_BOUNDARY = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"


def _mjpeg_generator():
    """Yield the pipeline's annotated frames as multipart JPEG (~20fps)."""
    while pipeline.is_running:
        jpeg = pipeline.get_annotated_jpeg()
        if jpeg:
            yield _BOUNDARY + jpeg + b"\r\n"
        time.sleep(0.05)


@camera_bp.route("/video_feed")
@login_required
def video_feed():
    if not pipeline.is_running:
        return Response("Pipeline is not running", status=503)
    return Response(
        _mjpeg_generator(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@camera_bp.route("/api/pipeline/status")
@login_required
def pipeline_status():
    return jsonify(pipeline.status())


@camera_bp.route("/api/pipeline/start", methods=["POST"])
@login_required
def pipeline_start():
    try:
        started = pipeline.start()
    except (CameraError, RuntimeError) as exc:
        log.error("Pipeline start failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True, "already_running": not started})


@camera_bp.route("/api/pipeline/stop", methods=["POST"])
@login_required
def pipeline_stop():
    pipeline.stop()
    return jsonify({"ok": True})
