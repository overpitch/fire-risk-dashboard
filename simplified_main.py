import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import logger
from simplified_endpoints import router as main_router

# Logging is already set up in config.py
logger.info("🔥 Starting Fire Risk Dashboard with simplified caching")

# Create the FastAPI app
app = FastAPI(
    title="Fire Risk Dashboard",
    description="Dashboard for wildfire risk monitoring in Sierra County",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development - restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include the main router
app.include_router(main_router)

# Add startup event to log server start
@app.on_event("startup")
async def startup_event():
    logger.info("📊 Fire Risk Dashboard server started with simplified snapshot-based caching")
    logger.info("🔄 Data will be refreshed every 10 minutes")
    logger.info("⚠️ Stale data will be clearly marked with timestamps")

# Add shutdown event to log server stop
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("🛑 Fire Risk Dashboard server stopped")

# Log environment configuration
logger.info(f"🔧 Environment: {os.getenv('ENVIRONMENT', 'development')}")

if __name__ == "__main__":
    import uvicorn
    
    # Use the default host/port for local development
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    
    logger.info(f"🚀 Starting server at http://{host}:{port}")
    uvicorn.run("simplified_main:app", host=host, port=port, reload=True)
