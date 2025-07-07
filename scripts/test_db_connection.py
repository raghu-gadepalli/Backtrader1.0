# scripts/test_db_connection.py

from sqlalchemy import text
from config.db import engine, get_session, DatabaseConnectionError

def test_engine():
    try:
        with engine.connect() as conn:
            # Wrap the SQL string in text()
            result = conn.execute(text("SELECT 1")).scalar_one()
            print(f"[Engine] OK — SELECT 1 returned: {result}")
    except Exception as e:
        print(f"[Engine] FAILED — {e}")
        raise

def test_session():
    try:
        with get_session() as session:
            # Use text() here as well
            count = session.execute(
                text("SELECT COUNT(*) FROM candles WHERE frequency = 1")
            ).scalar_one()
            print(f"[Session] OK — 1-min candle rows: {count}")
    except DatabaseConnectionError as e:
        print(f"[Session] DB connection error — {e}")
        raise
    except Exception as e:
        print(f"[Session] FAILED — {e}")
        raise

if __name__ == "__main__":
    print("=== DB Connectivity Tests ===")
    test_engine()
    test_session()
    print("=== All tests passed ===")
