"""Flask extension singletons.

Instantiated here (unbound) and bound to the app in the factory, so any
module can ``from app.extensions import db`` without circular imports.
"""
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
