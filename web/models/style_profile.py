"""Style profile model for storing dynamic writing style analysis."""

import json
from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, Text

from web.database import Base


class StyleProfile(Base):
    """Aggregated writing style profile built from reference posts and approved drafts."""

    __tablename__ = "style_profiles"

    id = Column(Integer, primary_key=True, index=True)
    profile_data = Column(Text, nullable=False)      # JSON: 통합 스타일 분석
    version = Column(Integer, default=1)
    source_post_count = Column(Integer, default=0)   # 기여 포스트 수
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<StyleProfile v{self.version}: {self.source_post_count} posts>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        try:
            profile = json.loads(self.profile_data) if self.profile_data else {}
        except json.JSONDecodeError:
            profile = {}

        return {
            "id": self.id,
            "profile_data": profile,
            "version": self.version,
            "source_post_count": self.source_post_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
