"""
Gateway controller routes - main gateway endpoints
"""
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Request, Response, Header, Depends
from fastapi.responses import RedirectResponse, JSONResponse
import json
import httpx
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


@router.get("/home", tags=["home"])
@router.get("/home/", tags=["home"])
async def home_page(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    provider: Optional[str] = None,
    authorization: Optional[str] = Header(None)
) -> Dict[str, Any]:
    """
    Home page endpoint
    Displays dashboard or returns status information
    
    Args:
        request: Request object
        code: Authorization code from OAuth2 callback
        state: State parameter from OAuth2 callback
        provider: OAuth2 provider/realm
        authorization: Authorization header (Bearer token)
        
    Returns:
        Home page data or redirect
    """
    # Check if user is authenticated
    is_authenticated = authorization and authorization.startswith('Bearer ')
    
    logger.info(f"Home page accessed - authenticated: {is_authenticated}")
    
    if code:
        logger.info(f"Processing authorization code from {provider}")
        # Authorization code is in the URL, frontend should handle token exchange
        return {
            "status": "success",
            "message": "Ready to exchange authorization code for tokens",
            "code": code,
            "state": state,
            "provider": provider,
            "authenticated": is_authenticated
        }
    
    if is_authenticated:
        # Get user info
        token = authorization[7:]  # Remove 'Bearer ' prefix
        user = TokenProcessor.extract_user_info(token)
        logger.info(f"User {user.subject} accessing home page")
        return {
            "status": "authenticated",
            "message": "Welcome to the application",
            "user": user.dict() if hasattr(user, 'dict') else user.__dict__
        }
    else:
        logger.info("Unauthenticated user accessing home page")
        host = request.headers.get("host", "localhost")
        hostname = host.split(':')[0]
        master_entity = settings.get_master_entity()
        realm = MultiTenantResolver.extract_subdomain(hostname, master_entity)
        
        return {
            "status": "unauthenticated",
            "message": "Please login to continue",
            "login_url": f"{settings.get_scheme()}://{host}/oauth2/authorization/{realm}"
        }


@router.post("/oauth2/token", tags=["authentication"])
async def exchange_authorization_code(
    request: Request,
    code: str,
    provider: str,
    redirect_uri: Optional[str] = None
) -> Response:
    """
    Exchange authorization code for access token
    
    Args:
        request: Request object
        code: Authorization code from Keycloak
        provider: OAuth2 provider/realm name
        redirect_uri: Redirect URI (optional, uses registered URI if not provided)
        
    Returns:
        JSON response with tokens and user info
    """
    logger.info(f"Token exchange request for provider: {provider}")
    
    # Get OAuth2 registration
    registrations = settings.get_oauth2_registrations()
    registration = registrations.get(provider, {})
    
    if not registration or not registration.get('issuer'):
        logger.error(f"Unknown OAuth2 provider: {provider}")
        return JSONResponse(
            status_code=404,
            content={"error": "Unknown OAuth2 provider"}
        )
    
    # Get Keycloak configuration
    issuer_uri = registration.get('issuer', '').rstrip('/')
    client_id = registration.get('client_id')
    client_secret = registration.get('client_secret')
    registered_redirect_uri = registration.get('redirect_uri')
    
    # Use provided redirect_uri or fall back to registered one
    final_redirect_uri = redirect_uri or registered_redirect_uri
    
    if not client_id or not client_secret:
        logger.error(f"Missing OAuth2 credentials for provider: {provider}")
        return JSONResponse(
            status_code=500,
            content={"error": "OAuth2 credentials not configured"}
        )
    
    # Token endpoint
    token_endpoint = f"{issuer_uri}/protocol/openid-connect/token"
    
    # Prepare token request
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": final_redirect_uri
    }
    
    try:
        # Exchange authorization code for tokens
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                token_endpoint,
                data=token_data,
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                return JSONResponse(
                    status_code=response.status_code,
                    content={"error": "Token exchange failed", "details": response.text}
                )
            
            token_response = response.json()
            
            # Extract tokens
            access_token = token_response.get('access_token')
            refresh_token = token_response.get('refresh_token')
            id_token = token_response.get('id_token')
            expires_in = token_response.get('expires_in', 300)
            
            logger.info(f"Token exchange successful for provider: {provider}")
            logger.debug(f"Access token issued with {expires_in}s expiration")
            
            # Extract user info from access token
            user_info = TokenProcessor.extract_user_info(access_token) if access_token else None
            
            # Create response with tokens
            json_response = {
                "status": "success",
                "message": "Token exchange successful",
                "provider": provider,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "id_token": id_token,
                "expires_in": expires_in,
                "token_type": token_response.get('token_type', 'Bearer'),
                "user": user_info.dict() if user_info and hasattr(user_info, 'dict') else user_info.__dict__ if user_info else None
            }
            
            # Create response with HTTP-only cookie
            response_obj = JSONResponse(content=json_response, status_code=200)
            
            # Set secure HTTP-only cookies for tokens
            response_obj.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=settings.get_scheme() == "https",
                samesite="Lax",
                max_age=expires_in
            )
            
            if refresh_token:
                response_obj.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    httponly=True,
                    secure=settings.get_scheme() == "https",
                    samesite="Lax",
                    max_age=7 * 24 * 60 * 60  # 7 days
                )
            
            logger.info(f"Tokens stored in HTTP-only cookies for user")
            
            return response_obj
            
    except Exception as e:
        logger.error(f"Token exchange error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Token exchange failed", "details": str(e)}
        )


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
