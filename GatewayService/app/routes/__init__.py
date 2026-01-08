"""
Routes package initialization
"""
from app.routes.gateway import router as gateway_router
from app.routes.proxy import router as proxy_router

__all__ = ['gateway_router', 'proxy_router']
