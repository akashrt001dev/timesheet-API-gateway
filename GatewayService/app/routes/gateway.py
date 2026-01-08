"""
Gateway controller routes - main gateway endpoints
"""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Request, Response, Header, Depends
from fastapi.responses import RedirectResponse, JSONResponse
import json
from datetime import datetime

from app.config.settings import settings
from app.models import UserDto, LoginOptionDto
from app.utils import TokenProcessor, MultiTenantResolver, OAuthClientHelper

logger = logging.getLogger(__name__)
router = APIRouter(tags=["gateway"])


def extract_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract Bearer token from Authorization header"""
    if authorization and authorization.startswith('Bearer '):
        return authorization[7:]  # Remove 'Bearer ' prefix
    return None


@router.get("/home", tags=["frontend"])
@router.get("/home/", tags=["frontend"])
async def home_redirect(
    request: Request,
    code: Optional[str] = None,
    provider: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    session_state: Optional[str] = None
) -> Response:
    """
    OAuth2 callback handler - serves frontend with OAuth2 parameters
    Proxies frontend from REACT_APP_URI and injects OAuth2 parameters
    
    Args:
        request: Request object
        code: OAuth2 authorization code
        provider: OAuth2 provider/realm name
        state: State parameter for CSRF protection
        error: Error code (if authentication failed)
        error_description: Error description
        session_state: Keycloak session state
        
    Returns:
        Frontend HTML response with OAuth2 parameters available
    """
    import httpx
    
    # Get frontend URL
    frontend_url = settings.get_react_uri()
    
    # Fetch frontend content from REACT_APP_URI
    frontend_home_url = f"{frontend_url}/home/"
    
    try:
        # Fetch the frontend HTML
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.get(frontend_home_url)
        
        html_content = response.text
        
        # Build OAuth2 parameters JSON
        oauth_params = {}
        if code:
            oauth_params['code'] = code
        if provider:
            oauth_params['provider'] = provider
        if state:
            oauth_params['state'] = state
        if session_state:
            oauth_params['session_state'] = session_state
        if error:
            oauth_params['error'] = error
            oauth_params['error_description'] = error_description or ""
        
        oauth_json = json.dumps(oauth_params)
        
        # Inject OAuth2 parameters into the HTML
        inject_script = f"""
        <script>
            // OAuth2 parameters from gateway
            window.oauth2Params = {oauth_json};
            console.log('OAuth2 parameters available:', window.oauth2Params);
        </script>
        """
        
        # Insert script before closing </head> tag if it exists, otherwise before </body>
        if '</head>' in html_content:
            html_content = html_content.replace('</head>', f'{inject_script}</head>')
        elif '</body>' in html_content:
            html_content = html_content.replace('</body>', f'{inject_script}</body>')
        else:
            html_content += inject_script
        
        logger.info(f"OAuth2 home page - provider: {provider}, serving frontend from {frontend_url}")
        
        return Response(
            content=html_content,
            status_code=200,
            media_type="text/html; charset=utf-8"
        )
    
    except Exception as e:
        logger.error(f"Error fetching frontend from {frontend_home_url}: {str(e)}")
        return Response(
            content=f"Error loading frontend: {str(e)}",
            status_code=502,
            media_type="text/plain"
        )


@router.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"], tags=["frontend-proxy"])
async def proxy_frontend_static(
    path_name: str,
    request: Request
) -> Response:
    """
    Proxy static files and API requests to frontend
    Handles JS, CSS, JSON, images, and other assets
    
    Args:
        path_name: Request path
        request: Request object
        
    Returns:
        Proxied response from frontend
    """
    import httpx
    
    # List of paths that should be proxied to frontend
    # These are typically static assets and frontend routes
    static_extensions = ['.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.woff', '.woff2', '.ttf', '.eot', '.ico']
    frontend_paths = ['/static/', '/public/', '/assets/', '/dist/']
    
    # Check if this is a static file or frontend path
    is_static = any(path_name.endswith(ext) for ext in static_extensions)
    is_frontend_path = any(path_name.startswith(fp) for fp in frontend_paths)
    
    # If it's not a static file or frontend path, don't proxy (let other routes handle it)
    if not is_static and not is_frontend_path:
        # Don't intercept - this will be handled by other routes or proxy
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
    
    try:
        # Get frontend URL
        frontend_url = settings.get_react_uri()
        
        # Construct full target URL
        target_url = f"{frontend_url}/{path_name}"
        
        # Get request body if needed
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
        
        # Forward the request to frontend
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=dict(request.headers),
                content=body,
                timeout=30.0
            )
        
        logger.debug(f"Proxied {request.method} {target_url} - Status: {response.status_code}")
        
        # Return the response from frontend
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get('content-type', 'application/octet-stream')
        )
    
    except Exception as e:
        logger.error(f"Error proxying frontend request to {target_url}: {str(e)}")
        return Response(
            content=f"Error proxying request: {str(e)}",
            status_code=502,
            media_type="text/plain"
        )


@router.get("/", tags=["root"])
async def redirect_index_to_ui(request: Request) -> RedirectResponse:
    """
    Redirect root to OAuth2 authorization
    Extracts subdomain and redirects to appropriate Keycloak realm
    
    Returns:
        Redirect response to OAuth2 authorization endpoint
    """
    # Get hostname from request
    host = request.headers.get("host", "localhost")
    hostname = host.split(':')[0]  # Remove port
    
    # Extract subdomain
    master_entity = settings.get_master_entity()
    subdomain = MultiTenantResolver.extract_subdomain(hostname, master_entity)
    
    # Get scheme
    scheme = settings.get_scheme()
    
    # Construct redirect URL
    redirect_url = f"{scheme}://{host}/oauth2/authorization/{subdomain}"
    
    logger.info(f"Redirecting root request to: {redirect_url}")
    
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/oauth2/authorization/{realm}", tags=["authentication"])
async def oauth2_authorization(
    realm: str,
    request: Request
) -> RedirectResponse:
    """
    OAuth2 Authorization endpoint
    Redirects to Keycloak authorization server
    
    Args:
        realm: Keycloak realm name
        request: Request object
        
    Returns:
        Redirect response to Keycloak authorization endpoint
    """
    host = request.headers.get("host", "localhost")
    scheme = settings.get_scheme()
    
    # Get OAuth2 registrations
    registrations = settings.get_oauth2_registrations()
    registration = registrations.get(realm, {})
    
    if not registration or not registration.get('issuer'):
        logger.error(f"No OAuth2 registration found for realm: {realm}")
        return JSONResponse(
            status_code=404,
            content={"error": f"No OAuth2 configuration for realm: {realm}"}
        )
    
    # Get configuration from registration
    issuer_uri = registration.get('issuer', '').rstrip('/')
    client_id = registration.get('client_id')
    redirect_uri = registration.get('redirect_uri')
    scope = registration.get('scope', 'openid profile email')
    
    # Convert comma-separated scopes to space-separated for OAuth2
    scope = scope.replace(',', ' ').strip()
    
    if not client_id or not redirect_uri or not issuer_uri:
        logger.error(f"Incomplete OAuth2 configuration for realm: {realm}")
        return JSONResponse(
            status_code=500,
            content={"error": f"OAuth2 configuration incomplete for realm: {realm}"}
        )
    
    # Get authorization endpoint from issuer
    auth_endpoint = f"{issuer_uri}/protocol/openid-connect/auth"
    
    # Get authorization request parameters
    query_params = request.query_params
    
    # Build authorization URL
    authorization_url = (
        f"{auth_endpoint}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
    )
    
    if query_params.get('state'):
        authorization_url += f"&state={query_params.get('state')}"
    
    if query_params.get('nonce'):
        authorization_url += f"&nonce={query_params.get('nonce')}"
    
    logger.info(f"Redirecting to OAuth2 authorization for realm: {realm}")
    logger.debug(f"Authorization endpoint: {auth_endpoint}")
    logger.debug(f"Client ID: {client_id}")
    
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/login/oauth2/code/{provider}", tags=["authentication"])
async def oauth2_callback(
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    request: Request = None
) -> RedirectResponse:
    """
    OAuth2 Authorization Code Callback
    Handles the callback from Keycloak after user authorization
    
    Args:
        provider: OAuth2 provider/realm name
        code: Authorization code
        state: State parameter
        error: Error code (if authorization failed)
        error_description: Error description
        request: Request object
        
    Returns:
        Redirect response
    """
    host = request.headers.get("host", "localhost")
    scheme = settings.get_scheme()
    
    # Handle authorization errors
    if error:
        logger.error(f"OAuth2 authorization error from {provider}: {error} - {error_description}")
        error_redirect = f"{scheme}://{host}/login?error={error}&error_description={error_description}"
        return RedirectResponse(url=error_redirect, status_code=302)
    
    # Check if authorization code is present
    if not code:
        logger.error(f"Missing authorization code in callback from {provider}")
        error_redirect = f"{scheme}://{host}/login?error=missing_code"
        return RedirectResponse(url=error_redirect, status_code=302)
    
    logger.info(f"Received OAuth2 callback from {provider} with authorization code")
    logger.debug(f"State: {state}, Code: {code[:20]}...")
    
    # Get registration to validate provider
    registrations = settings.get_oauth2_registrations()
    registration = registrations.get(provider, {})
    
    if not registration or not registration.get('issuer'):
        logger.error(f"Unknown OAuth2 provider/realm: {provider}")
        error_redirect = f"{scheme}://{host}/login?error=invalid_provider"
        return RedirectResponse(url=error_redirect, status_code=302)
    
    # Get post-login redirect path
    post_login_path = settings.get_post_login_redirect_path()
    redirect_url = f"{scheme}://{host}{post_login_path}"
    
    # In a real implementation, you would:
    # 1. Exchange authorization code for tokens using client credentials
    # 2. Store tokens in session/cookies
    # 3. Create authenticated session
    # 4. Redirect to post-login URL
    
    logger.info(f"OAuth2 callback processed successfully for {provider}")
    logger.debug(f"Redirecting to: {redirect_url}")
    
    # For now, redirect to home with code in query parameter
    # The frontend or another service would handle token exchange
    callback_redirect = f"{redirect_url}?code={code}&state={state}&provider={provider}" if state else f"{redirect_url}?code={code}&provider={provider}"
    
    return RedirectResponse(url=callback_redirect, status_code=302)


@router.get("/login-options", response_model=List[LoginOptionDto], tags=["authentication"])
async def get_login_options(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> List[LoginOptionDto]:
    """
    Get available login options (OAuth2 providers)
    Returns empty list if already authenticated
    
    Args:
        request: Request object
        authorization: Authorization header (Bearer token)
        
    Returns:
        List of login options
    """
    # Check if already authenticated
    is_authenticated = authorization and authorization.startswith('Bearer ')
    
    if is_authenticated:
        # Already logged in, return empty list
        logger.debug("User already authenticated")
        return []
    
    # Get hostname
    host = request.headers.get("host", "localhost")
    hostname = host.split(':')[0]
    
    # Extract subdomain
    master_entity = settings.get_master_entity()
    subdomain = MultiTenantResolver.extract_subdomain(hostname, master_entity)
    
    # Get scheme
    scheme = settings.get_scheme()
    
    # Construct login URI for this subdomain
    login_uri = f"{scheme}://{host}/oauth2/authorization/{subdomain}"
    
    login_option = LoginOptionDto(
        label="keycloak",
        loginUri=login_uri
    )
    
    logger.debug(f"Returning login option for subdomain: {subdomain}")
    
    return [login_option]


@router.get("/me", response_model=UserDto, tags=["user"])
async def get_me(
    token: Optional[str] = Depends(extract_token)
) -> UserDto:
    """
    Get current user information from OAuth2 token
    
    Args:
        token: Bearer token from Authorization header
        
    Returns:
        UserDto with user information or anonymous user
    """
    if not token:
        logger.debug("No token provided - returning anonymous user")
        return UserDto.anonymous()
    
    # Extract user information from token
    user = TokenProcessor.extract_user_info(token)
    
    logger.info(f"Retrieved user info: subject={user.subject}, roles={user.roles}")
    
    return user


@router.get("/logout_api", tags=["authentication"])
async def logout_api(
    request: Request,
    token: Optional[str] = Depends(extract_token)
) -> Response:
    """
    Logout API endpoint - returns redirect URI
    Clears security context and constructs OIDC logout URL
    
    Args:
        request: Request object
        token: Bearer token
        
    Returns:
        Response with redirect location header
    """
    host = request.headers.get("host", "localhost")
    hostname = host.split(':')[0]
    
    # Extract subdomain to find appropriate OAuth2 provider
    master_entity = settings.get_master_entity()
    subdomain = MultiTenantResolver.extract_subdomain(hostname, master_entity)
    
    # Get OAuth2 registration for this subdomain
    registrations = settings.get_oauth2_registrations()
    registration = registrations.get(subdomain, {})
    provider_key = registration.get('provider', f'keycloak-{subdomain}')
    
    # Get issuer URI
    providers = settings.get_oauth2_providers()
    issuer_uri = providers.get(provider_key, '')
    
    # Construct logout URL
    logout_uri = f"{issuer_uri.rstrip('/')}/protocol/openid-connect/logout"
    
    if token:
        # Add id_token_hint if available
        try:
            # Extract ID token claim
            logout_uri += f"?id_token_hint={token}"
        except Exception:
            pass
    
    # Add redirect URI
    scheme = settings.get_scheme()
    post_logout_redirect = settings.get_post_logout_redirect_path()
    redirect_uri = f"{scheme}://{host}{post_logout_redirect}"
    logout_uri += f"&post_logout_redirect_uri={redirect_uri}"
    
    logger.info(f"Logging out user - redirect to: {logout_uri}")
    
    # Return response with location header
    return Response(
        status_code=204,
        headers={"Location": logout_uri}
    )


@router.put("/logout", tags=["authentication"])
async def logout(
    request: Request,
    token: Optional[str] = Depends(extract_token)
) -> JSONResponse:
    """
    Logout endpoint - returns logout redirect URL in JSON body
    
    Args:
        request: Request object
        token: Bearer token
        
    Returns:
        JSON response with redirectURL
    """
    host = request.headers.get("host", "localhost")
    hostname = host.split(':')[0]
    
    # Extract subdomain
    master_entity = settings.get_master_entity()
    subdomain = MultiTenantResolver.extract_subdomain(hostname, master_entity)
    
    # Get OAuth2 registration
    registrations = settings.get_oauth2_registrations()
    registration = registrations.get(subdomain, {})
    provider_key = registration.get('provider', f'keycloak-{subdomain}')
    
    # Get issuer URI
    providers = settings.get_oauth2_providers()
    issuer_uri = providers.get(provider_key, '')
    
    # Construct logout URL
    logout_uri = f"{issuer_uri.rstrip('/')}/protocol/openid-connect/logout"
    
    if token:
        try:
            logout_uri += f"?id_token_hint={token}"
        except Exception:
            pass
    
    # Add redirect URI based on origin header
    scheme = settings.get_scheme()
    origin = request.headers.get('origin', f"{scheme}://{host}")
    post_logout_redirect = settings.get_post_logout_redirect_path()
    redirect_uri = f"{origin}{post_logout_redirect}"
    logout_uri += f"&post_logout_redirect_uri={redirect_uri}"
    
    logger.info(f"User logout initiated - redirect to: {logout_uri}")
    
    # Return JSON response with redirect URL
    return JSONResponse(
        status_code=202,
        content={"redirectURL": logout_uri},
        headers={"Location": logout_uri}
    )


@router.get("/health", tags=["health"])
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint
    
    Returns:
        Health status
    """
    return {
        "status": "UP",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "gateway-service"
    }


@router.get("/health/live", tags=["health"])
async def liveness() -> Dict[str, str]:
    """Kubernetes liveness probe"""
    return {"status": "UP"}


@router.get("/health/ready", tags=["health"])
async def readiness() -> Dict[str, str]:
    """Kubernetes readiness probe"""
    return {"status": "UP"}
