# config/db.py

import os
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Database URL: try environment first, then fallback to your MySQL backtest DB
DB_URL = "mysql+mysqlconnector://backtest_user:Backtest001#@88.222.212.231/backtest"

# Create a single Engine for the backtest database
engine = create_engine(
    DB_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Session factory
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class DatabaseConnectionError(Exception):
    """Raised when we cannot establish a DB session."""

@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Yield a SQLAlchemy Session. Automatically rolls back on error,
    and raises DatabaseConnectionError if there’s an OperationalError.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except OperationalError as e:
        session.rollback()
        logger.error("DB OperationalError: %s", e, exc_info=True)
        raise DatabaseConnectionError("Could not connect to backtest database") from e
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
