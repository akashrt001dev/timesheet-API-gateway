"""
Middleware for request/response processing
"""
import logging
from typing import Callable, Optional, Dict, Any
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time

logger = logging.getLogger(__name__)


class TokenRelayMiddleware(BaseHTTPMiddleware):
    """
    Middleware to relay OAuth2 tokens to backend services
    Extracts Bearer token from Authorization header
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and relay token
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        # Token extraction happens in route handlers
        # This middleware just logs token presence
        auth_header = request.headers.get('authorization', '')
        
        if auth_header.startswith('Bearer '):
            logger.debug("Token found in Authorization header")
        
        response = await call_next(request)
        return response


class DedupeResponseHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware to deduplicate response headers
    Removes duplicate CORS headers that may come from multiple sources
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process response and dedupe headers
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response with deduplicated headers
        """
        response = await call_next(request)
        
        # Deduplicate headers
        deduped_headers: Dict[str, str] = {}
        
        dedupe_keys = {
            'access-control-allow-credentials',
            'access-control-allow-origin',
            'access-control-allow-methods',
            'access-control-allow-headers'
        }
        
        for key, value in response.headers.items():
            lower_key = key.lower()
            if lower_key in dedupe_keys:
                if lower_key not in deduped_headers:
                    deduped_headers[lower_key] = value
            else:
                deduped_headers[key] = value
        
        # Create new response with deduplicated headers
        if isinstance(response, JSONResponse):
            return JSONResponse(
                content=response.body.decode(),
                status_code=response.status_code,
                headers=deduped_headers
            )
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for request/response logging
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Log request and response details
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        start_time = time.time()
        
        # Log request
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )
        
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            raise
        
        # Log response
        process_time = time.time() - start_time
        logger.info(
            f"Response: {response.status_code} "
            f"{request.method} {request.url.path} "
            f"in {process_time:.2f}s"
        )
        
        response.headers["X-Process-Time"] = str(process_time)
        return response


class CORSHeaderMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add CORS headers
    """
    
    def __init__(self, app: ASGIApp, allowed_origins: Optional[list] = None):
        """
        Initialize CORS middleware
        
        Args:
            app: ASGI application
            allowed_origins: List of allowed origins
        """
        super().__init__(app)
        self.allowed_origins = allowed_origins or ["*"]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add CORS headers to response
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response with CORS headers
        """
        response = await call_next(request)
        
        origin = request.headers.get("origin", "")
        
        # Check if origin is allowed
        if self.allowed_origins == ["*"] or origin in self.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin or "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        
        return response


class SessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware for session management
    Maintains session context for request processing
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with session context
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
            
        Returns:
            Response
        """
        # Store session data in request state
        if not hasattr(request.state, 'session'):
            request.state.session = {}
        
        # Extract any existing session data from cookies
        session_cookie = request.cookies.get('SESSIONID', '')
        if session_cookie:
            request.state.session['id'] = session_cookie
        
        response = await call_next(request)
        
        # Session is maintained via cookies by FastAPI
        return response
