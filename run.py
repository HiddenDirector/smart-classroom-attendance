"""Development entry point.

The recognition pipeline owns the webcam in a background thread, so the app
must run as a SINGLE process:

* the Werkzeug reloader is disabled (it forks a second process that would
  fight over the camera device), and
* in production use ``gunicorn -w 1 --threads 8 run:app`` — one worker,
  many request threads.
"""
import os

from app import create_app
from app.camera.pipeline import pipeline

app = create_app()

if app.config["PIPELINE_AUTOSTART"]:
    pipeline.start()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", 5000)),
        debug=app.config.get("DEBUG", False),
        threaded=True,       # MJPEG stream holds a connection open per viewer
        use_reloader=False,  # see module docstring
    )
