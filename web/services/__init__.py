"""Service layer for web application."""

from web.services.digest_service import DigestService
from web.services.linkedin_service import LinkedInService

__all__ = ["DigestService", "LinkedInService"]
