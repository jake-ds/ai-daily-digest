"""LinkedIn service with Jake's guidelines for post generation."""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from anthropic import Anthropic
from sqlalchemy.orm import Session

from web.models import Article, LinkedInDraft, ReferencePost
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
    "F": {
        "name": "권위자 관점 + 역설적 인사이트",
        "description": "독자 고민 공감 후 권위자의 반대 관점을 제시하여 인사이트 전달",
        "hook_style": "공감형 + 반전: 독자 고민 공감 → 권위자의 반대 관점 제시",
        "structure": "권위자 소개 + 핵심 관점 → 3개 핵심 포인트 논증 (넘버링) → 구체적 인용구와 메타포 → 실행 가능한 가이드",
        "closing": "격려형 + 리프레이밍",
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

    # 시나리오 감지 결과 캐시 (article_id -> {scenario, confidence, reason})
    _scenario_cache: dict = {}

    def detect_scenario(self, article: Article) -> str:
        """Detect the best scenario for an article (returns scenario letter only)."""
        result = self.detect_scenario_detailed(article)
        return result["scenario"]

    def detect_scenario_detailed(self, article: Article) -> dict:
        """Detect the best scenario using Claude API, with keyword fallback.

        Returns:
            dict: {scenario: str, confidence: float, reason: str}
        """
        # 캐시 확인
        if article.id in self._scenario_cache:
            return self._scenario_cache[article.id]

        # Claude API 기반 분석 시도
        try:
            result = self._detect_scenario_with_claude(article)
            self._scenario_cache[article.id] = result
            return result
        except Exception:
            # API 실패 시 키워드 기반 폴백
            scenario = self._detect_scenario_keyword(article)
            result = {"scenario": scenario, "confidence": 0.5, "reason": "키워드 기반 자동 감지 (AI 분석 실패)"}
            self._scenario_cache[article.id] = result
            return result

    def _detect_scenario_with_claude(self, article: Article) -> dict:
        """Use Claude API to analyze article and detect best scenario."""
        scenarios_desc = "\n".join(
            f"- {key}: {val['name']} - {val['description']}"
            for key, val in SCENARIOS.items()
        )

        prompt = f"""다음 기사에 가장 적합한 LinkedIn 포스팅 시나리오(A-F)를 분석해주세요.

## 기사
- 제목: {article.title}
- 출처: {article.source or '알 수 없음'}
- 요약: {article.ai_summary or article.summary or '없음'}

## 시나리오 목록
{scenarios_desc}

## 출력 형식 (JSON만 출력)
{{"scenario": "A", "confidence": 0.85, "reason": "이 기사가 해당 시나리오에 적합한 이유를 한 문장으로"}}"""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        json_start = raw.find("{")
        json_end = raw.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            data = json.loads(raw[json_start:json_end])
            scenario = data.get("scenario", "A")
            if scenario not in SCENARIOS:
                scenario = "A"
            return {
                "scenario": scenario,
                "confidence": float(data.get("confidence", 0.8)),
                "reason": data.get("reason", ""),
            }

        raise ValueError("Failed to parse Claude response")

    def _detect_scenario_keyword(self, article: Article) -> str:
        """Keyword-based scenario detection (fallback)."""
        title = article.title.lower()
        summary = (article.ai_summary or article.summary or "").lower()
        content = f"{title} {summary}"

        if any(kw in content for kw in ["출시", "release", "launch", "announced", "공개"]):
            return "B"
        if any(kw in content for kw in ["연구", "paper", "research", "study", "논문"]):
            return "A"
        if any(kw in content for kw in ["결정", "decision", "선택", "chose", "pivot"]):
            return "E"
        if any(kw in content for kw in ["트렌드", "trend", "시장", "market", "signal"]):
            return "D"
        if any(kw in content for kw in ["경험", "experience", "learned", "배운"]):
            return "C"
        if any(kw in content for kw in ["권위자", "expert", "통념", "학습", "fomo", "배워야", "역설", "misconception", "myth", "contrary"]):
            return "F"

        category_map = {
            "bigtech": "B",
            "research": "A",
            "vc": "D",
            "viral": "D",
            "news": "A",
        }
        return category_map.get(article.category, "A")

    # 금지어 목록
    FORBIDDEN_WORDS = [
        "여러분", "혁명", "패러다임 시프트", "게임체인저",
        "하세요", "해보세요", "읽어주셔서 감사",
    ]

    def _validate_draft(self, content: str, article_url: str) -> dict:
        """Validate a generated draft against quality rules."""
        issues = []
        char_count = len(content)

        # 1. 글자수 검증 (1200-1800)
        if char_count < 1200:
            issues.append(f"글자수 부족: {char_count}자 (최소 1200자 필요)")
        elif char_count > 1800:
            issues.append(f"글자수 초과: {char_count}자 (최대 1800자)")

        # 2. 금지어 체크
        for word in self.FORBIDDEN_WORDS:
            if word in content:
                issues.append(f"금지어 포함: '{word}'")

        # 이모지 체크
        import unicodedata
        for char in content:
            if unicodedata.category(char).startswith("So"):
                issues.append("이모지 포함됨")
                break

        # 3. 원문 링크 포함 여부
        if article_url and article_url not in content:
            issues.append("원문 링크가 포함되지 않음")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "char_count": char_count,
        }

    def generate_draft(
        self,
        article: Article,
        scenario: Optional[str] = None,
    ) -> LinkedInDraft:
        """
        Generate a LinkedIn draft for an article.

        Args:
            article: Article to generate draft for
            scenario: Scenario (A-F), auto-detected if not provided

        Returns:
            LinkedInDraft record
        """
        # 매 생성 시 지침서를 새로 로드 (hot-reload)
        self.guidelines = self._load_guidelines()

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

        # 품질 검증 및 자동 재생성 (최대 2회)
        max_retries = 2
        for attempt in range(max_retries):
            validation = self._validate_draft(draft_content, article.url)
            if validation["valid"]:
                break

            # 수정 프롬프트로 재생성
            issues_text = "\n".join(f"- {issue}" for issue in validation["issues"])
            fix_prompt = f"""다음 LinkedIn 포스트에 문제가 발견되었습니다. 아래 이슈를 수정해서 다시 작성해주세요.

## 현재 초안
{draft_content}

## 발견된 문제
{issues_text}

## 수정 요청
위 문제를 모두 수정하여 LinkedIn 포스트 본문만 다시 출력해주세요.
설명 없이 바로 사용 가능한 형태로 작성하세요.
마지막에 원문 링크를 포함하세요: {article.url}"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": fix_prompt}],
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

    def _get_reference_examples(self, scenario: str) -> str:
        """Get reference post examples for the given scenario."""
        examples = []

        # 1. DB에서 ReferencePost 최대 2개 가져오기
        ref_posts = (
            self.db.query(ReferencePost)
            .order_by(ReferencePost.created_at.desc())
            .limit(2)
            .all()
        )
        for post in ref_posts:
            examples.append(post.content)

        # 2. 지침서에서 해당 시나리오 예시 추출
        if self.guidelines:
            pattern = rf"### 시나리오 {scenario} 예시.*?```\n(.*?)```"
            match = re.search(pattern, self.guidelines, re.DOTALL)
            if match:
                examples.append(match.group(1).strip())

        if not examples:
            return ""

        examples_text = ""
        for i, ex in enumerate(examples, 1):
            examples_text += f"\n### 예시 {i}\n{ex}\n"

        return f"""## 참고 예시

다음은 좋은 포스팅 예시입니다. 이 스타일과 구조를 참고하세요:
{examples_text}"""

    def _build_article_context(self, article: Article) -> str:
        """Build enriched article context with metadata."""
        lines = [
            f"## 기사 정보",
            f"- 제목: {article.title}",
            f"- 출처: {article.source}",
            f"- URL: {article.url}",
            f"- 카테고리: {article.category or '미분류'}",
            f"- 요약: {article.ai_summary or article.summary or '없음'}",
        ]

        # Score 기반 톤 가이드
        if article.score and article.score >= 8:
            lines.append(f"- 품질 점수: {article.score}/10 (고품질 기사 → 깊은 분석과 구체적 인사이트를 포함하세요)")
        elif article.score and article.score <= 5:
            lines.append(f"- 품질 점수: {article.score}/10 (간결한 코멘터리와 핵심 포인트 위주로 작성하세요)")
        elif article.score:
            lines.append(f"- 품질 점수: {article.score}/10")

        # Viral score 맥락
        if article.viral_score and article.viral_score > 0:
            lines.append(f"- 바이럴 점수: {article.viral_score} (화제성 높은 뉴스 → 독자의 관심을 활용하되, 과장은 피하세요)")

        # Source 기반 맥락
        authority_sources = ["mit", "stanford", "google", "deepmind", "openai", "anthropic", "meta ai", "microsoft research"]
        if article.source and any(src in article.source.lower() for src in authority_sources):
            lines.append(f"- 출처 권위: {article.source}는 권위 있는 연구/기술 기관입니다. 연구 권위를 강조하세요.")

        return "\n".join(lines)

    def _build_prompt(self, article: Article, scenario: str, scenario_info: dict) -> str:
        """Build the generation prompt with Jake's guidelines."""
        # 기사 정보 섹션 (풍부한 맥락 포함)
        article_section = self._build_article_context(article)

        # 지침서가 있으면 전문 포함, 없으면 하드코딩된 규칙 사용
        if self.guidelines:
            rules_section = f"""## 작성 지침서 (반드시 준수)

아래는 LinkedIn 포스팅 작성 지침서 전문입니다. 이 지침을 철저히 따라주세요:

{self.guidelines}"""
        else:
            rules_section = f"""## 공통 규칙

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
- 단락 구분 명확히"""

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

{article_section}

{rules_section}
{self._get_reference_examples(scenario)}
## LinkedIn 포맷팅 규칙
- 줄바꿈으로 단락을 명확히 구분하세요
- 짧은 문장을 사용하세요 (한 문장에 2줄 이상 금지)
- 넘버링(1, 2, 3)을 활용하여 가독성을 높이세요
- 구분선(ㅡ)을 활용하여 시각적으로 정리하세요

## 길이 제약 (매우 중요)
반드시 1200자 이상 1800자 이하로 작성하세요.
이상적 길이는 1400-1600자입니다. 이 범위를 벗어나면 조절하세요.

## 출력 형식
- 제목/헤더 없이 본문만 출력하세요. 첫 줄이 곧 훅입니다.
- 설명이나 주석 없이 바로 사용 가능한 형태로 작성하세요.
- 마지막에 원문 링크 한 줄: {article.url}

## 다음과 같이 작성하지 마세요 (anti-pattern)
1. 너무 일반적인 서론 ("오늘은 ~에 대해...")
2. "~에 대해 이야기하겠습니다"
3. "결론적으로~"
4. "요약하면~"
"""

    def chat_refine_by_draft(self, draft_id: int, user_message: str) -> dict:
        """Refine draft via chat message using draft from DB (no session needed).

        Args:
            draft_id: LinkedInDraft ID
            user_message: User's chat message

        Returns:
            dict with revised_draft, char_count, chat_history, updated_content
        """
        import time as _time

        draft = self.db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
        if not draft:
            raise ValueError(f"Draft {draft_id} not found")

        current_content = draft.draft_content

        # 기존 채팅 이력 로드
        chat_messages = []
        if draft.chat_history:
            try:
                chat_messages = json.loads(draft.chat_history)
            except json.JSONDecodeError:
                chat_messages = []

        # 채팅 컨텍스트 구성
        chat_context = ""
        for msg in chat_messages:
            role_label = "사용자" if msg["role"] == "user" else "어시스턴트"
            chat_context += f"\n[{role_label}]: {msg['content']}\n"

        # 가이드라인 체크리스트 (draft에 저장된 것 사용)
        checklist_section = ""
        if draft.guidelines_checklist:
            checklist_section = f"""
## 적용된 가이드라인 체크리스트
{draft.guidelines_checklist}
"""

        # 기사 분석 (agent 모드에서 저장된 것)
        analysis_section = ""
        if draft.analysis:
            analysis_section = f"""
## 기사 분석
{draft.analysis}
"""

        prompt = f"""다음 LinkedIn 포스트를 사용자의 요청에 따라 수정해주세요.

## 현재 초안
{current_content}
{analysis_section}{checklist_section}{f'''
## 이전 대화
{chat_context}
''' if chat_context else ''}
## 사용자 요청
{user_message}

## 중요
- 사용자의 요청사항만 반영하고, 나머지는 그대로 유지하세요
- LinkedIn 포스트 본문만 출력하세요
- 설명 없이 바로 사용 가능한 형태
- 1200자 이상 1800자 이하 유지"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        revised = response.content[0].text

        # 채팅 이력 업데이트
        timestamp = _time.strftime("%Y-%m-%d %H:%M:%S")
        chat_messages.append({"role": "user", "content": user_message, "timestamp": timestamp})
        chat_messages.append({"role": "assistant", "content": f"수정 완료 ({len(revised)}자)", "timestamp": timestamp})

        # DB 업데이트
        draft.draft_content = revised
        draft.chat_history = json.dumps(chat_messages, ensure_ascii=False)
        self.db.commit()

        return {
            "revised_draft": revised,
            "char_count": len(revised),
            "chat_history": chat_messages,
            "updated_content": revised,
        }

    def get_scenarios(self) -> dict:
        """Get all available scenarios."""
        return SCENARIOS
