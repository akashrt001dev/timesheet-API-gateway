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


def error_response(message: str, status_code: int = 500) -> Response:
    """Create JSON error response"""
    try:
        content = json.dumps({"error": message})
    except Exception as e:
        logger.error(f"Failed to encode error: {e}")
        content = json.dumps({"error": "Internal Server Error"})
    
    return Response(
        content=content.encode(),
        status_code=status_code,
        media_type="application/json"
    )


def extract_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract Bearer token from Authorization header"""
    if authorization and authorization.startswith('Bearer '):
        return authorization[7:]  # Remove 'Bearer ' prefix
    return None


@router.get("/home/{path_name:path}", tags=["frontend"])
async def frontend_assets(
    path_name: str,
    request: Request,
    code: Optional[str] = None,
    provider: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    session_state: Optional[str] = None
) -> Response:
    """
    Handle frontend requests and assets
    - If plain /home/ with OAuth2 params: inject params into HTML
    - Otherwise: proxy static assets directly
    
    Args:
        path_name: Path within /home/ (empty string for /home/)
        request: Request object
        code, provider, state, error, error_description, session_state: OAuth2 params
        
    Returns:
        Proxied response or HTML with injected OAuth2 parameters
    """
    import httpx
    
    # Get frontend URL
    frontend_url = settings.get_react_uri()
    
    # Construct full path
    if path_name:
        frontend_request_url = f"{frontend_url}/home/{path_name}"
        is_asset_request = True
    else:
        frontend_request_url = f"{frontend_url}/home/"
        is_asset_request = False
    
    # Include query parameters if present
    if request.query_params:
        query_string = "&".join([f"{k}={v}" for k, v in request.query_params.items()])
        frontend_request_url += f"?{query_string}"
    
    try:
        logger.debug(f"Frontend request: {path_name or '/'} -> {frontend_request_url}")
        
        # Fetch from frontend service
        async with httpx.AsyncClient(verify=False, follow_redirects=True) as client:
            response = await client.get(frontend_request_url)
        
        # For plain /home/ requests with OAuth2 params, inject them into the HTML
        if not is_asset_request and (code or provider or state or error or session_state):
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
            
            logger.info(f"OAuth2 home page - provider: {provider}, OAuth2 params injected")
            
            return Response(
                content=html_content,
                status_code=200,
                media_type="text/html; charset=utf-8"
            )
        
        # For other requests, return proxied response as-is
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get('content-type', 'application/octet-stream'),
            headers=dict(response.headers)
        )
    
    except Exception as e:
        logger.error(f"Error handling frontend request {path_name}: {str(e)}")
        return error_response(f"Failed to fetch frontend: {str(e)}", 502)




@router.get("/", tags=["root"])
async def redirect_index_to_ui(request: Request) -> RedirectResponse:
    """
    Redirect root to OAuth2 authorization
    Extracts subdomain/tenant from hostname (works with both domains and IPs)
    Matches Java BffApplication.redirectIndexToUi behavior
    
    Returns:
        Redirect response to OAuth2 authorization endpoint
    """
    # Get hostname from request (check X-Forwarded-Host first for proxy support)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    hostname = host.split(':')[0]  # Remove port
    
    # Extract first part of hostname as subdomain/tenant identifier
    # Works with: domains (tenant.example.com -> tenant), IPs (127.0.0.1 -> 127), localhost (-> localhost)
    hostparts = hostname.split(".")
    subdomain = hostparts[0] if hostparts and hostparts[0] else settings.get_master_entity()
    
    # Only use master entity as fallback if we couldn't extract any subdomain
    if not subdomain or subdomain == "":
        subdomain = settings.get_master_entity()
    
    # Get scheme (check X-Forwarded-Proto for proxy support)
    scheme = request.headers.get("x-forwarded-proto") or settings.get_scheme()
    
    # Construct redirect URL - matches Java format
    redirect_url = f"{scheme}://{host}/oauth2/authorization/{subdomain}"
    
    logger.info(f"Redirecting root request to: {redirect_url} (subdomain: {subdomain}, hostname: {hostname})")
    
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
    Exchanges authorization code for Bearer token and redirects to frontend
    
    Args:
        provider: OAuth2 provider/realm name
        code: Authorization code from Keycloak
        state: State parameter for CSRF protection
        error: Error code (if authorization failed)
        error_description: Error description
        request: Request object
        
    Returns:
        Redirect response with token or error
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
    
    # Prepare token exchange parameters
    issuer_uri = registration.get('issuer')
    client_id = registration.get('client_id')
    client_secret = registration.get('client_secret')
    
    if not client_id or not client_secret:
        logger.error(f"Missing OAuth2 credentials for {provider}")
        error_redirect = f"{scheme}://{host}/login?error=missing_credentials"
        return RedirectResponse(url=error_redirect, status_code=302)
    
    # Construct redirect_uri (same as the authorization request)
    callback_uri = f"{scheme}://{host}/login/oauth2/code/{provider}"
    
    # Exchange authorization code for tokens
    logger.info(f"Exchanging authorization code for tokens from {provider}")
    token_response = await TokenProcessor.exchange_authorization_code(
        code=code,
        issuer_uri=issuer_uri,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=callback_uri
    )
    
    if not token_response or 'access_token' not in token_response:
        logger.error(f"Failed to exchange authorization code for tokens from {provider}")
        error_redirect = f"{scheme}://{host}/login?error=token_exchange_failed"
        return RedirectResponse(url=error_redirect, status_code=302)
    
    access_token = token_response.get('access_token')
    refresh_token = token_response.get('refresh_token')
    id_token = token_response.get('id_token')
    
    logger.info(f"Successfully obtained access token from {provider}")
    
    # Get post-login redirect path
    post_login_path = settings.get_post_login_redirect_path()
    redirect_url = f"{scheme}://{host}{post_login_path}"
    
    # Redirect to frontend with Bearer token in Authorization header
    # The frontend will receive the token and use it for API calls
    response = RedirectResponse(url=redirect_url, status_code=302)
    
    # Set Authorization header with Bearer token in redirect
    # Note: Browsers won't send Authorization header in redirects
    # So we pass token as query parameter and frontend stores it
    if state:
        redirect_url = f"{redirect_url}?access_token={access_token}&token_type=Bearer&state={state}"
    else:
        redirect_url = f"{redirect_url}?access_token={access_token}&token_type=Bearer"
    
    response = RedirectResponse(url=redirect_url, status_code=302)
    
    logger.info(f"Redirecting to {post_login_path} with Bearer token")
    return response


@router.get("/login-options", response_model=List[LoginOptionDto], tags=["authentication"])
async def get_login_options(
    request: Request,
    authorization: Optional[str] = Header(None)
) -> List[LoginOptionDto]:
    """
    Get available login options (OAuth2 providers)
    Returns empty list if already authenticated
    Matches Java GatewayController.getLoginOptions behavior
    
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
    
    # Get hostname (check X-Forwarded-Host for proxy support)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    hostname = host.split(':')[0]
    
    # Extract first part of hostname as subdomain/tenant identifier
    # Works with: domains (tenant.example.com -> tenant), IPs (127.0.0.1 -> 127), localhost (-> localhost)
    hostparts = hostname.split(".")
    subdomain = hostparts[0] if hostparts and hostparts[0] else settings.get_master_entity()
    
    # Only use master entity as fallback if we couldn't extract any subdomain
    if not subdomain or subdomain == "":
        subdomain = settings.get_master_entity()
    
    # Get scheme (check X-Forwarded-Proto for proxy support)
    scheme = request.headers.get("x-forwarded-proto") or settings.get_scheme()
    
    # Construct login URI - match Java format (uses scheme from settings or header)
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
    Matches Java GatewayController.getMe behavior
    Extracts subject, issuer, and roles from OAuth2/OIDC token
    
    Args:
        token: Bearer token from Authorization header
        
    Returns:
        UserDto with user information or anonymous user
    """
    if not token:
        logger.debug("No token provided - returning anonymous user")
        return UserDto.anonymous()
    
    # Extract user information from token
    # Java extracts: subject, issuer URL, and authorities (roles)
    user = TokenProcessor.extract_user_info(token)
    
    logger.info(f"Retrieved user info: subject={user.subject}, issuer={user.issuer}, roles={user.roles}")
    
    return user


@router.get("/logout_api", tags=["authentication"])
async def logout_api(
    request: Request,
    token: Optional[str] = Depends(extract_token)
) -> Response:
    """
    Logout API endpoint - returns redirect URI with 204 No Content
    Clears security context and constructs OIDC logout URL
    Matches Java GatewayController.logout_api behavior
    
    Args:
        request: Request object
        token: Bearer token
        
    Returns:
        Response with redirect location header (204 No Content)
    """
    # Get hostname (check X-Forwarded-Host for proxy support)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    hostname = host.split(':')[0]
    
    # Extract first part of hostname as subdomain/tenant identifier
    hostparts = hostname.split(".")
    subdomain = hostparts[0] if hostparts and hostparts[0] else settings.get_master_entity()
    
    # Get OAuth2 registration for this subdomain
    registrations = settings.get_oauth2_registrations()
    registration = registrations.get(subdomain, {})
    
    # Get issuer URI from registration
    issuer_uri = registration.get('issuer', '')
    
    if not issuer_uri:
        # Fallback to provider lookup
        provider_key = registration.get('provider', f'keycloak-{subdomain}')
        providers = settings.get_oauth2_providers()
        provider_info = providers.get(provider_key, {})
        issuer_uri = provider_info if isinstance(provider_info, str) else provider_info.get('issuer_uri', '')
    
    # Construct logout URL
    logout_uri = f"{issuer_uri.rstrip('/')}/protocol/openid-connect/logout"
    
    # Build query parameters
    params = []
    if token:
        # Add id_token_hint if available (Java uses idToken.getTokenValue())
        params.append(f"id_token_hint={token}")
    
    # Add post_logout_redirect_uri - Java uses headers.getHost().getHostName()
    scheme = request.headers.get("x-forwarded-proto") or settings.get_scheme()
    post_logout_redirect = settings.get_post_logout_redirect_path()
    redirect_uri = f"{scheme}://{hostname}{post_logout_redirect}"
    params.append(f"post_logout_redirect_uri={redirect_uri}")
    
    if params:
        logout_uri += "?" + "&".join(params)
    
    logger.info(f"Logging out user - redirect to: {logout_uri}")
    
    # Return 204 No Content with Location header (matches Java ResponseEntity.noContent().location())
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
    Logout endpoint - returns logout redirect URL in JSON body with 202 Accepted
    Matches Java GatewayController.logout behavior
    
    Args:
        request: Request object
        token: Bearer token
        
    Returns:
        JSON response with redirectURL (202 Accepted)
    """
    # Get hostname (check X-Forwarded-Host for proxy support)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "localhost")
    hostname = host.split(':')[0]
    
    # Extract first part of hostname as subdomain/tenant identifier
    hostparts = hostname.split(".")
    subdomain = hostparts[0] if hostparts and hostparts[0] else settings.get_master_entity()
    
    # Get OAuth2 registration
    registrations = settings.get_oauth2_registrations()
    registration = registrations.get(subdomain, {})
    
    # Get issuer URI from registration
    issuer_uri = registration.get('issuer', '')
    
    if not issuer_uri:
        # Fallback to provider lookup
        provider_key = registration.get('provider', f'keycloak-{subdomain}')
        providers = settings.get_oauth2_providers()
        provider_info = providers.get(provider_key, {})
        issuer_uri = provider_info if isinstance(provider_info, str) else provider_info.get('issuer_uri', '')
    
    # Construct logout URL
    logout_uri = f"{issuer_uri.rstrip('/')}/protocol/openid-connect/logout"
    
    # Build query parameters
    params = []
    if token:
        params.append(f"id_token_hint={token}")
    
    # Add redirect URI based on Origin header (Java uses headers.getOrigin())
    origin = request.headers.get('origin')
    if not origin:
        scheme = request.headers.get("x-forwarded-proto") or settings.get_scheme()
        origin = f"{scheme}://{host}"
    
    post_logout_redirect = settings.get_post_logout_redirect_path()
    redirect_uri = f"{origin}{post_logout_redirect}"
    params.append(f"post_logout_redirect_uri={redirect_uri}")
    
    if params:
        logout_uri += "?" + "&".join(params)
    
    logger.info(f"User logout initiated - redirect to: {logout_uri}")
    
    # Return JSON response with redirect URL (matches Java ResponseEntity.accepted().location().body())
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
