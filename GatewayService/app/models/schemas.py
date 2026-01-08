"""
Data models for request/response handling
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UserDto(BaseModel):
    """User information DTO"""
    subject: str = Field(default="", description="User subject/ID from token")
    issuer: str = Field(default="", description="Token issuer URL")
    roles: List[str] = Field(default_factory=list, description="User roles/authorities")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject": "user123",
                "issuer": "https://idm.timesmart.io/realms/timesmart-master",
                "roles": ["admin", "user"]
            }
        }
    
    @staticmethod
    def anonymous() -> 'UserDto':
        """Return anonymous user"""
        return UserDto(subject="", issuer="", roles=[])


class LoginOptionDto(BaseModel):
    """Login option DTO"""
    label: str = Field(description="Provider name/label")
    loginUri: str = Field(description="OAuth2 authorization URI")
    
    class Config:
        json_schema_extra = {
            "example": {
                "label": "keycloak",
                "loginUri": "https://app.timesmart.io/oauth2/authorization/timesmart-master"
            }
        }


class OAuthToken(BaseModel):
    """OAuth2 token information"""
    access_token: str
    token_type: str = "Bearer"
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    scope: Optional[str] = None


class TokenClaims(BaseModel):
    """JWT token claims"""
    sub: str = Field(default="", alias="subject")
    preferred_username: Optional[str] = None
    email: Optional[str] = None
    realm_access: Optional[Dict[str, Any]] = None
    resource_access: Optional[Dict[str, Any]] = None
    iss: Optional[str] = None
    aud: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    
    class Config:
        populate_by_name = True


class LogoutRequest(BaseModel):
    """Logout request"""
    redirectURL: Optional[str] = None


class GatewayRoute(BaseModel):
    """Gateway route configuration"""
    id: str
    uri: str
    predicates: List[Dict[str, Any]]
    filters: Optional[List[Dict[str, Any]]] = None


class ErrorResponse(BaseModel):
    """Error response"""
    detail: str
    status_code: int
    timestamp: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "UP"
    checks: Optional[Dict[str, Any]] = None
