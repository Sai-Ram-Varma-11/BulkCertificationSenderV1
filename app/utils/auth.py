from functools import wraps
from typing import Callable
from flask import session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash


def password_hash(password: str) -> str:
	return generate_password_hash(password)


def verify_password(password: str, hashed: str) -> bool:
	return check_password_hash(hashed, password)


def require_roles(*roles: str) -> Callable:
	def decorator(fn: Callable) -> Callable:
		@wraps(fn)
		def wrapper(*args, **kwargs):
			user_id = session.get("user_id")
			if not user_id:
				flash("Please login first", "warning")
				return redirect(url_for("login"))
			role = session.get("role")
			if roles and role not in roles:
				flash("Access denied", "error")
				return redirect(url_for("index"))
			return fn(*args, **kwargs)
		return wrapper
	return decorator
