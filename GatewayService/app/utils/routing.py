"""
HTTP and routing utilities
"""
import re
import logging
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urljoin, urlparse
import httpx

logger = logging.getLogger(__name__)


class PathRewriter:
    """Handle path rewriting for routing"""
    
    @staticmethod
    def rewrite_path(
        original_path: str,
        rewrite_rules: List[str]
    ) -> str:
        """
        Apply path rewriting rules (regex-based)
        
        Args:
            original_path: Original request path
            rewrite_rules: List of rewrite rules
            
        Returns:
            Rewritten path
        """
        rewritten_path = original_path
        
        for rule in rewrite_rules:
            # Parse rule format: RewritePath=/old/(?<path>.*), /$\{path}
            if ',' not in rule:
                continue
            
            parts = [p.strip() for p in rule.split(',', 1)]
            if len(parts) != 2:
                continue
            
            pattern = parts[0]
            replacement = parts[1]
            
            # Remove "RewritePath=" prefix if present
            if pattern.startswith('RewritePath='):
                pattern = pattern[12:]
            
            try:
                # Convert pattern to regex
                # Pattern like /auth/(?<path>.*) becomes /auth/(.*)
                regex_pattern = re.sub(r'\(\?<\w+>', '(', pattern)
                regex_pattern = regex_pattern.replace('$\{path}', '\g<1>')
                regex_pattern = replacement.replace('$\{path}', '\g<1>')
                
                # Apply regex replacement
                rewritten_path = re.sub(pattern.replace('(?<path>', '(').replace(')', ')'), 
                                       regex_pattern, rewritten_path)
            except Exception:
                continue
        
        return rewritten_path
    
    @staticmethod
    def rewrite_path_simple(
        original_path: str,
        pattern: str,
        replacement: str
    ) -> str:
        """
        Simple path rewriting using regex
        
        Args:
            original_path: Original path
            pattern: Regex pattern
            replacement: Replacement string
            
        Returns:
            Rewritten path
        """
        try:
            return re.sub(pattern, replacement, original_path)
        except Exception:
            return original_path


class RouterMatcher:
    """Match requests to routes based on predicates"""
    
    @staticmethod
    def matches_path_predicate(request_path: str, path_pattern: str) -> bool:
        """
        Check if request path matches the path pattern
        
        Args:
            request_path: Request path from URL
            path_pattern: Path pattern from configuration
                         Examples: /auth/**, /user/**, /api/**, /entity/**
            
        Returns:
            True if matches
        """
        # Convert Spring path pattern to regex
        # /auth/** -> ^/auth/.*
        # /entity/**,/entityID/** -> multiple patterns
        
        patterns = [p.strip() for p in path_pattern.split(',')]
        
        for pattern in patterns:
            if RouterMatcher._match_single_pattern(request_path, pattern):
                return True
        
        return False
    
    @staticmethod
    def _match_single_pattern(request_path: str, pattern: str) -> bool:
        """Match single pattern"""
        # Exact match
        if '**' not in pattern and '*' not in pattern:
            return request_path == pattern or request_path.startswith(pattern + '/')
        
        # Convert Spring pattern to regex
        regex_pattern = pattern.replace('.', r'\.').replace('**', '.*').replace('*', '[^/]*')
        regex_pattern = f"^{regex_pattern}$"
        
        try:
            return re.match(regex_pattern, request_path) is not None
        except Exception:
            return False
    
    @staticmethod
    def find_matching_route(
        request_path: str,
        routes: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Find matching route for request
        
        Args:
            request_path: Request path
            routes: List of route configurations
            
        Returns:
            Matching route or None
        """
        for route in routes:
            predicates = route.get('predicates', [])
            
            for predicate in predicates:
                if isinstance(predicate, dict):
                    path_pattern = predicate.get('Path', '')
                elif isinstance(predicate, str):
                    # Format: Path=/path/**
                    if predicate.startswith('Path='):
                        path_pattern = predicate[5:]
                    else:
                        continue
                else:
                    continue
                
                if RouterMatcher.matches_path_predicate(request_path, path_pattern):
                    return route
        
        return None


class ProxyClient:
    """HTTP client for proxying requests to backend services"""
    
    @staticmethod
    async def forward_request(
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[bytes] = None,
        timeout: float = 30.0
    ) -> Tuple[int, Dict[str, str], bytes]:
        """
        Forward request to backend service
        
        Args:
            method: HTTP method
            url: Target URL
            headers: Request headers
            body: Request body
            timeout: Request timeout
            
        Returns:
            Tuple of (status_code, response_headers, response_body)
        """
        try:
            # Whitelist of safe headers for backend services
            SAFE_HEADERS = {
                'authorization',
                'content-type',
                'content-length',
                'accept',
                'accept-encoding',
                'accept-language',
                'user-agent',
                'x-forwarded-for',
                'x-forwarded-proto',
                'x-forwarded-host',
                'x-real-ip',
                'x-request-id',
                'x-correlation-id',
                'x-tenant-id',
                'x-user-id',
                'origin',
                'referer',
                'cache-control',
            }
            
            # Filter headers using whitelist approach
            headers_copy = {}
            for k, v in headers.items():
                # Skip null/empty values
                if v is None or (isinstance(v, str) and v.strip() == ''):
                    continue
                
                # Skip host header - HTTP client will set it
                if k.lower() == 'host':
                    continue
                
                # Only include whitelisted headers
                if k.lower() in SAFE_HEADERS:
                    headers_copy[k] = v
            
            # SSL verification: disable for internal services (both HTTP and HTTPS)
            verify_ssl = False
            
            logger.debug(f"Forwarding {method} {url} with headers: {list(headers_copy.keys())}")
            
            async with httpx.AsyncClient(verify=verify_ssl, timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers_copy,
                    content=body
                )
                
                logger.debug(f"Response status: {response.status_code}")
                return response.status_code, dict(response.headers), response.content
        except Exception as e:
            # Log detailed error for debugging
            logger.error(f"ProxyClient error forwarding to {url}: {type(e).__name__}: {str(e)}", exc_info=True)
            # Return error response
            return 502, {'content-type': 'application/json'}, b'{"error": "Bad Gateway"}'


class HeaderProcessor:
    """Process and clean response headers"""
    
    @staticmethod
    def dedupe_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """
        Remove duplicate CORS headers
        
        Args:
            headers: Response headers dict
            
        Returns:
            Cleaned headers dict
        """
        # Keycloak-specific headers to dedupe
        dedupe_keys = [
            'access-control-allow-credentials',
            'access-control-allow-origin',
            'access-control-allow-methods',
            'access-control-allow-headers'
        ]
        
        cleaned = {}
        for key, value in headers.items():
            lower_key = key.lower()
            if lower_key in dedupe_keys:
                # Keep only if not already present
                if lower_key not in cleaned:
                    cleaned[key] = value
            else:
                cleaned[key] = value
        
        return cleaned
    
    @staticmethod
    def add_token_relay_header(
        headers: Dict[str, str],
        access_token: str
    ) -> Dict[str, str]:
        """
        Add Bearer token to Authorization header
        
        Args:
            headers: Original headers dict
            access_token: Access token value
            
        Returns:
            Headers with Authorization header
        """
        headers_copy = dict(headers)
        headers_copy['authorization'] = f"Bearer {access_token}"
        return headers_copy
    
    @staticmethod
    def remove_sensitive_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """
        Remove sensitive headers from response
        
        Args:
            headers: Response headers dict
            
        Returns:
            Cleaned headers dict
        """
        sensitive = ['cookie', 'set-cookie', 'authorization', 'x-csrf-token']
        
        return {
            k: v for k, v in headers.items()
            if k.lower() not in sensitive
        }
