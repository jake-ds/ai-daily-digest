"""Reference post model for storing LinkedIn post examples for guideline learning."""

import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text

from web.database import Base


class ReferencePost(Base):
    """Represents a reference LinkedIn post used for guideline learning."""

    __tablename__ = "reference_posts"

    id = Column(Integer, primary_key=True, index=True)
    content = Column(Text, nullable=False)          # 포스팅 전문
    author = Column(String(255), nullable=True)     # 작성자
    source_url = Column(Text, nullable=True)        # 원본 URL
    analysis = Column(Text, nullable=True)          # AI 분석 결과 JSON
    scenario = Column(String(10), nullable=True)    # 시나리오 (A-F)
    tags = Column(Text, nullable=True)              # JSON array: ["writing", "hook", "storytelling"]
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<ReferencePost {self.id}: {self.content[:50]}...>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "content": self.content,
            "author": self.author,
            "source_url": self.source_url,
            "analysis": self.analysis,
            "scenario": self.scenario,
            "tags": json.loads(self.tags) if self.tags else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
