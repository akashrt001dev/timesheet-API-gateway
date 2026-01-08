# FastAPI Gateway Service (BFF)

A high-performance, FastAPI-based Backend For Frontend (BFF) gateway service that provides OAuth2/OIDC authentication, API routing, multi-tenant support, and request forwarding to microservices.

This is a Python/FastAPI migration of the original Spring Boot gateway-service.

## Features

- **OAuth2/OIDC Authentication** - Full OpenID Connect support with Keycloak integration
- **Multi-tenant Support** - Subdomain-based tenant routing and OAuth2 provider selection
- **API Gateway** - Smart routing to backend microservices based on path predicates
- **Token Relay** - Automatic Bearer token forwarding to backend services
- **Path Rewriting** - URL path transformation before forwarding requests
- **CORS Support** - Comprehensive CORS header handling
- **Async/Reactive** - Built on FastAPI with async/await for high performance
- **Health Checks** - Kubernetes-ready liveness and readiness probes
- **Request Logging** - Detailed request/response logging
- **Configuration Management** - YAML-based configuration from `application-qa.yml`

## Project Structure

```
gateway-service-fastapi/
├── app/
│   ├── __init__.py              # Package initialization
│   ├── main.py                  # FastAPI app setup and configuration
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py          # Configuration manager (loads YAML)
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py           # Pydantic models for request/response
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── gateway.py           # Main gateway endpoints (/, /login-options, /me, /logout)
│   │   └── proxy.py             # API proxy routes to backend services
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── oauth.py             # OAuth2/JWT token processing
│   │   └── routing.py           # Path rewriting, routing, HTTP proxy
│   └── middleware/
│       └── __init__.py          # Request/response middleware
├── config/
│   └── application-qa.yml       # Configuration file (QA environment)
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Docker image configuration
├── docker-compose.yml           # Docker Compose setup
├── .env.example                 # Environment variables template
└── README.md                    # This file
```

## Installation

### Prerequisites

- Python 3.11+
- pip or Poetry
- Keycloak (for OAuth2/OIDC)
- Backend microservices (or Eureka service discovery)

### Local Development

1. **Clone and navigate to the project:**
   ```bash
   cd gateway-service-fastapi
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create environment file:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Run the application:**
   ```bash
   python main.py
   # Or with auto-reload:
   uvicorn app.main:app --reload --port 8000
   ```

6. **Access the application:**
   - API Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc
   - Health Check: http://localhost:8000/health

## Docker Setup

### Build and Run with Docker

```bash
# Build image
docker build -t gateway-service:latest .

# Run container
docker run -p 8000:8000 \
  -v $(pwd)/config:/app/config \
  gateway-service:latest
```

### Docker Compose

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f gateway-service

# Stop services
docker-compose down
```

## Configuration

Configuration is loaded from `config/application-qa.yml`. This file contains:

- **OAuth2 Providers** - Keycloak realms and issuer URIs
- **OAuth2 Registrations** - Client credentials and authorization settings
- **Gateway Routes** - Service routing rules with path predicates
- **Server Settings** - Port, SSL, and other server config
- **Application Settings** - Master entity name, timezones, etc.

### Key Configuration Sections

```yaml
# Server configuration
server:
  port: 8000
  ssl:
    enabled: false

# OAuth2 Providers (Keycloak realms)
spring:
  security:
    oauth2:
      client:
        provider:
          keycloak-timesmart-master:
            issuer-uri: https://idm.timesmart.io/realms/timesmart-master

# OAuth2 Client Registration
        registration:
          timesmart-master:
            client-id: spring-addons-confidential
            client-secret: <secret>
            scope: openid,profile,email,offline_access,roles

# Gateway Routes
  cloud:
    gateway:
      routes:
      - id: user-management-service
        uri: lb://user-management-service
        predicates:
          - Path=/auth/**, /user/**
```

## API Endpoints

### Gateway Endpoints

#### `GET /`
Redirect to OAuth2 authorization based on subdomain

**Response:**
- Redirect (302) to `/oauth2/authorization/{subdomain}`

---

#### `GET /login-options`
Get available login providers

**Response:**
```json
[
  {
    "label": "keycloak",
    "loginUri": "https://app.timesmart.io/oauth2/authorization/timesmart-master"
  }
]
```

---

#### `GET /me`
Get current user information

**Headers:**
- `Authorization: Bearer <token>`

**Response:**
```json
{
  "subject": "user123",
  "issuer": "https://idm.timesmart.io/realms/timesmart-master",
  "roles": ["admin", "user"]
}
```

---

#### `GET /logout_api`
Logout and return redirect URI in Location header

**Response:**
- 204 No Content with Location header pointing to Keycloak logout

---

#### `PUT /logout`
Logout and return redirect URI in JSON body

**Response:**
```json
{
  "redirectURL": "https://idm.timesmart.io/realms/timesmart-master/protocol/openid-connect/logout?..."
}
```

---

#### `GET /health`
Service health check

**Response:**
```json
{
  "status": "UP",
  "timestamp": "2024-01-08T10:30:00",
  "service": "gateway-service"
}
```

---

#### `GET /health/live`
Kubernetes liveness probe

---

#### `GET /health/ready`
Kubernetes readiness probe

---

### Proxy Endpoints

All other routes are automatically routed to backend services based on path predicates in the configuration.

#### Examples:
- `GET /auth/users` → routes to `user-management-service`
- `GET /user/profile` → routes to `user-management-service`
- `GET /contracts/list` → routes to `contract-managment-service`
- `GET /entity/details` → routes to `entity-service`
- `GET /timesheet/entries` → routes to `timesheet-management-service`
- `POST /api/user-management-service/**` → routes to `user-management-service`

## Multi-tenant Support

The gateway extracts the subdomain from the request hostname and maps it to the appropriate OAuth2 provider:

```
Request: https://tenant1.timesmart.io/
Subdomain extracted: tenant1
OAuth2 registration: tenant1
Redirect to: https://tenant1.timesmart.io/oauth2/authorization/tenant1
```

If no subdomain is found, uses the master entity name from configuration.

## OAuth2/OIDC Flow

1. **Root Request**
   ```
   GET https://tenant1.timesmart.io/
   ```
   ↓ Redirects to Keycloak

2. **Authorization**
   ```
   GET https://tenant1.timesmart.io/oauth2/authorization/tenant1
   ```
   ↓ Redirects to Keycloak login

3. **Callback**
   ```
   GET https://tenant1.timesmart.io/login/oauth2/code/tenant1?code=...
   ```
   ↓ Exchanges code for token

4. **Session Created**
   Bearer token stored in session/cookie

5. **API Access**
   ```
   GET https://tenant1.timesmart.io/user/profile
   Header: Authorization: Bearer <token>
   ```
   ↓ Proxied to backend with token

## Token Processing

The gateway extracts and processes JWT tokens:

- **Token Decoding** - Parses JWT payload without verification
- **Claims Extraction** - Extracts user subject, issuer, and roles
- **Role Mapping** - Collects roles from `realm_access` and `resource_access`
- **Token Relay** - Forwards Bearer token to backend services

## Path Rewriting

Routes can include path rewriting rules to transform URLs before forwarding:

```yaml
routes:
  - id: user-management-service
    uri: lb://user-management-service
    filters:
      - RewritePath=/auth/(?<path>.*), /$\{path}
      - RewritePath=/user/(?<path>.*), /$\{path}
```

Examples:
- `/auth/users` → `/users`
- `/user/profile` → `/profile`

## Middleware Stack

The middleware is applied in the following order:

1. **SessionMiddleware** - Session context management
2. **RequestLoggingMiddleware** - Request/response logging
3. **TokenRelayMiddleware** - Bearer token extraction
4. **DedupeResponseHeaderMiddleware** - Remove duplicate CORS headers
5. **CORSMiddleware** - Standard CORS handling
6. **CORSHeaderMiddleware** - Custom CORS headers

## Logging

Logs are output to stdout with the following format:

```
2024-01-08 10:30:00,123 - app.routes.gateway - INFO - Redirecting root request to: https://app.timesmart.io/oauth2/authorization/timesmart-master
```

Configure logging level via environment:
```bash
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

## Testing

Run tests with pytest:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app

# Run specific test file
pytest tests/test_gateway.py

# Run with verbose output
pytest -v
```

## Performance Considerations

- **Async/Await** - All I/O operations are non-blocking
- **Connection Pooling** - httpx maintains connection pools
- **Token Caching** - Tokens are extracted on-demand (implement caching for production)
- **Middleware Ordering** - Optimized for minimal overhead

## Security

- **CORS** - Configurable per environment
- **HTTPS** - Enabled in production (via reverse proxy)
- **Token Validation** - OAuth2 tokens validated by Keycloak
- **Header Filtering** - Sensitive headers removed from responses
- **Input Validation** - Pydantic models validate all inputs

## Troubleshooting

### Issue: "No matching route"
- Check path predicates in `application-qa.yml`
- Verify service is running and discoverable
- Check path rewriting rules

### Issue: "Authorization header missing"
- Ensure Bearer token is included in request
- Check token validity and expiration
- Verify OAuth2 session is established

### Issue: CORS errors
- Check CORS middleware configuration
- Verify `Access-Control-Allow-Origin` header
- Check preflight OPTIONS requests

### Issue: Backend service not found
- Verify Eureka service discovery is running
- Check service name matches configuration
- Verify network connectivity between services

## Deployment

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gateway-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: gateway-service
  template:
    metadata:
      labels:
        app: gateway-service
    spec:
      containers:
      - name: gateway
        image: gateway-service:latest
        ports:
        - containerPort: 8000
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests
4. Run tests and linting
5. Submit a pull request

## License

Proprietary - TimeSmart AI

## Support

For issues or questions, contact the development team.
