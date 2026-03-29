from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from core.settings import settings

# Using the constructed database_url from settings
# (Supports secure password resolution)
engine = create_engine(
    settings.database_url,
    pool_size=settings.db.pool_size,
    pool_timeout=settings.db.pool_timeout,
    client_encoding='utf8'
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Session:
    """Dependency for fetching a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
