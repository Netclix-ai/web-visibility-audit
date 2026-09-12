"""Database engine/session setup for the Web Visibility Audit platform.

Uses the auto-provisioned Neon Postgres connector. Connection string comes
from the DB5C90F310_DATABASE_URL secret (injected as an env var).
"""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DB5C90F310_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DB5C90F310_DATABASE_URL is not set")

# psycopg2 doesn't understand the "postgresql+asyncpg" etc scheme variants
# some providers hand out — normalize to the plain psycopg2 driver.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
