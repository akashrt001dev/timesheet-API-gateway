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
    
    if not registration:
        logger.error(f"No OAuth2 registration found for realm: {realm}")
        return JSONResponse(
            status_code=404,
            content={"error": f"No OAuth2 configuration for realm: {realm}"}
        )
    
    # Get provider configuration
    provider_key = registration.get('provider', f'keycloak-{realm}')
    providers = settings.get_oauth2_providers()
    issuer_uri = providers.get(provider_key, '')
    
    if not issuer_uri:
        logger.error(f"No issuer URI found for provider: {provider_key}")
        return JSONResponse(
            status_code=500,
            content={"error": f"OAuth2 provider not configured: {provider_key}"}
        )
    
    # Get OAuth2 client configuration
    client_id = registration.get('client_id')
    redirect_uri = registration.get('redirect_uri')
    scope = registration.get('scope', 'openid profile email')
    
    # Get authorization endpoint from issuer
    auth_endpoint = f"{issuer_uri.rstrip('/')}/protocol/openid-connect/auth"
    
    # Get authorization request parameters
    query_params = request.query_params
    
    # Build authorization URL
    authorization_url = (
        f"{auth_endpoint}"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&state={query_params.get('state', '')}"
    )
    
    if query_params.get('nonce'):
        authorization_url += f"&nonce={query_params.get('nonce')}"
    
    logger.info(f"Redirecting to OAuth2 authorization for realm: {realm}")
    logger.debug(f"Authorization endpoint: {auth_endpoint}")
    
    return RedirectResponse(url=authorization_url, status_code=302)


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
