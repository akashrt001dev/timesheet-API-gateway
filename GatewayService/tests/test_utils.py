"""
Tests for OAuth utilities
"""
import pytest
from app.utils import TokenProcessor, MultiTenantResolver


class TestTokenProcessor:
    """Tests for token processing utilities"""
    
    def test_extract_subdomain_with_three_parts(self):
        """Test subdomain extraction from hostname with 3 parts"""
        hostname = "tenant1.example.com"
        result = MultiTenantResolver.extract_subdomain(hostname, "master")
        assert result == "tenant1"
    
    def test_extract_subdomain_with_port(self):
        """Test subdomain extraction with port"""
        hostname = "tenant1.example.com:8000"
        result = MultiTenantResolver.extract_subdomain(hostname, "master")
        assert result == "tenant1"
    
    def test_extract_subdomain_fallback_to_master(self):
        """Test fallback to master entity"""
        hostname = "localhost"
        result = MultiTenantResolver.extract_subdomain(hostname, "master-entity")
        assert result == "master-entity"
    
    def test_get_oauth2_registration_id(self):
        """Test OAuth2 registration ID mapping"""
        result = MultiTenantResolver.get_oauth2_registration_id("tenant1")
        assert result == "tenant1"


class TestMultiTenantResolver:
    """Tests for multi-tenant resolver"""
    
    def test_extract_subdomain_two_parts(self):
        """Test with 2-part hostname"""
        hostname = "example.com"
        result = MultiTenantResolver.extract_subdomain(hostname, "master")
        assert result == "master"
    
    def test_extract_subdomain_four_parts(self):
        """Test with 4-part hostname"""
        hostname = "api.tenant.example.com"
        result = MultiTenantResolver.extract_subdomain(hostname, "master")
        assert result == "api"
