"""
Main FastAPI application setup and initialization
"""
import logging
from fastapi import FastAPI
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config.settings import settings
from app.routes import gateway_router, proxy_router
from app.middleware import (
    ForwardedHeaderMiddleware,
    TokenRelayMiddleware,
    DedupeResponseHeaderMiddleware,
    RequestLoggingMiddleware,
    CORSHeaderMiddleware,
    SessionMiddleware
)
from app.utils.eureka_client import eureka_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("Gateway service starting up...")
    logger.info(f"Server port: {settings.get_server_port()}")
    logger.info(f"Scheme: {settings.get_scheme()}")
    logger.info(f"Master entity: {settings.get_master_entity()}")
    
    # Register with Eureka if enabled
    if settings.get_eureka_enabled():
        logger.info(f"Registering with Eureka at {settings.get_eureka_url()}")
        await eureka_client.register()
        await eureka_client.start_heartbeat_loop()
    
    yield
    
    # Shutdown
    logger.info("Gateway service shutting down...")
    if settings.get_eureka_enabled() and eureka_client.registered:
        await eureka_client.deregister()


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application
    
    Returns:
        Configured FastAPI application
    """
    # Create app with lifespan
    app = FastAPI(
        title="Gateway Service",
        description="BFF Gateway Service - OAuth2/OIDC enabled API Gateway",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/v3/api-docs"
    )
    
    # Add middleware (order matters - earlier middleware wraps later ones)
    # ForwardedHeaderFilter first (highest precedence) - matches Java
    app.add_middleware(ForwardedHeaderMiddleware)
    
    # Session middleware
    app.add_middleware(SessionMiddleware)
    
    # Request logging
    app.add_middleware(RequestLoggingMiddleware)
    
    # Token relay (matches Java TokenRelay filter)
    app.add_middleware(TokenRelayMiddleware)
    
    # Response header deduplication
    app.add_middleware(DedupeResponseHeaderMiddleware)
    
    # CORS - Allow all origins (configurable)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"]
    )
    
    # Custom CORS header middleware
    app.add_middleware(CORSHeaderMiddleware, allowed_origins=["*"])
    
    # Include routers
    app.include_router(gateway_router)
    app.include_router(proxy_router)
    
    logger.info("FastAPI application created successfully")
    
    return app


# Create application instance
app = create_app()


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle global exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return {
        "detail": "Internal server error",
        "status_code": 500
    }


if __name__ == "__main__":
    import uvicorn
    
    port = config.get_server_port()
    host = "0.0.0.0"
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )
