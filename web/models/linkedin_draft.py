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

    # Agent 모드 관련
    generation_mode = Column(String(20), default="simple")  # "simple" | "agent"
    analysis = Column(Text, nullable=True)          # 기사 분석 결과
    direction = Column(Text, nullable=True)         # 선택된 방향
    review_notes = Column(Text, nullable=True)      # 자기 검토 노트
    evaluation = Column(Text, nullable=True)        # 가이드라인 평가 JSON
    user_feedback = Column(Text, nullable=True)     # 사용자 피드백 JSON
    iteration_count = Column(Integer, default=1)    # 검토 반복 횟수
    chat_history = Column(Text, nullable=True)      # JSON: [{role, content, timestamp}]
    guidelines_checklist = Column(Text, nullable=True)  # 가이드라인 체크리스트 (agent 모드)

    # 포스팅 상태 관련
    status = Column(String(20), default="draft")    # "draft" | "final" | "published"
    linkedin_url = Column(Text, nullable=True)      # 실제 포스팅 URL
    published_at = Column(DateTime, nullable=True)  # 포스팅 일시

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
            "generation_mode": self.generation_mode or "simple",
            "analysis": self.analysis,
            "direction": self.direction,
            "review_notes": self.review_notes,
            "evaluation": self.evaluation,
            "user_feedback": self.user_feedback,
            "iteration_count": self.iteration_count or 1,
            "chat_history": self.chat_history,
            "guidelines_checklist": self.guidelines_checklist,
            "status": self.status or "draft",
            "linkedin_url": self.linkedin_url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
        }
