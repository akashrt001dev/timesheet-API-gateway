"""
Configuration management module - loads from .env and application-qa.yml
"""
import os
from typing import Any, Dict, Optional, List
from pathlib import Path
from dotenv import load_dotenv

# Load .env file on module import
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class ConfigManager:
    """Manages application configuration from environment variables"""
    
    _instance: Optional['ConfigManager'] = None
    
    def __new__(cls) -> 'ConfigManager':
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        pass
    
    # ====================================================================
    # Server Configuration
    # ====================================================================
    @classmethod
    def get_server_host(cls) -> str:
        """Get server host"""
        return os.getenv('SERVER_HOST', '0.0.0.0')
    
    @classmethod
    def get_server_port(cls) -> int:
        """Get server port"""
        return int(os.getenv('SERVER_PORT', '8000'))
    
    @classmethod
    def get_scheme(cls) -> str:
        """Get scheme (http/https)"""
        return os.getenv('SCHEME', 'https')
    
    @classmethod
    def get_debug(cls) -> bool:
        """Get debug mode"""
        return os.getenv('DEBUG', 'false').lower() == 'true'
    
    @classmethod
    def get_log_level(cls) -> str:
        """Get log level"""
        return os.getenv('LOG_LEVEL', 'INFO')
    
    @classmethod
    def get_app_profile(cls) -> str:
        """Get application profile"""
        return os.getenv('APP_PROFILE', 'qa')
    
    # ====================================================================
    # Gateway Configuration
    # ====================================================================
    @classmethod
    def get_master_entity(cls) -> str:
        """Get master entity name"""
        return os.getenv('MASTER_ENTITY_NAME', 'timesmart-master')
    
    @classmethod
    def get_gateway_base_uri(cls) -> str:
        """Get gateway base URI"""
        return os.getenv('GATEWAY_BASE_URI', 'https://localhost:8000')
    
    @classmethod
    def get_react_uri(cls) -> str:
        """Get React app URI"""
        return os.getenv('REACT_APP_URI', 'https://app.timesmart.io')
    
    @classmethod
    def get_flutter_uri(cls) -> str:
        """Get Flutter app URI"""
        return os.getenv('FLUTTER_APP_URI', 'https://app.timesmart.io')
    
    @classmethod
    def get_greetings_api_uri(cls) -> str:
        """Get Greetings API URI"""
        return os.getenv('GREETINGS_API_URI', 'https://localhost:6443/greetings')
    
    # ====================================================================
    # Keycloak Configuration
    # ====================================================================
    @classmethod
    def get_keycloak_server_url(cls) -> str:
        """Get Keycloak server URL"""
        return os.getenv('KEYCLOAK_SERVER_URL', 'https://idm.timesmart.io')
    
    @classmethod
    def get_keycloak_port(cls) -> int:
        """Get Keycloak port"""
        return int(os.getenv('KEYCLOAK_PORT', '443'))
    
    @classmethod
    def get_keycloak_realms(cls) -> List[str]:
        """Get list of Keycloak realms"""
        realms_str = os.getenv('KEYCLOAK_REALMS', 'timesmart-master')
        return [r.strip() for r in realms_str.split(',')]
    
    @classmethod
    def get_keycloak_issuers(cls) -> List[str]:
        """Get list of Keycloak issuers"""
        issuers_str = os.getenv('KEYCLOAK_ISSUERS', '')
        return [i.strip() for i in issuers_str.split(',')] if issuers_str else []
    
    # ====================================================================
    # OAuth2 Configuration - Dynamic
    # ====================================================================
    @classmethod
    def get_oauth2_providers(cls) -> Dict[str, str]:
        """
        Get OAuth2 providers configuration from environment
        Returns a dict mapping provider keys (like 'keycloak-apollo-demo') to issuer URIs
        Matches Java's spring.security.oauth2.client.provider configuration
        """
        realms = cls.get_keycloak_realms()
        providers = {}
        keycloak_url = cls.get_keycloak_server_url()
        
        for realm in realms:
            # Create provider key in format 'keycloak-{realm}'
            provider_key = f"keycloak-{realm}"
            env_key = f"OAUTH2_{realm.upper().replace('-', '_')}_ISSUER"
            issuer = os.getenv(env_key, f"{keycloak_url}/realms/{realm}")
            providers[provider_key] = issuer
        
        return providers
    
    @classmethod
    def get_oauth2_registrations(cls) -> Dict[str, Dict[str, str]]:
        """
        Get OAuth2 client registrations from environment
        Returns a dict mapping realm names to their registration config
        Matches Java's spring.security.oauth2.client.registration configuration
        """
        realms = cls.get_keycloak_realms()
        registrations = {}
        keycloak_url = cls.get_keycloak_server_url()
        scheme = cls.get_scheme()
        
        for realm in realms:
            # Replace hyphens with underscores for environment variable names
            env_realm = realm.upper().replace('-', '_')
            env_base = f"OAUTH2_{env_realm}"
            
            # Get issuer - fallback to constructing from realm
            issuer = os.getenv(f"{env_base}_ISSUER", f"{keycloak_url}/realms/{realm}")
            
            # Get redirect URI - fallback to standard format
            redirect_uri = os.getenv(
                f"{env_base}_REDIRECT_URI",
                f"{scheme}://{realm}.mytimesmart.com/login/oauth2/code/{realm}"
            )
            
            registrations[realm] = {
                'authorization_grant_type': 'authorization_code',
                'client_name': 'Keycloak',
                'client_id': os.getenv(f"{env_base}_CLIENT_ID", 'spring-addons-confidential'),
                'client_secret': os.getenv(f"{env_base}_CLIENT_SECRET", ''),
                'provider': f'keycloak-{realm}',  # Links to provider
                'issuer': issuer,
                'redirect_uri': redirect_uri,
                'scope': os.getenv(f"{env_base}_SCOPE", 'openid,profile,email,offline_access,roles'),
            }
        
        return registrations
    
    # ====================================================================
    # Gateway Routes Configuration
    # ====================================================================
    @classmethod
    def get_gateway_routes(cls) -> List[Dict[str, Any]]:
        """
        Get gateway routes configuration
        Matches Java's spring.cloud.gateway.routes configuration
        """
        return [
            # Frontend routes
            {
                'id': 'greetings',
                'uri': cls.get_greetings_api_uri(),
                'predicates': ['Path=/greetings/**'],
            },
            {
                'id': 'app',
                'uri': cls.get_react_uri(),
                'predicates': ['Path=/app/**'],
            },
            {
                'id': 'home',
                'uri': cls.get_flutter_uri(),
                'predicates': ['Path=/home/**'],
            },
            # Microservice routes - direct paths
            {
                'id': 'user-management-service',
                'uri': f"lb://{os.getenv('SERVICE_USER_MANAGEMENT_HOST', 'user-management-service')}",
                'predicates': ['Path=/auth/**, /user/**, /roles/**'],
                'filters': [
                    'RewritePath=/auth/(?<path>.*), /$\\{path}',
                    'RewritePath=/user/(?<path>.*), /$\\{path}',
                    'RewritePath=/roles/(?<path>.*), /$\\{path}'
                ],
            },
            # Microservice routes - API paths with /api prefix
            {
                'id': 'user-management-service-api',
                'uri': f"lb://{os.getenv('SERVICE_USER_MANAGEMENT_HOST', 'user-management-service')}",
                'predicates': ['Path=/api/user-management-service/**'],
                'filters': [
                    'RewritePath=/api/user-management-service/auth/(?<path>.*), /auth/$\\{path}',
                    'RewritePath=/api/user-management-service/user/(?<path>.*), /user/$\\{path}',
                    'RewritePath=/api/user-management-service/roles/(?<path>.*), /roles/$\\{path}'
                ],
            },
            {
                'id': 'contract-managment-service',
                'uri': f"lb://{os.getenv('SERVICE_CONTRACT_MANAGEMENT_HOST', 'contract-managment-service')}",
                'predicates': ['Path=/contracts/**'],
                'filters': ['RewritePath=/contracts/(?<path>.*), /$\\{path}'],
            },
            {
                'id': 'contract-managment-service-api',
                'uri': f"lb://{os.getenv('SERVICE_CONTRACT_MANAGEMENT_HOST', 'contract-managment-service')}",
                'predicates': ['Path=/api/contract-managment-service/**'],
                'filters': [],  # No rewrite for API path
            },
            {
                'id': 'entity-service',
                'uri': f"lb://{os.getenv('SERVICE_ENTITY_HOST', 'entity-service')}",
                'predicates': ['Path=/entity/**, /entityID/**'],
                'filters': ['RewritePath=/entity/(?<path>.*), /$\\{path}'],
            },
            {
                'id': 'entity-service-api',
                'uri': f"lb://{os.getenv('SERVICE_ENTITY_HOST', 'entity-service')}",
                'predicates': ['Path=/api/entity-service/**'],
                'filters': [],  # No rewrite for API path
            },
            {
                'id': 'timesheet-management-service',
                'uri': f"lb://{os.getenv('SERVICE_TIMESHEET_MANAGEMENT_HOST', 'timesheet-management-service')}",
                'predicates': ['Path=/timesheet/**, /activity/**'],
                'filters': [
                    'RewritePath=/timesheet/(?<path>.*), /$\\{path}',
                    'RewritePath=/activity/(?<path>.*), /$\\{path}'
                ],
            },
            {
                'id': 'timesheet-management-service-api',
                'uri': f"lb://{os.getenv('SERVICE_TIMESHEET_MANAGEMENT_HOST', 'timesheet-management-service')}",
                'predicates': ['Path=/api/timesheet-management-service/**'],
                'filters': [],  # No rewrite for API path
            },
            {
                'id': 'notification-service',
                'uri': f"lb://{os.getenv('SERVICE_NOTIFICATION_HOST', 'notification-service')}",
                'predicates': ['Path=/emailtemplate/**'],
                'filters': [
                    'RewritePath=/emailtemplate/(?<path>.*), /$\\{path}',
                    'RemoveRequestHeader=Cookie,Set-Cookie'
                ],
            },
        ]
    
    # ====================================================================
    # Eureka Configuration
    # ====================================================================
    @classmethod
    def get_eureka_url(cls) -> str:
        """Get Eureka service registry URL"""
        return os.getenv('EUREKA_URL', 'http://localhost:8761/eureka/')
    
    @classmethod
    def get_eureka_enabled(cls) -> bool:
        """Check if Eureka is enabled"""
        return os.getenv('EUREKA_ENABLED', 'true').lower() == 'true'
    
    @classmethod
    def get_eureka_prefer_ip_address(cls) -> bool:
        """Check if Eureka should prefer IP address"""
        return os.getenv('EUREKA_PREFER_IP_ADDRESS', 'true').lower() == 'true'
    
    @classmethod
    def get_eureka_heartbeat_interval(cls) -> int:
        """Get Eureka heartbeat interval in seconds"""
        return int(os.getenv('EUREKA_HEARTBEAT_INTERVAL', '30'))
    
    # ====================================================================
    # Security & CORS Configuration
    # ====================================================================
    @classmethod
    def get_csrf_cookie_accessible_from_js(cls) -> bool:
        """Check if CSRF cookie is accessible from JS"""
        return os.getenv('CSRF_COOKIE_ACCESSIBLE_FROM_JS', 'true').lower() == 'true'
    
    @classmethod
    def get_login_path(cls) -> str:
        """Get login path"""
        return os.getenv('LOGIN_PATH', '/')
    
    @classmethod
    def get_post_login_redirect_path(cls) -> str:
        """Get post-login redirect path"""
        return os.getenv('POST_LOGIN_REDIRECT_PATH', '/home/')
    
    @classmethod
    def get_post_logout_redirect_path(cls) -> str:
        """Get post logout redirect path"""
        return os.getenv('POST_LOGOUT_REDIRECT_PATH', '/home')
    
    @classmethod
    def get_back_channel_logout_enabled(cls) -> bool:
        """Check if back-channel logout is enabled"""
        return os.getenv('BACK_CHANNEL_LOGOUT_ENABLED', 'true').lower() == 'true'
    
    @classmethod
    def get_permit_all_paths(cls) -> List[str]:
        """Get paths that permit all access"""
        paths_str = os.getenv('PERMIT_ALL_PATHS', '/login/**,/oauth2/**,/,/login-options,/me')
        return [p.strip() for p in paths_str.split(',')]
    
    # ====================================================================
    # Timeouts & Lifecycle Configuration
    # ====================================================================
    @classmethod
    def get_shutdown_timeout(cls) -> int:
        """Get shutdown timeout in seconds"""
        return int(os.getenv('SHUTDOWN_TIMEOUT_SECONDS', '30'))
    
    @classmethod
    def get_connection_timeout(cls) -> int:
        """Get connection timeout in seconds"""
        return int(os.getenv('CONNECTION_TIMEOUT_SECONDS', '30'))
    
    @classmethod
    def get_request_timeout(cls) -> int:
        """Get request timeout in seconds"""
        return int(os.getenv('REQUEST_TIMEOUT_SECONDS', '60'))
    
    # ====================================================================
    # Health Check Configuration
    # ====================================================================
    @classmethod
    def get_health_endpoint_enabled(cls) -> bool:
        """Check if health endpoint is enabled"""
        return os.getenv('HEALTH_ENDPOINT_ENABLED', 'true').lower() == 'true'
    
    @classmethod
    def get_health_liveness_enabled(cls) -> bool:
        """Check if liveness probe is enabled"""
        return os.getenv('HEALTH_LIVENESS_ENABLED', 'true').lower() == 'true'
    
    @classmethod
    def get_health_readiness_enabled(cls) -> bool:
        """Check if readiness probe is enabled"""
        return os.getenv('HEALTH_READINESS_ENABLED', 'true').lower() == 'true'
    
    @classmethod
    def get_health_check_interval(cls) -> int:
        """Get health check interval in seconds"""
        return int(os.getenv('HEALTH_CHECK_INTERVAL_SECONDS', '30'))
    
    @classmethod
    def get_health_check_timeout(cls) -> int:
        """Get health check timeout in seconds"""
        return int(os.getenv('HEALTH_CHECK_TIMEOUT_SECONDS', '10'))
    
    @classmethod
    def get_health_check_retries(cls) -> int:
        """Get health check retries"""
        return int(os.getenv('HEALTH_CHECK_RETRIES', '3'))
    
    # ====================================================================
    # Logging Configuration
    # ====================================================================
    @classmethod
    def get_log_level_root(cls) -> str:
        """Get root log level"""
        return os.getenv('LOG_LEVEL_ROOT', 'ERROR')
    
    @classmethod
    def get_log_level_security(cls) -> str:
        """Get security log level"""
        return os.getenv('LOG_LEVEL_SECURITY', 'DEBUG')
    
    @classmethod
    def get_log_format(cls) -> str:
        """Get log format (text or json)"""
        return os.getenv('LOG_FORMAT', 'json')
    
    # ====================================================================
    # Feature Flags
    # ====================================================================
    @classmethod
    def is_eureka_discovery_enabled(cls) -> bool:
        """Check if Eureka discovery is enabled"""
        return os.getenv('FEATURE_EUREKA_DISCOVERY', 'true').lower() == 'true'
    
    @classmethod
    def is_token_relay_enabled(cls) -> bool:
        """Check if token relay is enabled"""
        return os.getenv('FEATURE_TOKEN_RELAY', 'true').lower() == 'true'
    
    @classmethod
    def is_request_logging_enabled(cls) -> bool:
        """Check if request logging is enabled"""
        return os.getenv('FEATURE_REQUEST_LOGGING', 'true').lower() == 'true'
    
    @classmethod
    def is_cors_headers_enabled(cls) -> bool:
        """Check if CORS headers are enabled"""
        return os.getenv('FEATURE_CORS_HEADERS', 'true').lower() == 'true'
    
    @classmethod
    def is_session_management_enabled(cls) -> bool:
        """Check if session management is enabled"""
        return os.getenv('FEATURE_SESSION_MANAGEMENT', 'true').lower() == 'true'
    
    # ====================================================================
    # Gateway Discovery Configuration
    # ====================================================================
    @classmethod
    def is_gateway_discovery_enabled(cls) -> bool:
        """Check if gateway discovery locator is enabled"""
        return os.getenv('GATEWAY_DISCOVERY_ENABLED', 'true').lower() == 'true'
    
    @classmethod
    def is_lower_case_service_id(cls) -> bool:
        """Check if service IDs should be converted to lowercase"""
        return os.getenv('GATEWAY_LOWER_CASE_SERVICE_ID', 'true').lower() == 'true'
    
    # ====================================================================
    # Microservice Configuration
    # ====================================================================
    @classmethod
    def get_known_services(cls) -> list:
        """Get list of known microservices for direct routing"""
        services_str = os.getenv('KNOWN_SERVICES', '')
        if not services_str:
            return []
        return [s.strip() for s in services_str.split(',')]
    
    @classmethod
    def get_service_url(cls, service_name: str) -> str:
        """Get service URL by service name"""
        env_key = f"SERVICE_{service_name.upper()}_URL"
        return os.getenv(env_key, "")
    
    @classmethod
    def get_service_host(cls, service_name: str) -> str:
        """Get service host by service name"""
        # Normalize service name for env variable lookup
        # Remove trailing "-service" suffix and replace hyphens with underscores
        if service_name.endswith('-service'):
            normalized_name = service_name[:-8]  # Remove "-service" suffix
        else:
            normalized_name = service_name
        normalized_name = normalized_name.replace('-', '_').upper()
        env_key = f"SERVICE_{normalized_name}_HOST"
        return os.getenv(env_key, service_name)
    
    @classmethod
    def get_service_port(cls, service_name: str) -> int:
        """Get service port by service name"""
        # Normalize service name for env variable lookup
        # Remove trailing "-service" suffix and replace hyphens with underscores
        if service_name.endswith('-service'):
            normalized_name = service_name[:-8]  # Remove "-service" suffix
        else:
            normalized_name = service_name
        normalized_name = normalized_name.replace('-', '_').upper()
        env_key = f"SERVICE_{normalized_name}_PORT"
        port_str = os.getenv(env_key, "")
        return int(port_str) if port_str else 0


# Create singleton instance
settings = ConfigManager()

# Initialize configuration singleton
config = ConfigManager()

