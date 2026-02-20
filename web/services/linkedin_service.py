"""LinkedIn service with Jake's guidelines for post generation."""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from anthropic import Anthropic
from sqlalchemy.orm import Session

from web.models import Article, LinkedInDraft
from web.config import ANTHROPIC_API_KEY, LINKEDIN_GUIDELINES_PATH


# Jake's LinkedIn Post Scenarios
SCENARIOS = {
    "A": {
        "name": "산업 분석 + 프레임워크",
        "description": "충격적 숫자로 시작, 현상 분석 후 프레임워크 추출",
        "hook_style": "충격적 숫자 + 방향성 제시",
        "structure": "현상 나열 → 프레임워크 추출 → 시사점 확장",
        "closing": "본인 경험 연결 또는 선언",
    },
    "B": {
        "name": "제품/도구 리뷰 + 실사용",
        "description": "신제품 출시 팩트로 시작, 직접 사용 경험 공유",
        "hook_style": "출시 팩트 + 임팩트",
        "structure": "제품 설명 → 직접 사용 경험 → 왜 중요한지",
        "closing": "가벼운 행동 선언",
    },
    "C": {
        "name": "개인 실천 + 회고",
        "description": "의외성 있는 행동 선언으로 시작, 인사이트 도출",
        "hook_style": "의외성 또는 행동 선언",
        "structure": "맥락 → 행동 상세 → 인사이트 추출",
        "closing": "자기 고백 또는 결심",
    },
    "D": {
        "name": "시장 시그널 읽기",
        "description": "메타 관찰로 시작, 패턴과 시그널 분석",
        "hook_style": "메타 관찰 또는 시간축 대비",
        "structure": "시간축 나열 → 패턴 추출 → 시그널 분석",
        "closing": "변하지 않는 원칙",
    },
    "E": {
        "name": "전략적 의사결정 공유",
        "description": "역설적 결정 선언으로 시작, 논리적 근거 전개",
        "hook_style": "결정 선언 + 역설",
        "structure": "기존 포지션 → 변화 시그널 → 의사결정 논리",
        "closing": "최종 결정 + 원칙",
    },
}


class LinkedInService:
    """Service for generating LinkedIn posts using Jake's guidelines."""

    def __init__(self, db: Session):
        self.db = db
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.guidelines = self._load_guidelines()

    def _load_guidelines(self) -> str:
        """Load LinkedIn guidelines from file."""
        try:
            return LINKEDIN_GUIDELINES_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def detect_scenario(self, article: Article) -> str:
        """Detect the best scenario for an article."""
        title = article.title.lower()
        summary = (article.ai_summary or article.summary or "").lower()
        content = f"{title} {summary}"

        # Scenario detection heuristics
        if any(kw in content for kw in ["출시", "release", "launch", "announced", "공개"]):
            return "B"  # Product review

        if any(kw in content for kw in ["연구", "paper", "research", "study", "논문"]):
            return "A"  # Industry analysis

        if any(kw in content for kw in ["결정", "decision", "선택", "chose", "pivot"]):
            return "E"  # Strategic decision

        if any(kw in content for kw in ["트렌드", "trend", "시장", "market", "signal"]):
            return "D"  # Market signal

        if any(kw in content for kw in ["경험", "experience", "learned", "배운"]):
            return "C"  # Personal practice

        # Default based on category
        category_map = {
            "bigtech": "B",
            "research": "A",
            "vc": "D",
            "viral": "D",
            "news": "A",
        }
        return category_map.get(article.category, "A")

    def generate_draft(
        self,
        article: Article,
        scenario: Optional[str] = None,
    ) -> LinkedInDraft:
        """
        Generate a LinkedIn draft for an article.

        Args:
            article: Article to generate draft for
            scenario: Scenario (A-E), auto-detected if not provided

        Returns:
            LinkedInDraft record
        """
        if scenario is None:
            scenario = self.detect_scenario(article)

        scenario_info = SCENARIOS.get(scenario, SCENARIOS["A"])

        # Build the prompt
        prompt = self._build_prompt(article, scenario, scenario_info)

        # Generate with Claude
        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        draft_content = response.content[0].text

        # Get next version number
        existing_drafts = (
            self.db.query(LinkedInDraft)
            .filter(LinkedInDraft.article_id == article.id)
            .count()
        )
        version = existing_drafts + 1

        # Create draft record
        draft = LinkedInDraft(
            article_id=article.id,
            scenario=scenario,
            draft_content=draft_content,
            version=version,
        )
        self.db.add(draft)

        # Update article status
        article.linkedin_status = "generated"
        self.db.commit()
        self.db.refresh(draft)

        return draft

    def regenerate_draft(self, draft_id: int) -> LinkedInDraft:
        """Regenerate a draft with the same scenario."""
        existing_draft = self.db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
        if not existing_draft:
            raise ValueError(f"Draft {draft_id} not found")

        article = existing_draft.article
        return self.generate_draft(article, scenario=existing_draft.scenario)

    def get_drafts_for_article(self, article_id: int) -> List[LinkedInDraft]:
        """Get all drafts for an article."""
        return (
            self.db.query(LinkedInDraft)
            .filter(LinkedInDraft.article_id == article_id)
            .order_by(LinkedInDraft.version.desc())
            .all()
        )

    def _build_prompt(self, article: Article, scenario: str, scenario_info: dict) -> str:
        """Build the generation prompt with Jake's guidelines."""
        return f"""당신은 LinkedIn 포스팅 전문가입니다. 다음 기사를 바탕으로 LinkedIn 포스트를 작성해주세요.

## 페르소나
- VC 심사역 + ML 엔지니어 출신 AI 빌더
- 최신 AI 기술과 시장 동향에 깊은 이해
- 실무 경험을 바탕으로 인사이트 공유

## 시나리오 {scenario}: {scenario_info['name']}
- 설명: {scenario_info['description']}
- 훅 스타일: {scenario_info['hook_style']}
- 본문 구조: {scenario_info['structure']}
- 마무리: {scenario_info['closing']}

## 기사 정보
- 제목: {article.title}
- 출처: {article.source}
- URL: {article.url}
- 요약: {article.ai_summary or article.summary or "없음"}

## 공통 규칙

### 문체
- 기본: 하십시오체 ("~입니다", "~했습니다")
- 리듬 전환시: 해요체로 변화 ("~해요", "~네요")
- 자연스러운 톤 유지

### 금지 사항
- 조언톤 금지 ("~하세요", "~해보세요" 대신 "저는 ~합니다")
- 공포 마케팅 금지 ("지금 안 하면 뒤처집니다" 금지)
- 이모지 금지
- "여러분" 호칭 금지
- "혁명", "패러다임 시프트" 등 과장 표현 금지

### 구조
1. 훅 (1-2문장): {scenario_info['hook_style']}
2. 본문: {scenario_info['structure']}
3. 마무리: {scenario_info['closing']}

### 길이
- 1200~1800자 사이
- 단락 구분 명확히

## 출력 형식
LinkedIn 포스트 본문만 출력하세요. 설명이나 주석 없이 바로 사용 가능한 형태로 작성해주세요.
마지막에 원문 링크를 포함하세요: {article.url}
"""

    def get_scenarios(self) -> dict:
        """Get all available scenarios."""
        return SCENARIOS
