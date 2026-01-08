"""
OAuth2 and JWT utilities for token processing
"""
import json
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime
import jwt
from jwt import PyJWTError
import httpx
from app.models.schemas import TokenClaims, UserDto


class TokenProcessor:
    """Process and validate OAuth2/OIDC tokens"""
    
    ALGORITHM = "RS256"
    
    @staticmethod
    def decode_token_header(token: str) -> Dict[str, Any]:
        """
        Decode JWT header without verification (for getting 'kid')
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded header dict
        """
        try:
            header = jwt.get_unverified_header(token)
            return header
        except PyJWTError:
            return {}
    
    @staticmethod
    def decode_token_payload(token: str) -> Optional[Dict[str, Any]]:
        """
        Decode JWT payload without verification
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded payload dict or None
        """
        try:
            # Split token and decode payload
            parts = token.split('.')
            if len(parts) != 3:
                return None
            
            # Add padding if needed
            payload = parts[1]
            payload += '=' * (4 - len(payload) % 4)
            
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)
        except Exception:
            return None
    
    @staticmethod
    def extract_claims(token: str) -> Optional[TokenClaims]:
        """
        Extract token claims
        
        Args:
            token: JWT token string
            
        Returns:
            TokenClaims object or None
        """
        payload = TokenProcessor.decode_token_payload(token)
        if not payload:
            return None
        
        try:
            return TokenClaims(**payload)
        except Exception:
            return None
    
    @staticmethod
    def extract_user_info(token: str) -> UserDto:
        """
        Extract user information from token
        
        Args:
            token: JWT token string
            
        Returns:
            UserDto with user information
        """
        claims = TokenProcessor.extract_claims(token)
        if not claims:
            return UserDto.anonymous()
        
        # Extract roles from realm_access and resource_access
        roles: List[str] = []
        
        if claims.realm_access and 'roles' in claims.realm_access:
            roles.extend(claims.realm_access['roles'])
        
        if claims.resource_access:
            for resource, access in claims.resource_access.items():
                if isinstance(access, dict) and 'roles' in access:
                    roles.extend(access['roles'])
        
        return UserDto(
            subject=claims.sub or "",
            issuer=claims.iss or "",
            roles=list(set(roles))  # Remove duplicates
        )
    
    @staticmethod
    def get_id_token_value(token: str) -> str:
        """Get ID token value (the token itself)"""
        return token


class MultiTenantResolver:
    """Resolve tenant/subdomain from hostname"""
    
    @staticmethod
    def extract_subdomain(hostname: str, master_entity: str) -> str:
        """
        Extract subdomain from hostname
        
        Args:
            hostname: Request hostname (e.g., tenant1.example.com)
            master_entity: Default master entity name
            
        Returns:
            Subdomain/tenant name
        """
        if not hostname:
            return master_entity
        
        # Remove port if present
        hostname = hostname.split(':')[0]
        
        # Split by dots
        parts = hostname.split('.')
        
        # If 3+ parts, first part is subdomain (e.g., tenant1.example.com)
        if len(parts) >= 3:
            return parts[0]
        
        # Otherwise return master entity
        return master_entity
    
    @staticmethod
    def get_oauth2_registration_id(subdomain: str) -> str:
        """
        Get OAuth2 registration ID from subdomain
        
        Args:
            subdomain: Tenant subdomain name
            
        Returns:
            OAuth2 registration ID
        """
        # Mapping: subdomain -> registration ID
        # Based on config, most registrations match subdomain directly
        return subdomain


class OAuthClientHelper:
    """Helper for OAuth2 client operations"""
    
    @staticmethod
    async def get_token_introspection(
        token: str,
        issuer_uri: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get token introspection from OAuth2 provider
        
        Args:
            token: Access token
            issuer_uri: Issuer URI from configuration
            
        Returns:
            Introspection result or None
        """
        try:
            # Construct introspection endpoint
            introspection_url = f"{issuer_uri.rstrip('/')}/protocol/openid-connect/token/introspect"
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(
                    introspection_url,
                    data={'token': token},
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    return response.json()
        except Exception:
            pass
        
        return None
    
    @staticmethod
    async def revoke_token(
        token: str,
        issuer_uri: str,
        client_id: str,
        client_secret: str
    ) -> bool:
        """
        Revoke a token
        
        Args:
            token: Token to revoke
            issuer_uri: Issuer URI
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
            
        Returns:
            True if successful
        """
        try:
            revocation_url = f"{issuer_uri.rstrip('/')}/protocol/openid-connect/revoke"
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(
                    revocation_url,
                    data={
                        'token': token,
                        'client_id': client_id,
                        'client_secret': client_secret
                    },
                    timeout=10.0
                )
                
                return response.status_code in (200, 204)
        except Exception:
            return False
