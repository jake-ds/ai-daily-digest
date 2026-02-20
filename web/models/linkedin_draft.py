"""LinkedIn draft model for storing generated posts."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from web.database import Base


class LinkedInDraft(Base):
    """Represents a generated LinkedIn draft for an article."""

    __tablename__ = "linkedin_drafts"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False, index=True)
    scenario = Column(String(10), nullable=False)  # A, B, C, D, E
    draft_content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    article = relationship("Article", back_populates="linkedin_drafts")

    def __repr__(self):
        return f"<LinkedInDraft {self.id}: Article {self.article_id}, Scenario {self.scenario}, v{self.version}>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": self.id,
            "article_id": self.article_id,
            "scenario": self.scenario,
            "draft_content": self.draft_content,
            "version": self.version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
