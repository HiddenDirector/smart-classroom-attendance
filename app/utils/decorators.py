"""Route decorators."""
from __future__ import annotations
from functools import wraps

from flask import abort
from flask_login import current_user


def role_required(*roles: str):
    """Allow only users whose role is in ``roles``. Apply AFTER
    ``login_required`` so anonymous users get redirected to login first."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
