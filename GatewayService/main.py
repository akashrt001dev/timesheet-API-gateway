"""
Application entry point
"""
from app.main import app

# This allows the app to be run with: uvicorn main:app --reload
if __name__ == "__main__":
    import uvicorn
    from app.config import config
    
    port = config.get_server_port()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
