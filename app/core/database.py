# app/core/database.py

from sqlalchemy import create_engine, text  
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
import urllib.parse
import logging

from app.core.config import get_settings  

settings = get_settings()
logger = logging.getLogger(__name__)

# ==========================================
# Helper: Parse Azure Connection String
# ==========================================
def get_sqlalchemy_url(conn_str: str) -> str:
    """Converts Azure SQL Connection String to SQLAlchemy URL"""
    if not conn_str:
        raise ValueError("Database connection string is required")
    
    # Add ODBC driver if not present
    if "Driver=" not in conn_str:
        conn_str = f"Driver={{ODBC Driver 18 for SQL Server}};{conn_str}"
    
    params = urllib.parse.quote_plus(conn_str)
    return f"mssql+pyodbc:///?odbc_connect={params}"

# ==========================================
# 1. Operations DB (Hot Path - Writes)
# ==========================================
try:
    url_ops = get_sqlalchemy_url(settings.SQLALCHEMY_DATABASE_URI_OPS)
    
    engine_ops = create_engine(
        url_ops,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        echo=settings.DEBUG
    )
    
    SessionLocalOps = sessionmaker(
        autocommit=False, 
        autoflush=False, 
        bind=engine_ops
    )
    
    logger.info("✓ Operations database engine created")
except Exception as e:
    logger.error(f"✗ Failed to create Operations DB engine: {e}")
    raise

# Base class for Transactional Models
BaseOps = declarative_base()

# ==========================================
# 2. Analytics DB (Cold Path - Reads)
# ==========================================
engine_analytics = None
SessionLocalAnalytics = None

if settings.SQLALCHEMY_DATABASE_URI_ANALYTICS:
    try:
        url_analytics = get_sqlalchemy_url(settings.SQLALCHEMY_DATABASE_URI_ANALYTICS)
        
        engine_analytics = create_engine(
            url_analytics,
            pool_pre_ping=True,
            pool_size=3,
            max_overflow=5,
            pool_recycle=3600,
            echo=False
        )
        
        SessionLocalAnalytics = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine_analytics
        )
        
        logger.info("✓ Analytics database engine created")
    except Exception as e:
        logger.warning(f"⚠ Analytics DB unavailable: {e}")
        engine_analytics = None
        SessionLocalAnalytics = None
else:
    logger.warning("⚠ Analytics database not configured")

# Base class for Analytical Models
BaseAnalytics = declarative_base()

# ==========================================
# Dependency Injection Generators
# ==========================================

def get_db_ops() -> Generator[Session, None, None]:
    """Dependency for HOT path (Operations DB)"""
    db = SessionLocalOps()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def get_db_analytics() -> Generator[Session, None, None]:
    """Dependency for COLD path (Analytics DB)"""
    if not SessionLocalAnalytics:
        raise RuntimeError(
            "Analytics database not configured. "
            "Add SQLALCHEMY_DATABASE_URI_ANALYTICS to environment or Key Vault."
        )
    
    db = SessionLocalAnalytics()
    try:
        yield db
    except Exception as e:
        logger.error(f"Analytics query error: {e}")
        raise
    finally:
        db.close()

# ==========================================
# Test Database Connections on Startup
# ==========================================
def test_database_connections():
    """Test both database connections using text()-wrapped SQL"""
    try:
        db_ops = SessionLocalOps()
        db_ops.execute(text("SELECT 1"))  
        db_ops.close()
        logger.info("✓ Operations DB connection successful")
    except Exception as e:
        logger.error(f"✗ Operations DB connection failed: {e}")
        raise
    
    if SessionLocalAnalytics:
        try:
            db_analytics = SessionLocalAnalytics()
            db_analytics.execute(text("SELECT 1"))  
            db_analytics.close()
            logger.info("✓ Analytics DB connection successful")
        except Exception as e:
            logger.warning(f"⚠ Analytics DB connection failed: {e}")