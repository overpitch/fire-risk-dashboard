from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import IS_PRODUCTION, logger
from cache import data_cache
from cache_refresh import refresh_data_cache
from endpoints import router as main_router
from dev_endpoints import router as dev_router
from admin_endpoints import router as admin_router

# Create a lifespan context manager for application startup and shutdown
@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for application startup and shutdown."""
    # Startup event
    logger.info("🚀 Application startup: Initializing data cache...")
    
    # Try to fetch initial data, but don't block startup if it fails
    try:
        await refresh_data_cache()
        logger.info("✅ Initial data cache populated successfully")
    except Exception as e:
        logger.error(f"❌ Failed to populate initial data cache: {str(e)}")
        logger.info("Application will continue startup and retry data fetch on first request")
    
    # Yield control back to FastAPI during application lifetime
    yield
    
    # Shutdown event (if needed in the future)
    logger.info("🛑 Application shutting down...")

# Initialize the FastAPI application
app = FastAPI(lifespan=lifespan)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Add CORS middleware
# Using "*" for origins with allow_credentials=True is not allowed by browsers
# so we specify the origin explicitly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "https://fire-risk-dashboard.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with explicit route prefixes for clarity
app.include_router(main_router, prefix="")  # Main router handles root paths like / and /fire-risk

# Include the admin router (stays at its own paths)
app.include_router(admin_router, prefix="")

# Include the development router only in development mode
if not IS_PRODUCTION:
    app.include_router(dev_router, prefix="/dev")
    logger.info("Development endpoints enabled")
else:
    logger.info("Running in production mode - development endpoints disabled")

# Log all registered routes for debugging
for route in app.routes:
    logger.info(f"Registered route: {route.path}")
