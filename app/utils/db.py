from flask_sqlalchemy import SQLAlchemy

# Global SQLAlchemy instance bound in app factory or app module

db = SQLAlchemy()


def init_db(db_instance: SQLAlchemy) -> None:
	"""Create all tables if they do not exist."""
	db_instance.create_all()
