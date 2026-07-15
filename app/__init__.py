"""Application factory.

``create_app`` wires config, logging, database, auth, blueprints, the
recognition pipeline and CLI commands. Heavy CV dependencies (OpenCV,
face_recognition) are imported lazily inside the modules that use them, so
the app — and the test suite — boots on machines without them installed.
"""
from __future__ import annotations
import logging
import sys
from logging.handlers import RotatingFileHandler

import click
from flask import Flask

from config import BASE_DIR, get_config
from app.extensions import db, login_manager


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    _configure_logging(app)

    if not app.testing:
        (BASE_DIR / "database").mkdir(exist_ok=True)

    # --- Extensions --------------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # --- Blueprints ---------------------------------------------------------
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.students import students_bp
    from app.routes.attendance import attendance_bp
    from app.routes.camera import camera_bp

    for bp in (auth_bp, dashboard_bp, students_bp, attendance_bp, camera_bp):
        app.register_blueprint(bp)

    # --- Recognition pipeline ------------------------------------------------
    # init_app only stores the app reference; the camera is NOT opened here.
    from app.camera.pipeline import pipeline

    pipeline.init_app(app)

    # --- Schema -------------------------------------------------------------
    # create_all is idempotent; for multi-developer teams swap in Alembic.
    if not app.testing:
        with app.app_context():
            db.create_all()

    _register_cli(app)
    return app


def _configure_logging(app: Flask) -> None:
    """Console + rotating file logging (file skipped under tests)."""
    level = logging.DEBUG if app.debug else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        root.addHandler(console)

    if not app.testing:
        log_dir = BASE_DIR / "logs"
        log_dir.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "attendance.log", maxBytes=1_000_000, backupCount=5
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


def _register_cli(app: Flask) -> None:
    from app.models.user import User

    @app.cli.command("init-db")
    def init_db() -> None:
        """Create all database tables."""
        db.create_all()
        click.echo("Database initialised.")

    @app.cli.command("create-user")
    @click.option("--username", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    @click.option("--role", type=click.Choice(["admin", "teacher"]), default="admin",
                  prompt=True)
    def create_user(username: str, password: str, role: str) -> None:
        """Create an admin or teacher account."""
        if User.query.filter_by(username=username).first():
            raise click.ClickException(f"User '{username}' already exists.")
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {role} '{username}'.")

    @app.cli.command("send-report")
    def send_report() -> None:
        """Email today's attendance summary (requires SMTP config)."""
        from app.utils.email_report import send_daily_report

        send_daily_report()
        click.echo("Report sent.")
