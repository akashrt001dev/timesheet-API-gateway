"""
Tests for gateway endpoints
"""
import pytest
from fastapi.testclient import TestClient


def test_root_redirect(client: TestClient):
    """Test root endpoint redirects to OAuth2 authorization"""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/oauth2/authorization/" in response.headers["location"]


def test_login_options_unauthenticated(client: TestClient):
    """Test login options returns list when not authenticated"""
    response = client.get("/login-options")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "label" in data[0]
        assert "loginUri" in data[0]


def test_login_options_authenticated(client: TestClient, sample_token: str):
    """Test login options returns empty list when authenticated"""
    headers = {"Authorization": f"Bearer {sample_token}"}
    response = client.get("/login-options", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_me_unauthenticated(client: TestClient):
    """Test /me endpoint without authentication"""
    response = client.get("/me")
    assert response.status_code == 200
    data = response.json()
    assert data["subject"] == ""
    assert data["roles"] == []


def test_me_authenticated(client: TestClient, sample_token: str):
    """Test /me endpoint with valid token"""
    headers = {"Authorization": f"Bearer {sample_token}"}
    response = client.get("/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "subject" in data
    assert "issuer" in data
    assert "roles" in data


def test_logout_api(client: TestClient):
    """Test logout_api endpoint"""
    response = client.get("/logout_api")
    assert response.status_code == 204
    assert "location" in response.headers


def test_logout(client: TestClient):
    """Test logout endpoint"""
    response = client.put("/logout")
    assert response.status_code == 202
    data = response.json()
    assert "redirectURL" in data


def test_health_check(client: TestClient):
    """Test health endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"


def test_liveness_probe(client: TestClient):
    """Test liveness probe"""
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"


def test_readiness_probe(client: TestClient):
    """Test readiness probe"""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"
