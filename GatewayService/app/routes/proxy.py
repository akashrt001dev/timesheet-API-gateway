"""
Routes for API proxying and request forwarding
"""
import logging
import json
import re
from typing import Optional, Dict, Any, List, Tuple
from fastapi import APIRouter, Request, Response, Header
from app.config.settings import settings
from app.utils import RouterMatcher, ProxyClient, HeaderProcessor, PathRewriter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])

# Get known services from configuration
KNOWN_SERVICES = settings.get_known_services()


def error_response(message: str, status_code: int = 500) -> Response:
    """
    Create error response with properly escaped JSON
    
    Args:
        message: Error message
        status_code: HTTP status code
        
    Returns:
        JSON error response
    """
    try:
        content = json.dumps({"error": message})
    except Exception as e:
        logger.error(f"Failed to encode error message: {e}")
        # Fallback if JSON encoding fails
        content = json.dumps({"error": "Internal Server Error"})
    
    return Response(
        content=content.encode(),
        status_code=status_code,
        media_type="application/json"
    )


def prepare_request_headers(request: Request, headers_to_remove: List[str] = None, request_path: str = "") -> Dict[str, str]:
    """
    Prepare headers for proxying
    - Remove host header (will be set by HTTP client)
    - Add X-Forwarded-* headers for backend services
    - Remove sensitive headers specified in filters
    - Keep authorization header, or add dummy for public endpoints
    
    Args:
        request: Incoming request
        headers_to_remove: List of header names to remove (from RemoveRequestHeader filter)
        request_path: Full request path for context
        
    Returns:
        Cleaned headers dictionary with forwarded headers
    """
    headers = dict(request.headers)
    
    # Always remove host - HTTP client will set it correctly
    headers.pop('host', None)
    
    # Keep Authorization header as-is if present
    # The backend will validate the token
    if 'authorization' in headers:
        logger.debug(f"Authorization header present, will be forwarded to backend")
    
    # =====================================================
    # ADD FORWARDED HEADERS (HTTPS COMPATIBILITY FIX)
    # =====================================================
    # Tell backend the original protocol (http / https)
    # This is crucial: backend receives HTTP but needs to know original was HTTPS
    if "x-forwarded-proto" not in headers:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        headers["x-forwarded-proto"] = proto
        logger.debug(f"Added X-Forwarded-Proto: {proto}")
    
    # Client IP tracking
    if "x-forwarded-for" not in headers:
        if request.client and request.client.host:
            headers["x-forwarded-for"] = request.client.host
            logger.debug(f"Added X-Forwarded-For: {request.client.host}")
    
    # Original host from client request
    if "x-forwarded-host" not in headers:
        host = request.headers.get("host")
        if host:
            headers["x-forwarded-host"] = host
            logger.debug(f"Added X-Forwarded-Host: {host}")
    
    # Add correlation ID if available (from middleware for request tracing)
    if "correlation_id" in request.scope:
        headers["x-correlation-id"] = request.scope["correlation_id"]
        logger.debug(f"Added X-Correlation-ID: {request.scope['correlation_id']}")
    
    # Remove headers specified in RemoveRequestHeader filter
    if headers_to_remove:
        for header in headers_to_remove:
            header_lower = header.strip().lower()
            headers.pop(header_lower, None)
            logger.debug(f"Removed header: {header_lower}")
    
    return headers


def apply_gateway_filters(
    request_path: str,
    filters: List[str],
    request: Request
) -> Tuple[str, List[str]]:
    """
    Apply all gateway filters to the request path in order
    Handles RewritePath and RemoveRequestHeader filters
    
    Args:
        request_path: Original request path (e.g., /auth/users)
        filters: List of filter configurations
        request: Request object (for context logging)
        
    Returns:
        Tuple of (rewritten_path, headers_to_remove)
    """
    rewritten_path = request_path
    headers_to_remove: List[str] = []
    
    for filter_config in filters:
        if not isinstance(filter_config, str):
            continue
        
        # Handle RewritePath filters
        # Format: RewritePath=/old/(?<path>.*), /$\{path}
        if filter_config.startswith('RewritePath='):
            try:
                # Extract pattern and replacement
                # Remove 'RewritePath=' prefix
                config_body = filter_config[12:]
                
                # Split by comma to separate pattern and replacement
                if ',' not in config_body:
                    logger.warning(f"Invalid RewritePath filter format: {filter_config}")
                    continue
                
                parts = config_body.split(',', 1)  # Split on first comma only
                pattern = parts[0].strip()
                replacement = parts[1].strip()
                
                # Convert Spring path pattern to Python regex
                # Spring uses: /auth/(?<path>.*) for named groups
                # Python needs: /auth/(.*) for unnamed groups
                regex_pattern = re.sub(r'\(\?<\w+>', '(', pattern)
                
                # Apply regex replacement
                # Note: $\{path} in config becomes \1 in Python regex
                # Spring: /$\{path} -> Python: /\1
                replacement_python = replacement.replace('$\\{path}', '\\1').replace('${path}', '\\1')
                
                new_path = re.sub(regex_pattern, replacement_python, rewritten_path)
                
                if new_path != rewritten_path:
                    logger.debug(f"RewritePath: {rewritten_path} -> {new_path}")
                    rewritten_path = new_path
                else:
                    logger.debug(f"RewritePath pattern {pattern} did not match {rewritten_path}")
                    
            except Exception as e:
                logger.error(f"Error applying RewritePath filter '{filter_config}': {e}")
        
        # Handle RemoveRequestHeader filters
        # Format: RemoveRequestHeader=Cookie,Set-Cookie
        elif filter_config.startswith('RemoveRequestHeader='):
            try:
                headers_str = filter_config[20:]  # Remove 'RemoveRequestHeader=' prefix
                headers_list = [h.strip() for h in headers_str.split(',')]
                headers_to_remove.extend(headers_list)
                logger.debug(f"Marked headers for removal: {headers_list}")
            except Exception as e:
                logger.error(f"Error parsing RemoveRequestHeader filter '{filter_config}': {e}")
    
    return rewritten_path, headers_to_remove


def get_service_url(service_name: str) -> Optional[str]:
    """
    Get service URL with proper validation
    
    Args:
        service_name: Name of the microservice (e.g., 'user-management-service')
        
    Returns:
        Service URL (e.g., 'http://localhost:8081') or None if invalid
    """
    try:
        service_host = settings.get_service_host(service_name)
        service_port = settings.get_service_port(service_name)
        
        # Validate port
        if not service_port or service_port <= 0 or service_port > 65535:
            logger.error(
                f"Invalid/unconfigured port for service '{service_name}': {service_port}. "
                f"Set SERVICE_{service_name.upper().replace('-', '_')}_PORT environment variable."
            )
            return None
        
        service_url = f"http://{service_host}:{service_port}"
        logger.info(f"Service URL for '{service_name}': {service_url}")
        return service_url
        
    except Exception as e:
        logger.error(f"Error getting service URL for '{service_name}': {e}")
        return None


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_api_request(
    request: Request,
    full_path: str,
    authorization: Optional[str] = Header(None)
) -> Response:
    """
    Proxy API requests to backend services based on routes configuration
    Handles both direct service routing and gateway route matching
    
    Args:
        request: Incoming request
        full_path: Full request path
        authorization: Authorization header
        
    Returns:
        Response from backend service
    """
    request_path = f"/{full_path}"
    
    # Check if this is a direct service request (e.g., /user-management-service or /user-management-service/...)
    path_parts = full_path.split('/')
    first_part = path_parts[0] if path_parts else ""
    
    if first_part in KNOWN_SERVICES:
        # ====================================================================
        # DIRECT SERVICE ROUTING
        # ====================================================================
        service_name = first_part
        remaining_path = "/" + "/".join(path_parts[1:]) if len(path_parts) > 1 else "/"
        
        logger.info(f"Direct service routing: {service_name} → {remaining_path}")
        
        # Get service URL
        service_url = get_service_url(service_name)
        if not service_url:
            return error_response(
                f"Service '{service_name}' is not properly configured. "
                f"Check SERVICE_{service_name.upper().replace('-', '_')}_HOST and _PORT settings.",
                status_code=503
            )
        
        full_target_url = f"{service_url.rstrip('/')}{remaining_path}"
        
        # Prepare headers
        headers = prepare_request_headers(request, request_path=remaining_path)
        
        # Get request body
        body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else None
        
        logger.info(f"Forwarding request: {request.method} {full_target_url}")
        
        # Forward request with error handling
        try:
            status_code, response_headers, response_body = await ProxyClient.forward_request(
                method=request.method,
                url=full_target_url,
                headers=headers,
                body=body
            )
        except Exception as e:
            logger.error(
                f"Error forwarding request to {full_target_url}: {type(e).__name__}: {str(e)}",
                exc_info=True
            )
            return error_response(f"Service unavailable: {str(e)}", status_code=502)
        
        # Deduplicate response headers
        cleaned_headers = HeaderProcessor.dedupe_headers(response_headers)
        
        logger.info(f"Proxied service request - Status: {status_code}")
        
        return Response(
            content=response_body,
            status_code=status_code,
            headers=cleaned_headers
        )
    
    # ====================================================================
    # GATEWAY ROUTE MATCHING
    # ====================================================================
    # Get gateway routes from config
    gateway_routes = settings.get_gateway_routes()
    
    # Find matching route based on predicates
    matching_route = RouterMatcher.find_matching_route(request_path, gateway_routes)
    
    if not matching_route:
        logger.warning(f"No matching route found for: {request_path}")
        return error_response(
            f"No matching route for path: {request_path}",
            status_code=404
        )
    
    route_id = matching_route.get('id', 'unknown')
    logger.info(f"Matched route: {route_id} for path: {request_path}")
    
    # Get target service URI
    target_uri = matching_route.get('uri', '')
    
    # Resolve service URI (handle lb:// prefix for load-balanced services)
    if target_uri.startswith('lb://'):
        # Load-balanced service (Eureka discovery)
        service_name = target_uri[5:]  # Remove 'lb://' prefix
        
        service_url = get_service_url(service_name)
        if not service_url:
            logger.error(f"Cannot resolve service: {service_name}")
            return error_response(
                f"Service '{service_name}' is not available",
                status_code=503
            )
        
        target_url = service_url
    else:
        # Direct URI (e.g., https://app.timesmart.io)
        target_url = target_uri
    
    # Apply gateway filters (RewritePath, RemoveRequestHeader, etc.)
    filters = matching_route.get('filters', [])
    rewritten_path, headers_to_remove = apply_gateway_filters(request_path, filters, request)
    
    logger.debug(f"Path rewriting: {request_path} -> {rewritten_path}")
    
    # Construct full target URL
    full_target_url = f"{target_url.rstrip('/')}{rewritten_path}"
    
    # Prepare headers (apply RemoveRequestHeader filters)
    headers = prepare_request_headers(request, headers_to_remove=headers_to_remove, request_path=request_path)
    
    # Get request body
    body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else None
    
    logger.info(f"Forwarding request: {request.method} {full_target_url}")
    
    # Forward request with error handling
    try:
        status_code, response_headers, response_body = await ProxyClient.forward_request(
            method=request.method,
            url=full_target_url,
            headers=headers,
            body=body
        )
    except Exception as e:
        logger.error(
            f"Error forwarding request to {full_target_url}: {type(e).__name__}: {str(e)}",
            exc_info=True
        )
        return error_response(f"Service unavailable: {str(e)}", status_code=502)
    
    # Deduplicate response headers
    cleaned_headers = HeaderProcessor.dedupe_headers(response_headers)
    
    logger.info(f"Proxied request - Status: {status_code}, Route: {route_id}")
    
    return Response(
        content=response_body,
        status_code=status_code,
        headers=cleaned_headers
    )
