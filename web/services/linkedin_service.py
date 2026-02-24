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

from web.models import Article, LinkedInDraft
from web.config import ANTHROPIC_API_KEY
from web.services.source_fetcher import fetch as fetch_source_content
from web.services.web_researcher import research_article
from web.services.style_brief import StyleBriefBuilder
from web.services.article_context import build_article_context
from web.services.evaluator import LinkedInEvaluator

# Writing-critical steps use Opus for quality; classification/evaluation use Haiku/Sonnet
MODEL_WRITING = "claude-opus-4-20250514"
MODEL_SUPPORT = "claude-sonnet-4-20250514"
MODEL_CLASSIFY = "claude-haiku-4-5-20251001"


# Jake's LinkedIn Post Scenarios
SCENARIOS = {
    "A": {
        "name": "산업 분석 + 프레임워크",
        "description": "테제 선언 후 점진적 논증으로 프레임워크 도출",
        "hook_style": "문화적 훅 또는 충격적 숫자 + 테제 선언",
        "structure": "테제 선언 → 점진적 논증 (난이도 상승) → 구체적 대비 → 종합 마무리",
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

    # 시나리오 감지 결과 캐시 (article_id -> {scenario, confidence, reason})
    _scenario_cache: dict = {}
    # 리서치 결과 캐시 (article_id -> research_text)
    _research_cache: dict = {}

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
        """Use Claude API to analyze article and detect best scenario (top-2)."""
        scenarios_desc = "\n".join(
            f"- {key}: {val['name']} - {val['description']}"
            for key, val in SCENARIOS.items()
        )

        prompt = f"""다음 기사에 가장 적합한 LinkedIn 포스팅 시나리오(A-F)를 분석해주세요.
1순위와 2순위 시나리오를 각각 confidence와 함께 반환하세요.

## 기사
- 제목: {article.title}
- 출처: {article.source or '알 수 없음'}
- 요약: {article.ai_summary or article.summary or '없음'}

## 시나리오 목록
{scenarios_desc}

## 출력 형식 (JSON만 출력)
{{"scenario": "A", "confidence": 0.85, "reason": "1순위 시나리오 적합 이유", "alternative": {{"scenario": "D", "confidence": 0.6, "reason": "2순위 시나리오 적합 이유"}}}}"""

        response = self.client.messages.create(
            model=MODEL_CLASSIFY,
            max_tokens=300,
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

            # 대안 시나리오 파싱
            alternatives = []
            alt_data = data.get("alternative")
            if alt_data and isinstance(alt_data, dict):
                alt_scenario = alt_data.get("scenario", "")
                if alt_scenario in SCENARIOS and alt_scenario != scenario:
                    alternatives.append({
                        "scenario": alt_scenario,
                        "confidence": float(alt_data.get("confidence", 0.5)),
                        "reason": alt_data.get("reason", ""),
                    })

            return {
                "scenario": scenario,
                "confidence": float(data.get("confidence", 0.8)),
                "reason": data.get("reason", ""),
                "alternatives": alternatives,
            }

        raise ValueError("Failed to parse Claude response")

    def detect_scenario_with_alternatives(self, article: Article) -> dict:
        """Detect the best scenario with alternatives for low-confidence cases.

        Returns:
            dict: {
                primary: {scenario: str, confidence: float, reason: str},
                alternatives: [{scenario: str, confidence: float, reason: str}]
            }
        """
        result = self.detect_scenario_detailed(article)
        return {
            "primary": {
                "scenario": result["scenario"],
                "confidence": result["confidence"],
                "reason": result["reason"],
            },
            "alternatives": result.get("alternatives", []),
        }

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

    def _research_topic(self, article: Article) -> str:
        """Research the article topic using Google Custom Search.

        Returns research context string, or empty string if unavailable.
        Results are cached per article_id.
        """
        if article.id in self._research_cache:
            return self._research_cache[article.id]

        try:
            result = research_article(
                title=article.title,
                summary=article.ai_summary or article.summary or "",
            )
            research_text = result or ""
        except Exception:
            research_text = ""

        self._research_cache[article.id] = research_text
        return research_text

    def generate_hooks(
        self,
        article: Article,
        scenario: Optional[str] = None,
        count: int = 5,
        instructions: Optional[str] = None,
    ) -> List[dict]:
        """Generate multiple hook options before full draft.

        Args:
            article: Article to generate hooks for
            scenario: Scenario (A-F), auto-detected if not provided
            count: Number of hooks to generate (default 5)
            instructions: Additional user instructions (optional)

        Returns:
            list[dict] — 각 {hook: str, style: str, reasoning: str}
        """
        if scenario is None:
            scenario = self.detect_scenario(article)

        # StyleBrief 빌드 (guidelines + StyleProfile + references)
        builder = StyleBriefBuilder(self.db)
        brief = builder.build(scenario)

        scenario_info = brief.scenario_info

        # Fetch source content for deeper hooks
        source_content = self._fetch_source_content(article.url)

        # Run research
        research_context = self._research_topic(article)

        article_context = build_article_context(
            article, source_content=source_content, research_context=research_context,
        )

        # Hook prompt section from brief
        hook_guidelines = ""
        hook_section_text = brief.to_hook_prompt_section()
        if hook_section_text:
            hook_guidelines = f"\n{hook_section_text}"

        persona = brief.persona

        # 추가 지시 섹션
        instructions_section = ""
        if instructions and instructions.strip():
            instructions_section = f"""
## 추가 지시 (반드시 반영)
{instructions.strip()}
"""

        prompt = f"""당신은 LinkedIn 포스팅 전문가입니다. 다음 기사에 대해 LinkedIn 포스트의 훅(첫 1-3줄)을 {count}개 생성해주세요.

## 페르소나
{persona}

## 시나리오 {scenario}: {scenario_info['name']}
- 훅 스타일: {scenario_info['hook_style']}
- 설명: {scenario_info['description']}

{article_context}
{hook_guidelines}{instructions_section}
## 훅 작성 규칙
- 각 훅은 1-3줄 (최대 210자 이내 — LinkedIn '더보기' 접힘점 기준)
- {count}개의 훅은 각각 다른 접근법/스타일이어야 함
- 금지: 이모지, "여러분", "혁명", "패러다임 시프트" 등 과장 표현
- 문체: 하십시오체 기본, 자연스러운 톤
- 훅만 작성 (본문 전개 X)

## 훅 스타일 분류
각 훅에 다음 중 하나의 스타일을 태깅하세요:
- 숫자형: 충격적 수치/통계로 시작
- 질문형: 독자의 호기심을 자극하는 질문
- 역설: 통념을 뒤집는 반전 제시
- 선언: 강한 의견이나 행동 선언
- 스토리: 개인 경험/관찰로 시작

## 출력 형식 (JSON 배열만 출력)
```json
[
  {{"hook": "훅 텍스트", "style": "숫자형", "reasoning": "왜 이 훅이 효과적인지 한 문장"}},
  ...
]
```

JSON만 출력하세요. 다른 설명은 불필요합니다."""

        response = self.client.messages.create(
            model=MODEL_SUPPORT,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text

        # JSON 배열 파싱
        try:
            json_start = raw.find("[")
            json_end = raw.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                hooks = json.loads(raw[json_start:json_end])
                # 필수 필드 검증
                validated = []
                for h in hooks:
                    if isinstance(h, dict) and "hook" in h:
                        validated.append({
                            "hook": h["hook"],
                            "style": h.get("style", "기타"),
                            "reasoning": h.get("reasoning", ""),
                        })
                return validated[:count]
        except (json.JSONDecodeError, ValueError):
            pass

        # 파싱 실패 시 빈 리스트 반환
        return []

    def generate_draft(
        self,
        article: Article,
        scenario: Optional[str] = None,
        hook: Optional[str] = None,
        instructions: Optional[str] = None,
    ) -> LinkedInDraft:
        """
        Generate a LinkedIn draft for an article.

        Args:
            article: Article to generate draft for
            scenario: Scenario (A-F), auto-detected if not provided
            hook: Pre-selected hook text to use as opening
            instructions: Additional user instructions (optional)

        Returns:
            LinkedInDraft record
        """
        if scenario is None:
            scenario = self.detect_scenario(article)

        # StyleBrief 빌드 (guidelines + StyleProfile + references)
        builder = StyleBriefBuilder(self.db)
        brief = builder.build(scenario)

        scenario_info = brief.scenario_info

        # Fetch source content for deep reading
        source_content = self._fetch_source_content(article.url)

        # Run research
        research_context = self._research_topic(article)

        # Build the prompt
        prompt = self._build_prompt(
            article, scenario, scenario_info, brief,
            hook=hook, source_content=source_content,
            research_context=research_context, instructions=instructions,
        )

        # Generate with Claude (Opus for writing quality)
        response = self.client.messages.create(
            model=MODEL_WRITING,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        draft_content = response.content[0].text

        # AI 평가-수정 루프 (정규식 + full AI 평가 → 타겟 수정, 최대 2회)
        evaluator = LinkedInEvaluator(self.db, brief)
        draft_content, evaluation, iteration_count = evaluator.evaluate_and_fix(
            draft_content, article.url, max_iterations=2
        )

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
            evaluation=evaluation,
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

    def _fetch_source_content(self, url: str) -> str:
        """Fetch source article content for deep reading."""
        try:
            content = fetch_source_content(url)
            return content or ""
        except Exception:
            return ""

    def _build_prompt(self, article: Article, scenario: str, scenario_info: dict, brief, hook: Optional[str] = None, source_content: str = "", research_context: str = "", instructions: Optional[str] = None) -> str:
        """Build the generation prompt using StyleBrief."""
        # 기사 정보 섹션 (풍부한 맥락 포함)
        article_section = build_article_context(article, source_content=source_content, research_context=research_context)

        # StyleBrief에서 통합 스타일 가이드 생성
        style_section = brief.to_writer_prompt_section()

        # 사전 선택된 훅 섹션
        hook_section = ""
        if hook:
            hook_section = f"""## 사용할 훅 (반드시 이 훅으로 시작)
다음 훅이 사전에 선택되었습니다. 포스트의 첫 부분을 반드시 이 훅으로 시작하세요:

{hook}

이 훅을 그대로 사용하되, 문맥에 맞게 미세 조정은 허용됩니다. 의미나 구조를 변경하지 마세요.
"""

        # 추가 지시 섹션
        instructions_section = ""
        if instructions and instructions.strip():
            instructions_section = f"""## 추가 지시 (반드시 반영)
{instructions.strip()}

"""

        return f"""당신은 LinkedIn 포스팅 전문가입니다. 다음 기사를 바탕으로 LinkedIn 포스트를 작성해주세요.

{style_section}

## 시나리오 {scenario}: {scenario_info['name']}
- 설명: {scenario_info['description']}
- 훅 스타일: {scenario_info['hook_style']}
- 본문 구조: {scenario_info['structure']}
- 마무리: {scenario_info['closing']}

{article_section}

{hook_section}{instructions_section}## LinkedIn 포맷팅 규칙
- 줄바꿈으로 단락을 명확히 구분하세요
- 짧은 문장과 긴 문장을 섞어 자연스러운 리듬감을 만드세요 (단문만 반복하면 AI스러워집니다)
- 도치문("~뭘까요.", "~보입니다.")은 글 전체에서 1-2회만 허용합니다. 남발하면 부자연스럽습니다
- 넘버링(1, 2, 3)을 활용하여 가독성을 높이세요
- 구분선(ㅡ)을 활용하여 시각적으로 정리하세요

## 길이 제약 (매우 중요)
반드시 1800자 이상 2800자 이하로 작성하세요.
이상적 길이는 2200-2600자입니다. 이 범위를 벗어나면 조절하세요.

## 출력 형식
- 제목/헤더 없이 본문만 출력하세요. 첫 줄이 곧 훅입니다.
- 설명이나 주석 없이 바로 사용 가능한 형태로 작성하세요.
- 마지막에 원문 링크 한 줄: {article.url}

## 작성 원칙

### 1. 원문 소재 충실 활용 (최우선 원칙)
원문 콘텐츠를 깊이 읽고 구체적 수치, 직접 인용구, 고유 사례, 대비 소재를 반드시 추출하여 포스트 전반에 녹이세요.
표면적 요약을 반복하지 말고, 원문의 '살아있는 디테일'을 활용하세요.
원문에 없는 내용을 만들어내지 마세요 — 팩트 기반으로 작성하세요.

### 2. 테제(Thesis) 주도
한 문장으로 포스트 전체를 관통하는 핵심 주장 선언.
좋은 예: "에이전트 시대에 살아남는 소프트웨어의 조건이 3가지로 수렴했습니다"
나쁜 예: "최근 AI 업계에서 여러 움직임이 있었습니다" (테제 없음)

### 3. 문화적 훅
업계 격언/유명 문구를 비틀어 인지적 마찰 생성.
예: "Make something people want" → "Make something agents want"

### 4. 점진적 논증
각 포인트가 이전 포인트 위에 쌓여야 함 (병렬 나열 금지).
예: 문서(쉬움) → harness(어려움) → 도메인(불가능)

### 5. 구체적 대비
승자 vs 패자를 이름/숫자로 보여주기.
예: "Supabase vs SendGrid", "2시간→3분"

### 6. 종합 마무리
전체 논증을 한 문장으로 응축.
예: "코드에서 문서로, 문서에서 harness로, harness에서 도메인으로."

## 다음과 같이 작성하지 마세요 (anti-pattern)
1. 너무 일반적인 서론 ("오늘은 ~에 대해...")
2. "~에 대해 이야기하겠습니다"
3. "결론적으로~"
4. "요약하면~"
5. 표면적 정보 나열 — 원문 요약 반복은 포스팅이 아님
6. 병렬 구조만 사용 — "첫째, 둘째, 셋째" 나열은 기계적
7. 테제 없는 나열 — 뉴스 요약이지 포스팅이 아님
"""

    def chat_refine_by_draft(self, draft_id: int, user_message: str) -> dict:
        """Refine draft via chat message using draft from DB (no session needed).

        Args:
            draft_id: LinkedInDraft ID
            user_message: User's chat message

        Returns:
            dict with revised_draft, char_count, chat_history, updated_content, validation_warnings
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

        # StyleBrief 로드 (시나리오/참고예시 컨텍스트)
        brief = None
        scenario_section = ""
        reference_section = ""
        if draft.scenario:
            builder = StyleBriefBuilder(self.db)
            brief = builder.build(draft.scenario)
            scenario_info = brief.scenario_info

            scenario_section = f"""
## 시나리오 {draft.scenario}: {scenario_info.get('name', '')}
- 본문 구조: {scenario_info.get('structure', '')}
- 마무리: {scenario_info.get('closing', '')}
"""
            if brief.reference_examples:
                reference_section = f"\n{brief.reference_examples}\n"

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
{analysis_section}{checklist_section}{scenario_section}{reference_section}{f'''
## 이전 대화
{chat_context}
''' if chat_context else ''}
## 사용자 요청
{user_message}

## 중요
- 사용자의 요청사항만 반영하고, 나머지는 그대로 유지하세요
- LinkedIn 포스트 본문만 출력하세요
- 설명 없이 바로 사용 가능한 형태
- 1800자 이상 2800자 이하 유지"""

        response = self.client.messages.create(
            model=MODEL_WRITING,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        revised = response.content[0].text

        # 수정 후 검증
        evaluator = LinkedInEvaluator(self.db, brief)
        validation = evaluator.validate(revised, "")
        warnings = validation["issues"] if not validation["valid"] else []

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
            "validation_warnings": warnings,
        }

    def get_scenarios(self) -> dict:
        """Get all available scenarios."""
        return SCENARIOS
