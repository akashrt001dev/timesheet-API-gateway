"""
Routes for API proxying and request forwarding
"""
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Request, Response, Header
from app.config.settings import settings
from app.utils import RouterMatcher, ProxyClient, HeaderProcessor, PathRewriter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])

# Get known services from configuration
KNOWN_SERVICES = settings.get_known_services()


@router.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def proxy_api_request(
    request: Request,
    full_path: str,
    authorization: Optional[str] = Header(None)
) -> Response:
    """
    Proxy API requests to backend services based on routes configuration
    Also supports direct service routing via service name
    
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
        # Direct service routing
        service_name = first_part
        remaining_path = "/" + "/".join(path_parts[1:]) if len(path_parts) > 1 else "/"
        
        # Get service host and port from config
        service_host = settings.get_service_host(service_name)
        service_port = settings.get_service_port(service_name)
        
        logger.info(f"Service routing: {service_name} → {service_host}:{service_port}")
        
        if service_port <= 0:
            logger.error(f"Invalid port {service_port} for service {service_name}")
            return Response(
                content=b'{"error": "Service port not configured"}',
                status_code=503,
                media_type="application/json"
            )
        
        service_url = f"http://{service_host}:{service_port}"
        
        full_target_url = f"{service_url.rstrip('/')}{remaining_path}"
        
        # Prepare headers
        headers = dict(request.headers)
        if authorization:
            headers['authorization'] = authorization
        
        # Get request body
        body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else None
        
        logger.info(f"Routing to target URL: {full_target_url}")
        
        # Forward request
        try:
            status_code, response_headers, response_body = await ProxyClient.forward_request(
                method=request.method,
                url=full_target_url,
                headers=headers,
                body=body
            )
        except Exception as e:
            logger.error(f"Error forwarding request to {full_target_url}: {str(e)}", exc_info=True)
            return Response(
                content=f'{{"error": "Service unavailable: {str(e)}"}}'.encode(),
                status_code=502,
                media_type="application/json"
            )
        
        # Deduplicate response headers
        cleaned_headers = HeaderProcessor.dedupe_headers(response_headers)
        
        logger.info(f"Proxied service request to {full_target_url} - Status: {status_code}")
        
        return Response(
            content=response_body,
            status_code=status_code,
            headers=cleaned_headers
        )
    
    # Otherwise, use gateway route matching
    # Get gateway routes from config
    gateway_routes = settings.get_gateway_routes()
    
    # Find matching route
    matching_route = RouterMatcher.find_matching_route(request_path, gateway_routes)
    
    if not matching_route:
        return Response(
            content=b'{"error": "No matching route"}',
            status_code=404,
            media_type="application/json"
        )
    
    # Get target service URI
    target_uri = matching_route.get('uri', '')
    
    if target_uri.startswith('lb://'):
        # Load-balanced service (Eureka discovery)
        service_name = target_uri[5:]  # Remove 'lb://' prefix
        # Get the service host and port from configuration
        service_host = settings.get_service_host(service_name)
        service_port = settings.get_service_port(service_name)
        target_url = f"http://{service_host}:{service_port}"
    else:
        target_url = target_uri
    
    # Apply path rewriting
    rewritten_path = request_path
    filters = matching_route.get('filters', [])
    for filter_config in filters:
        if isinstance(filter_config, str) and filter_config.startswith('RewritePath='):
            rewritten_path = PathRewriter.rewrite_path_simple(
                rewritten_path,
                filter_config[12:].split(',')[0],
                filter_config[12:].split(',')[1] if ',' in filter_config else '/'
            )
    
    # Construct full target URL
    full_target_url = f"{target_url.rstrip('/')}{rewritten_path}"
    
    # Prepare headers
    headers = dict(request.headers)
    if authorization:
        headers['authorization'] = authorization
    
    # Get request body
    body = await request.body() if request.method in ["POST", "PUT", "PATCH"] else None
    
    # Forward request
    status_code, response_headers, response_body = await ProxyClient.forward_request(
        method=request.method,
        url=full_target_url,
        headers=headers,
        body=body
    )
    
    # Deduplicate response headers
    cleaned_headers = HeaderProcessor.dedupe_headers(response_headers)
    
    logger.info(f"Proxied request to {full_target_url} - Status: {status_code}")
    
    return Response(
        content=response_body,
        status_code=status_code,
        headers=cleaned_headers
    )
