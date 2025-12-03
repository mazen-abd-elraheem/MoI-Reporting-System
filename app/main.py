from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
import logging

from app.core.config import get_settings
from app.core.database import test_database_connections, engine_ops
from app.api.v1 import reports, admin,users, auth

# Import models to register with SQLAlchemy (but don't use them directly)
from app.models import user, report, attachment

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events"""
    logger.info(f"Starting {settings.APP_NAME} in {settings.ENVIRONMENT} environment")
    
    try:
        test_database_connections()
        logger.info("✓ All database connections verified")
    except Exception as e:
        logger.critical(f"✗ Database connection failed: {e}", exc_info=True)
        raise SystemExit("Database connection failed")
    
    yield
    
    logger.info("Shutting down application...")
    engine_ops.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.API_VERSION,
    description="MoI Digital Reporting System - Two Database Architecture",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins = settings.ALLOWED_ORIGINS,
    allow_credentials = True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return RedirectResponse(url="/api/docs")

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.API_VERSION,
        "databases": {
            "operations": "connected",
            "analytics": "connected" if settings.SQLALCHEMY_DATABASE_URI_ANALYTICS else "not configured"
        }
    }


# Register routers
app.include_router(
    reports.router,
    prefix="/api/v1/reports",
    tags=["Reports"]
)

app.include_router(
    admin.router,
    prefix="/api/v1/admin",
    tags=["Admin Dashboard"]
)
app.include_router(
    users.router,
    prefix=f"/api/v1/users",
    tags=["Users"]
)


app.include_router(
    auth.router,
    prefix=f"/api/v1/auth",
    tags=["Auth"]
)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "message": str(exc) if settings.DEBUG else "An unexpected error occurred"
        }
    )
