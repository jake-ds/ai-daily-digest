"""API routers."""

from web.api.digest import router as digest_router
from web.api.articles import router as articles_router
from web.api.linkedin import router as linkedin_router
from web.api.settings import router as settings_router

__all__ = ["digest_router", "articles_router", "linkedin_router", "settings_router"]
