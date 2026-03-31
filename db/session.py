"""
db/session.py
=============
SQLAlchemy session management for agentic_os.
Provides SessionLocal and the declarative Base.
"""
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from agent_core.config import settings

logger = logging.getLogger("agentos.db.session")

# Retrieve database connection parameters from central settings
SQLALCHEMY_DATABASE_URL = settings.database_url

# Initialize engine and SessionLocal
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
