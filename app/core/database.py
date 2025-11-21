from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
import urllib.parse
from app.core.config import settings

# ==========================================
# 🔧 Helper: Parse Azure Connection String
# ==========================================
def get_sqlalchemy_url(conn_str: str) -> str:
    """
    Converts a raw Azure SQL Connection String into a SQLAlchemy URL.
    Example: 'Driver={...};Server=...' -> 'mssql+pyodbc:///?odbc_connect=...'
    """
    if not conn_str:
        return "sqlite:///:memory:" 
    
    params = urllib.parse.quote_plus(conn_str)
    return f"mssql+pyodbc:///?odbc_connect={params}"

# ==========================================
# 1. Operations DB (Hot Path - Writes)
# ==========================================
url_ops = get_sqlalchemy_url(settings.SQLALCHEMY_DATABASE_URI_OPS)

engine_ops = create_engine(
    url_ops,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    pool_recycle=3600
)

SessionLocalOps = sessionmaker(autocommit=False, autoflush=False, bind=engine_ops)
BaseOps = declarative_base()

# ==========================================
# 2. Analytics DB (Cold Path - Reads)
# ==========================================
url_analytics = get_sqlalchemy_url(settings.SQLALCHEMY_DATABASE_URI_ANALYTICS)

engine_analytics = create_engine(
    url_analytics,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=3600
)

SessionLocalAnalytics = sessionmaker(autocommit=False, autoflush=False, bind=engine_analytics)
BaseAnalytics = declarative_base()

# ==========================================
# 💉 Dependency Injection Generators
# ==========================================

def get_db_ops() -> Generator[Session, None, None]:
    """Dependency for HOT path (Submitting reports)"""
    db = SessionLocalOps()
    try:
        yield db
    finally:
        db.close()

def get_db_analytics() -> Generator[Session, None, None]:
    """Dependency for COLD path (Admin Dashboard)"""
    db = SessionLocalAnalytics()
    try:
        yield db
    finally:
        db.close()