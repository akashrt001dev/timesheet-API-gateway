"""
Test configuration and fixtures
"""
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client():
    """Create test client"""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_token():
    """Sample JWT token (base64 encoded)"""
    # This is a mock JWT token for testing
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyMTIzIiwicHJlZmVycmVkX3VzZXJuYW1lIjoidGVzdHVzZXIiLCJlbWFpbCI6InRlc3RAdGltZXNtYXJ0LmlvIiwicmVhbG1fYWNjZXNzIjp7InJvbGVzIjpbImFkbWluIiwidXNlciJdfSwiaXNzIjoiaHR0cHM6Ly9pZG0udGltZXNtYXJ0LmlvL3JlYWxtcy90aW1lc21hcnQtbWFzdGVyIiwiYXVkIjoic3ByaW5nLWFkZG9ucy1jb25maWRlbnRpYWwiLCJleHAiOjk5OTk5OTk5OTksImlhdCI6MTYwNDk2MDAwMH0.mock"
