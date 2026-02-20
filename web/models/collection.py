"""Collection model for tracking digest runs."""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship

from web.database import Base


# Progress stages with display names
PROGRESS_STAGES = {
    "starting": {"name": "시작 중", "icon": "🚀", "order": 0},
    "collecting_rss": {"name": "RSS 피드 수집", "icon": "📡", "order": 1},
    "collecting_hn": {"name": "Hacker News 수집", "icon": "🔶", "order": 2},
    "collecting_viral": {"name": "바이럴 콘텐츠 수집", "icon": "🔥", "order": 3},
    "deduplicating": {"name": "중복 제거", "icon": "🔄", "order": 4},
    "scoring": {"name": "점수 계산", "icon": "📊", "order": 5},
    "enriching": {"name": "arXiv 논문 보강", "icon": "📚", "order": 6},
    "summarizing": {"name": "AI 요약 생성", "icon": "✨", "order": 7},
    "storing": {"name": "데이터베이스 저장", "icon": "💾", "order": 8},
    "syncing_notion": {"name": "Notion 동기화", "icon": "📝", "order": 9},
    "completed": {"name": "완료", "icon": "✅", "order": 10},
    "failed": {"name": "실패", "icon": "❌", "order": -1},
}


class Collection(Base):
    """Represents a single collection run (news or viral)."""

    __tablename__ = "collections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)  # daily_digest, viral, news
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    article_count = Column(Integer, default=0)
    notion_page_url = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Progress tracking
    progress_stage = Column(String(50), default="starting")
    progress_detail = Column(Text, nullable=True)  # e.g., "45/50 articles"

    # Relationships
    articles = relationship("Article", back_populates="collection")

    def __repr__(self):
        return f"<Collection {self.id}: {self.name} ({self.type})>"

    @property
    def duration_seconds(self) -> Optional[int]:
        """Calculate collection duration in seconds."""
        if self.completed_at and self.collected_at:
            return int((self.completed_at - self.collected_at).total_seconds())
        return None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        stage_info = PROGRESS_STAGES.get(self.progress_stage, PROGRESS_STAGES["starting"])
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "article_count": self.article_count,
            "notion_page_url": self.notion_page_url,
            "error_message": self.error_message,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "progress_stage": self.progress_stage,
            "progress_detail": self.progress_detail,
            "progress_stage_name": stage_info["name"],
            "progress_stage_icon": stage_info["icon"],
            "progress_order": stage_info["order"],
        }
