"""Article model for storing collected articles."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Float, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from web.database import Base


class Article(Base):
    """Represents a collected article."""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(Text, nullable=False)
    url = Column(Text, unique=True, nullable=False, index=True)
    source = Column(String(255), nullable=True)
    category = Column(String(100), nullable=True, index=True)
    summary = Column(Text, nullable=True)  # Original RSS summary
    ai_summary = Column(Text, nullable=True)  # Claude-generated summary
    score = Column(Float, default=0.0)
    viral_score = Column(Float, nullable=True)

    # AI evaluation scores
    ai_score = Column(Float, nullable=True, index=True)          # AI 종합 점수 (0-10)
    linkedin_potential = Column(Float, nullable=True)              # LinkedIn 잠재력 (0-10)
    eval_data = Column(Text, nullable=True)                        # 전체 평가 JSON
    published_at = Column(DateTime, nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Foreign keys
    collection_id = Column(Integer, ForeignKey("collections.id"), nullable=True)

    # Notion integration
    notion_page_id = Column(String(255), nullable=True)

    # LinkedIn status
    linkedin_status = Column(String(50), default="none")  # none, generated, posted

    # Read/Favorite status
    is_read = Column(Boolean, default=False, index=True)
    is_favorite = Column(Boolean, default=False, index=True)
    read_at = Column(DateTime, nullable=True)

    # Relationships
    collection = relationship("Collection", back_populates="articles")
    linkedin_drafts = relationship("LinkedInDraft", back_populates="article", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Article {self.id}: {self.title[:50]}...>"

    @property
    def latest_draft(self):
        """Get the most recent LinkedIn draft."""
        if self.linkedin_drafts:
            return max(self.linkedin_drafts, key=lambda d: d.created_at)
        return None

    def to_dict(self, include_drafts: bool = False) -> dict:
        """Convert to dictionary for API responses."""
        result = {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "category": self.category,
            "summary": self.summary,
            "ai_summary": self.ai_summary,
            "score": self.score,
            "viral_score": self.viral_score,
            "ai_score": self.ai_score,
            "linkedin_potential": self.linkedin_potential,
            "eval_data": self.eval_data,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "collection_id": self.collection_id,
            "notion_page_id": self.notion_page_id,
            "linkedin_status": self.linkedin_status,
            "is_read": self.is_read,
            "is_favorite": self.is_favorite,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }

        if include_drafts:
            result["linkedin_drafts"] = [d.to_dict() for d in self.linkedin_drafts]
            result["latest_draft"] = self.latest_draft.to_dict() if self.latest_draft else None

        return result
