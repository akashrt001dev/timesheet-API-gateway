# Quick Start Guide - FastAPI Gateway Service

Get the gateway service running in 5 minutes.

## 1. Prerequisites

- Python 3.11+ installed
- Git (optional, if cloning)
- ~500MB disk space

## 2. Setup (Choose Your OS)

### Windows
```bash
cd gateway-service-fastapi
setup.bat
```

### Linux / macOS
```bash
cd gateway-service-fastapi
chmod +x setup.sh
./setup.sh
```

### Manual Setup (All Platforms)
```bash
cd gateway-service-fastapi

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env
```

## 3. Start the Service

```bash
# Make sure virtual environment is active
# (should see (venv) in your terminal prompt)

# Option 1: Basic run
python main.py

# Option 2: Development with auto-reload
uvicorn app.main:app --reload --port 8000

# Option 3: Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 4. Verify It's Running

Open your browser or terminal:

```bash
# Health check
curl http://localhost:8000/health

# API documentation (interactive)
# Visit: http://localhost:8000/docs

# Alternative API docs
# Visit: http://localhost:8000/redoc
```

You should see:
- `health` returns `{"status": "UP"}`
- `docs` shows interactive Swagger UI
- `redoc` shows ReDoc documentation

## 5. Test Gateway Endpoints

```bash
# Get login options
curl http://localhost:8000/login-options

# Get user info (without token returns empty)
curl http://localhost:8000/me

# With a real OAuth2 token:
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8000/me
```

## 6. Docker Setup (Optional)

```bash
# Build image
docker build -t gateway-service:latest .

# Run container
docker run -p 8000:8000 gateway-service:latest

# Or with Docker Compose
docker-compose up
```

## 7. Configuration

Edit `config/application-qa.yml` to customize:
- Server port: `server.port`
- OAuth2 providers: `spring.security.oauth2.client.provider`
- Backend routes: `spring.cloud.gateway.routes`

No restart needed for some settings! Check ConfigManager for reload support.

## 8. Troubleshooting

### Issue: "Module not found"
```bash
# Make sure virtual environment is activated
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

### Issue: "Port 8000 already in use"
```bash
# Use a different port
uvicorn app.main:app --port 9000

# Or in .env:
SERVER_PORT=9000
```

### Issue: "Config file not found"
```bash
# Ensure you're in the gateway-service-fastapi directory
cd gateway-service-fastapi
ls config/application-qa.yml  # Should exist
```

### Issue: "Connection refused to Keycloak"
```bash
# Check application-qa.yml
# Verify Keycloak URLs are correct and accessible
# Check your network/firewall
```

## 9. Next Steps

### For Development
1. Read `README.md` for comprehensive documentation
2. Run tests: `pytest`
3. Check logs for debugging
4. Edit routes in `app/routes/gateway.py`

### For Deployment
1. Review `MIGRATION_GUIDE.md`
2. Deploy with Docker: `docker build -t my-gateway:v1 .`
3. Use Kubernetes manifests (see README)
4. Monitor with health endpoints

### For Integration
1. Configure backend services in `application-qa.yml`
2. Test routing: `curl http://localhost:8000/api/service-name/...`
3. Verify token relay is working
4. Check CORS headers for frontend access

## 10. Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Redirect to OAuth2 |
| `/login-options` | GET | List OAuth2 providers |
| `/me` | GET | Get user info |
| `/logout_api` | GET | Logout (header redirect) |
| `/logout` | PUT | Logout (JSON response) |
| `/health` | GET | Health check |
| `/health/live` | GET | Kubernetes liveness |
| `/health/ready` | GET | Kubernetes readiness |
| `/docs` | GET | Swagger UI docs |
| `/redoc` | GET | ReDoc docs |

## 11. Useful Commands

```bash
# List running services
curl http://localhost:8000/docs

# View logs in real-time
tail -f logs/app.log

# Run tests
pytest

# Run tests with coverage
pytest --cov=app

# Format code (install black first)
pip install black
black app/

# Check code style (install flake8)
pip install flake8
flake8 app/

# Check types (install mypy)
pip install mypy
mypy app/

# View installed packages
pip list

# Freeze dependencies to file
pip freeze > current-requirements.txt
```

## 12. Project Structure Overview

```
gateway-service-fastapi/
├── app/                    # Main application code
│   ├── config/             # Configuration management
│   ├── routes/             # API endpoints
│   ├── models/             # Data models (Pydantic)
│   ├── utils/              # Helper utilities
│   ├── middleware/         # Request/response middleware
│   └── main.py             # FastAPI app setup
├── config/                 # Configuration files
│   └── application-qa.yml  # QA environment config
├── tests/                  # Unit tests
├── main.py                 # Entry point
├── requirements.txt        # Python dependencies
├── Dockerfile              # Docker build file
├── README.md               # Full documentation
└── setup.sh/setup.bat      # Setup scripts
```

## 13. Performance Tips

```bash
# Production deployment with 4 workers
uvicorn app.main:app --workers 4 --host 0.0.0.0 --port 8000

# With proper logging
LOG_LEVEL=INFO uvicorn app.main:app --host 0.0.0.0

# With uvicorn worker process manager
gunicorn app.main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker

# Monitor performance
# Check /health endpoint regularly
# Monitor memory: watch free -h
# Monitor CPU: watch top -p $(pgrep -f uvicorn)
```

## 14. Getting Help

1. **API Documentation**: Visit http://localhost:8000/docs
2. **README.md**: Comprehensive guide with all features
3. **MIGRATION_GUIDE.md**: Spring Boot → FastAPI mapping
4. **IMPLEMENTATION_SUMMARY.md**: What was migrated
5. **Logs**: Check console output or log files

## 15. Common Workflows

### Adding a New Route
```python
# In app/routes/gateway.py
@router.get("/custom-endpoint")
async def custom_endpoint(request: Request) -> dict:
    return {"message": "Hello"}
```

### Modifying Configuration
```yaml
# In config/application-qa.yml
server:
  port: 9000  # Change port

# Restart application
```

### Adding OAuth2 Provider
```yaml
# In config/application-qa.yml under spring.security.oauth2.client.provider
keycloak-new-tenant:
  issuer-uri: https://idm.example.com/realms/new-tenant
```

### Testing an Endpoint
```bash
# Simple GET
curl http://localhost:8000/health

# With headers
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/me

# POST with data
curl -X POST http://localhost:8000/endpoint \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

---

**You're all set!** 🎉

For more details, see `README.md` and `MIGRATION_GUIDE.md`
