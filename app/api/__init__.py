"""HTTP adapters. Routes delegate to services."""

from app.api.files import router

__all__ = ["router"]
