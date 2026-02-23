"""LinkedIn Agent service for multi-step post generation with SSE streaming."""

import asyncio
import json
import re
import uuid
import time
from typing import Optional, AsyncGenerator
from dataclasses import dataclass, field

from anthropic import Anthropic
from sqlalchemy.orm import Session

from web.models import Article, LinkedInDraft, ReferencePost
from web.config import ANTHROPIC_API_KEY, LINKEDIN_GUIDELINES_PATH
from web.services.linkedin_service import SCENARIOS, MODEL_WRITING, MODEL_SUPPORT
from web.services.source_fetcher import fetch as fetch_source_content


# Agent step definitions
AGENT_STEPS = [
    {"id": 0, "name": "기사 분석", "description": "원문의 핵심 팩트, 맥락, 포인트를 분석합니다"},
    {"id": 1, "name": "방향 설정", "description": "3가지 포스팅 방향을 제안합니다", "needs_input": True},
    {"id": 2, "name": "가이드라인 검토", "description": "적용할 규칙을 체크합니다"},
    {"id": 3, "name": "초안 작성", "description": "선택된 방향으로 초안을 작성합니다", "needs_input": True},
    {"id": 4, "name": "자기 검토 & 개선", "description": "초안을 검토하고 개선합니다"},
    {"id": 5, "name": "가이드라인 평가", "description": "최종 초안을 지침 기준으로 평가합니다"},
]


@dataclass
class AgentSession:
    """In-memory session for agent execution."""
    session_id: str
    article_id: int
    scenario: str
    current_step: int = -1
    status: str = "running"  # running, waiting, completed, error
    analysis: str = ""
    directions: str = ""
    selected_direction: str = ""
    guidelines_checklist: str = ""
    draft: str = ""
    user_feedback: str = ""
    review_notes: str = ""
    improved_draft: str = ""
    evaluation: str = ""
    iteration_count: int = 0
    created_at: float = field(default_factory=time.time)
    # asyncio.Event for user input synchronization
    input_event: asyncio.Event = field(default_factory=asyncio.Event)
    input_data: dict = field(default_factory=dict)
    # 참고자료 및 채팅
    guidelines_raw: str = ""
    reference_examples: str = ""
    chat_messages: list = field(default_factory=list)
    draft_id: int = 0
    hook: str = ""
    source_content: str = ""


# Global session store
_sessions: dict[str, AgentSession] = {}


def get_session(session_id: str) -> Optional[AgentSession]:
    """Get an agent session by ID."""
    return _sessions.get(session_id)


def cleanup_old_sessions(max_age_seconds: int = 3600):
    """Remove sessions older than max_age_seconds."""
    now = time.time()
    expired = [sid for sid, s in _sessions.items() if now - s.created_at > max_age_seconds]
    for sid in expired:
        del _sessions[sid]


class LinkedInAgent:
    """Multi-step LinkedIn post generation agent with SSE streaming."""

    def __init__(self, db: Session):
        self.db = db
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def _load_guidelines(self) -> str:
        """Load LinkedIn guidelines from file."""
        try:
            return LINKEDIN_GUIDELINES_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def _extract_scenario_guidelines(self, scenario: str, guidelines: str) -> str:
        """Extract common rules + specific scenario section from guidelines."""
        if not guidelines:
            return ""

        sections = []

        # 1. Persona section
        persona_match = re.search(
            r'## Persona\n(.*?)(?=\n---)',
            guidelines, re.DOTALL,
        )
        if persona_match:
            sections.append(f"## 페르소나\n{persona_match.group(1).strip()}")

        # 2. Specific scenario guide
        scenario_pattern = rf'### 시나리오 {scenario}:.*?(?=\n---|\n### 시나리오 [A-F]:|$)'
        scenario_match = re.search(scenario_pattern, guidelines, re.DOTALL)
        if scenario_match:
            sections.append(scenario_match.group(0).strip())

        # 3. Common rules
        common_match = re.search(
            r'## 공통 규칙\n(.*?)(?=\n## |$)',
            guidelines, re.DOTALL,
        )
        if common_match:
            sections.append(f"## 공통 규칙\n{common_match.group(1).strip()}")

        # 4. Specific scenario example
        example_pattern = rf'### 시나리오 {scenario} 예시.*?```\n(.*?)```'
        example_match = re.search(example_pattern, guidelines, re.DOTALL)
        if example_match:
            sections.append(f"## 이 시나리오의 예시\n```\n{example_match.group(1).strip()}\n```")

        return "\n\n".join(sections)

    def _extract_persona(self, guidelines: str) -> str:
        """Extract persona section from guidelines."""
        if not guidelines:
            return ""

        persona_match = re.search(
            r'## Persona\n(.*?)(?=\n---)',
            guidelines, re.DOTALL,
        )
        if persona_match:
            return persona_match.group(1).strip()

        return ""

    def _get_past_learnings(self, limit: int = 5) -> str:
        """Extract learnings from past drafts (FAIL patterns, user feedback)."""
        try:
            from web.models import LinkedInDraft as LD
            past_drafts = (
                self.db.query(LD)
                .filter(LD.evaluation.isnot(None))
                .order_by(LD.created_at.desc())
                .limit(limit)
                .all()
            )

            if not past_drafts:
                return ""

            fail_patterns = []
            user_corrections = []

            for draft in past_drafts:
                if draft.evaluation:
                    try:
                        eval_data = json.loads(draft.evaluation)
                        for item in eval_data.get("items", []):
                            if not item.get("pass", True):
                                fail_msg = f"[{item.get('category', '')}] {item.get('rule', '')}"
                                if fail_msg not in fail_patterns:
                                    fail_patterns.append(fail_msg)
                    except (json.JSONDecodeError, KeyError):
                        pass

                if draft.user_feedback and draft.user_feedback.strip():
                    user_corrections.append(draft.user_feedback.strip()[:100])

                if draft.chat_history:
                    try:
                        chats = json.loads(draft.chat_history)
                        for msg in chats:
                            if msg.get("role") == "user":
                                user_corrections.append(msg["content"][:100])
                    except (json.JSONDecodeError, KeyError):
                        pass

            if not fail_patterns and not user_corrections:
                return ""

            result_parts = []
            if fail_patterns:
                result_parts.append("## 반복 실수 방지 (이전 드래프트에서 FAIL된 항목)")
                for p in fail_patterns[:5]:
                    result_parts.append(f"- {p}")

            if user_corrections:
                result_parts.append("\n## 사용자 수정 이력 (이전 피드백)")
                for c in user_corrections[:3]:
                    result_parts.append(f"- {c}")

            result = "\n".join(result_parts)
            if len(result) > 500:
                result = result[:497] + "..."

            return result

        except Exception:
            return ""

    def _get_reference_examples(self, scenario: str, guidelines: str) -> str:
        """Get reference post examples for the given scenario (scenario-filtered)."""
        examples = []

        # 같은 시나리오 ReferencePost 우선 2개
        ref_posts = (
            self.db.query(ReferencePost)
            .filter(ReferencePost.scenario == scenario)
            .order_by(ReferencePost.created_at.desc())
            .limit(2)
            .all()
        )
        for post in ref_posts:
            examples.append(post.content)

        # 부족하면 다른 시나리오에서 fallback
        if len(examples) < 2:
            remaining = 2 - len(examples)
            existing_ids = [p.id for p in ref_posts]
            query = self.db.query(ReferencePost)
            if existing_ids:
                query = query.filter(ReferencePost.id.notin_(existing_ids))
            fallback_posts = (
                query
                .order_by(ReferencePost.created_at.desc())
                .limit(remaining)
                .all()
            )
            for post in fallback_posts:
                examples.append(post.content)

        # 지침서에서 해당 시나리오 예시 추출
        if guidelines:
            pattern = rf"### 시나리오 {scenario} 예시.*?```\n(.*?)```"
            match = re.search(pattern, guidelines, re.DOTALL)
            if match:
                examples.append(match.group(1).strip())

        if not examples:
            return ""

        examples_text = ""
        for i, ex in enumerate(examples, 1):
            examples_text += f"\n### 예시 {i}\n{ex}\n"

        return f"""
## 참고 예시

다음은 좋은 포스팅 예시입니다. 이 스타일과 구조를 참고하세요:
{examples_text}"""

    async def run(
        self,
        article_id: int,
        scenario: Optional[str] = None,
        hook: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Run the agent pipeline, yielding SSE events.

        Yields SSE-formatted strings: "event: <type>\ndata: <json>\n\n"
        """
        # Load article
        article = self.db.query(Article).filter(Article.id == article_id).first()
        if not article:
            yield self._sse("agent_error", {"message": "Article not found"})
            return

        if scenario is None:
            from web.services.linkedin_service import LinkedInService
            service = LinkedInService(self.db)
            scenario = service.detect_scenario(article)

        # Create session
        session_id = str(uuid.uuid4())[:8]
        session = AgentSession(
            session_id=session_id,
            article_id=article_id,
            scenario=scenario,
            hook=hook or "",
        )
        _sessions[session_id] = session

        # Send session info
        yield self._sse("session_created", {
            "session_id": session_id,
            "steps": [{"id": s["id"], "name": s["name"], "description": s["description"]} for s in AGENT_STEPS],
        })

        guidelines = self._load_guidelines()
        scenario_info = SCENARIOS.get(scenario, SCENARIOS["A"])

        try:
            # Step 0: 기사 분석
            async for event in self._step_analyze(session, article, scenario_info):
                yield event

            # Step 1: 방향 설정 (사용자 입력 대기)
            async for event in self._step_directions(session, article, scenario_info):
                yield event

            # Step 2: 가이드라인 검토
            async for event in self._step_guidelines_check(session, guidelines, scenario_info):
                yield event

            # Step 3: 초안 작성 (사용자 피드백 가능)
            async for event in self._step_draft(session, article, scenario_info, guidelines):
                yield event

            # Step 4: 자기 검토 & 개선
            async for event in self._step_review(session, guidelines):
                yield event

            # Step 5: 가이드라인 평가 + 자동 수정 루프
            async for event in self._step_evaluate(session, guidelines):
                yield event

            # 평가 결과 분석 → 점수 < 70 또는 FAIL >= 3이면 자동 수정
            needs_retry = False
            try:
                eval_data = json.loads(session.evaluation)
                overall_score = eval_data.get("overall_score", 100)
                fail_items = [item for item in eval_data.get("items", []) if not item.get("pass", True)]
                if overall_score < 70 or len(fail_items) >= 3:
                    needs_retry = True
            except (json.JSONDecodeError, KeyError):
                pass

            if needs_retry:
                yield self._sse("retry_start", {"reason": f"점수 {overall_score}, FAIL {len(fail_items)}개"})

                # FAIL 항목 수정 프롬프트
                fail_descriptions = "\n".join(
                    f"- [{item.get('category', '')}] {item.get('rule', '')}: {item.get('comment', '')}"
                    for item in fail_items
                )
                fix_prompt = f"""다음 LinkedIn 포스트에서 평가에서 FAIL된 항목만 수정해주세요.

## 현재 초안
{session.improved_draft or session.draft}

## FAIL 항목 (반드시 수정)
{fail_descriptions}

## 중요
- FAIL 항목만 수정하고, 잘 된 부분은 그대로 유지하세요
- LinkedIn 포스트 본문만 출력하세요
- 설명 없이 바로 사용 가능한 형태"""

                fixed_draft = await self._call_claude_streaming(fix_prompt, session, step=5)
                pre_retry_draft = session.improved_draft or session.draft
                session.improved_draft = fixed_draft

                # 재평가 (1회만)
                async for event in self._step_evaluate(session, guidelines):
                    yield event

                yield self._sse("retry_complete", {
                    "pre_retry_draft": pre_retry_draft[:200] + "...",
                    "post_retry_draft": fixed_draft[:200] + "...",
                })

            # Save to database
            draft_record = self._save_draft(session, article)
            session.draft_id = draft_record.id

            session.status = "completed"
            yield self._sse("agent_complete", {
                "session_id": session_id,
                "draft_id": draft_record.id,
                "final_draft": session.improved_draft or session.draft,
            })

        except Exception as e:
            session.status = "error"
            yield self._sse("agent_error", {"message": str(e), "session_id": session_id})

    def _build_article_context(self, article: Article, source_content: str = "") -> str:
        """Build enriched article context with metadata and optional source content."""
        lines = [
            f"## 기사 정보",
            f"- 제목: {article.title}",
            f"- 출처: {article.source}",
            f"- URL: {article.url}",
            f"- 카테고리: {article.category or '미분류'}",
            f"- 요약: {article.ai_summary or article.summary or '없음'}",
        ]

        if article.score and article.score >= 8:
            lines.append(f"- 품질 점수: {article.score}/10 (고품질 기사 → 깊은 분석과 구체적 인사이트를 포함하세요)")
        elif article.score and article.score <= 5:
            lines.append(f"- 품질 점수: {article.score}/10 (간결한 코멘터리와 핵심 포인트 위주로 작성하세요)")
        elif article.score:
            lines.append(f"- 품질 점수: {article.score}/10")

        if article.viral_score and article.viral_score > 0:
            lines.append(f"- 바이럴 점수: {article.viral_score} (화제성 높은 뉴스 → 독자의 관심을 활용하되, 과장은 피하세요)")

        authority_sources = ["mit", "stanford", "google", "deepmind", "openai", "anthropic", "meta ai", "microsoft research"]
        if article.source and any(src in article.source.lower() for src in authority_sources):
            lines.append(f"- 출처 권위: {article.source}는 권위 있는 연구/기술 기관입니다. 연구 권위를 강조하세요.")

        result = "\n".join(lines)

        if source_content:
            result += f"""

## 원문 콘텐츠
아래는 기사 원문에서 추출한 내용입니다. 구체적 수치, 인용구, 사례, 대비 소재를 반드시 활용하세요.

{source_content}"""

        return result

    async def _step_analyze(self, session: AgentSession, article: Article, scenario_info: dict) -> AsyncGenerator[str, None]:
        """Step 0: Analyze the article (with source content fetching)."""
        session.current_step = 0
        yield self._sse("step_start", {"step": 0, "name": "기사 분석"})

        # Fetch source content for deep reading
        try:
            loop = asyncio.get_event_loop()
            source_content = await loop.run_in_executor(
                None, lambda: fetch_source_content(article.url) or ""
            )
            session.source_content = source_content
        except Exception:
            session.source_content = ""

        article_context = self._build_article_context(article, source_content=session.source_content)

        prompt = f"""다음 기사를 분석해주세요. LinkedIn 포스팅을 위한 핵심 정보를 추출합니다.

{article_context}

## 분석 항목
1. **핵심 팩트**: 기사의 주요 사실 3-5개
2. **맥락**: 이 뉴스가 중요한 이유, 업계 영향
3. **인사이트 포인트**: LinkedIn 포스팅으로 발전시킬 수 있는 관점 2-3개
4. **수치/데이터**: 인용 가능한 구체적 숫자나 통계
5. **추천 시나리오**: {session.scenario} ({scenario_info['name']})에 적합한 이유

간결하고 구조화된 형태로 분석해주세요."""

        analysis = await self._call_claude_streaming(prompt, session, step=0)
        session.analysis = analysis
        yield self._sse("step_complete", {
            "step": 0, "content": analysis,
            "reference_data": {"article_context": article_context},
        })

    async def _step_directions(self, session: AgentSession, article: Article, scenario_info: dict) -> AsyncGenerator[str, None]:
        """Step 1: Suggest 3 directions and wait for user choice."""
        session.current_step = 1
        yield self._sse("step_start", {"step": 1, "name": "방향 설정"})

        prompt = f"""기사 분석 결과를 바탕으로 LinkedIn 포스팅의 3가지 방향을 제안해주세요.

## 기사 분석
{session.analysis}

## 시나리오: {session.scenario} - {scenario_info['name']}
- 훅 스타일: {scenario_info['hook_style']}
- 본문 구조: {scenario_info['structure']}

## 출력 형식
각 방향에 대해 다음을 포함해주세요:

### 방향 1: [제목]
- **훅**: 첫 1-2문장 초안
- **핵심 메시지**: 전달하고자 하는 메시지
- **차별점**: 이 방향만의 강점

### 방향 2: [제목]
...

### 방향 3: [제목]
..."""

        directions = await self._call_claude_streaming(prompt, session, step=1)
        session.directions = directions
        yield self._sse("step_complete", {
            "step": 1, "content": directions,
            "reference_data": {
                "scenario_info": {
                    "hook_style": scenario_info.get("hook_style", ""),
                    "structure": scenario_info.get("structure", ""),
                    "closing": scenario_info.get("closing", ""),
                },
            },
        })

        # Wait for user input
        session.status = "waiting"
        yield self._sse("waiting_for_input", {
            "step": 1,
            "prompt": "포스팅 방향을 선택하거나 직접 입력해주세요",
            "type": "direction_select",
        })

        # Wait for user to provide input (with timeout)
        try:
            session.input_event.clear()
            await asyncio.wait_for(session.input_event.wait(), timeout=600)
            session.selected_direction = session.input_data.get("direction", "1")
            session.status = "running"
            yield self._sse("input_received", {"step": 1, "direction": session.selected_direction})
        except asyncio.TimeoutError:
            session.selected_direction = "1"
            session.status = "running"
            yield self._sse("input_timeout", {"step": 1, "default": "1"})

    async def _step_guidelines_check(self, session: AgentSession, guidelines: str, scenario_info: dict) -> AsyncGenerator[str, None]:
        """Step 2: Review guidelines and create checklist."""
        session.current_step = 2
        yield self._sse("step_start", {"step": 2, "name": "가이드라인 검토"})

        # 매번 파일에서 새로 로드 (hot-reload)
        guidelines = self._load_guidelines() or guidelines

        # 시나리오별 필터링된 지침서 사용
        scenario_guidelines = self._extract_scenario_guidelines(session.scenario, guidelines)
        guidelines_text = scenario_guidelines if scenario_guidelines else (
            guidelines if guidelines else "지침서가 설정되지 않았습니다. 기본 규칙을 적용합니다."
        )

        prompt = f"""LinkedIn 포스팅 지침서를 검토하고, 이번 포스팅에 적용할 규칙 체크리스트를 만들어주세요.

## 선택된 방향
{session.selected_direction}

## 시나리오: {session.scenario} - {scenario_info['name']}

## 지침서
{guidelines_text}

## 출력 형식
적용할 규칙을 체크리스트 형태로 정리해주세요:

1. **문체**: 적용할 문체 규칙
2. **구조**: 이 시나리오의 구조 규칙
3. **훅**: 적용할 훅 패턴
4. **금지사항**: 반드시 피할 항목
5. **길이/포맷**: 길이 및 형식 규칙
6. **기타**: 추가 적용 사항"""

        checklist = await self._call_claude_streaming(prompt, session, step=2)
        session.guidelines_checklist = checklist
        session.guidelines_raw = guidelines_text
        yield self._sse("step_complete", {
            "step": 2, "content": checklist,
            "reference_data": {"guidelines_text": guidelines_text},
        })

    async def _step_draft(self, session: AgentSession, article: Article, scenario_info: dict, guidelines: str) -> AsyncGenerator[str, None]:
        """Step 3: Write the draft."""
        session.current_step = 3
        yield self._sse("step_start", {"step": 3, "name": "초안 작성"})

        reference_section = self._get_reference_examples(session.scenario, guidelines)
        session.reference_examples = reference_section

        # 페르소나 추출
        persona = self._extract_persona(guidelines)
        if not persona:
            persona = "- VC 심사역 + ML 엔지니어 출신 AI 빌더\n- 최신 AI 기술과 시장 동향에 깊은 이해"

        # 이전 드래프트 학습
        past_learnings = self._get_past_learnings()
        learnings_section = ""
        if past_learnings:
            learnings_section = f"""
{past_learnings}
"""

        # 훅 섹션 (사전 선택된 훅이 있는 경우)
        hook_section = ""
        if session.hook:
            hook_section = f"""
## 사용할 훅 (반드시 이 훅으로 시작)
다음 훅이 사전에 선택되었습니다. 포스트의 첫 부분을 반드시 이 훅으로 시작하세요:

{session.hook}

이 훅을 그대로 사용하되, 문맥에 맞게 미세 조정은 허용됩니다. 의미나 구조를 변경하지 마세요.
"""

        prompt = f"""다음 정보를 바탕으로 LinkedIn 포스트 초안을 작성해주세요.

## 기사 분석
{session.analysis}

## 선택된 방향
{session.selected_direction}

## 적용할 규칙
{session.guidelines_checklist}

## 시나리오 {session.scenario}: {scenario_info['name']}
- 훅 스타일: {scenario_info['hook_style']}
- 본문 구조: {scenario_info['structure']}
- 마무리: {scenario_info['closing']}

{self._build_article_context(article, source_content=session.source_content)}

## 페르소나
{persona}
{reference_section}{hook_section}{learnings_section}
## LinkedIn 포맷팅 규칙
- 줄바꿈으로 단락을 명확히 구분하세요
- 짧은 문장을 사용하세요 (한 문장에 2줄 이상 금지)
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

### 1. 테제(Thesis) 주도
한 문장으로 포스트 전체를 관통하는 핵심 주장 선언.
좋은 예: "에이전트 시대에 살아남는 소프트웨어의 조건이 3가지로 수렴했습니다"
나쁜 예: "최근 AI 업계에서 여러 움직임이 있었습니다" (테제 없음)

### 2. 문화적 훅
업계 격언/유명 문구를 비틀어 인지적 마찰 생성.
예: "Make something people want" → "Make something agents want"

### 3. 점진적 논증
각 포인트가 이전 포인트 위에 쌓여야 함 (병렬 나열 금지).
예: 문서(쉬움) → harness(어려움) → 도메인(불가능)

### 4. 구체적 대비
승자 vs 패자를 이름/숫자로 보여주기.
예: "Supabase vs SendGrid", "2시간→3분"

### 5. 원문 소재 활용
원문 콘텐츠에서 구체적 수치, 인용구, 사례를 반드시 추출.

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
7. 테제 없는 나열 — 뉴스 요약이지 포스팅이 아님"""

        draft = await self._call_claude_streaming(prompt, session, step=3)
        session.draft = draft
        yield self._sse("step_complete", {
            "step": 3, "content": draft,
            "reference_data": {"reference_examples": reference_section},
        })

        # Wait for user feedback
        session.status = "waiting"
        yield self._sse("waiting_for_input", {
            "step": 3,
            "prompt": "초안에 대한 피드백을 입력하세요 (없으면 건너뛰기)",
            "type": "draft_feedback",
        })

        try:
            session.input_event.clear()
            await asyncio.wait_for(session.input_event.wait(), timeout=600)
            session.user_feedback = session.input_data.get("feedback", "")
            session.status = "running"
            yield self._sse("input_received", {"step": 3, "feedback": session.user_feedback})
        except asyncio.TimeoutError:
            session.user_feedback = ""
            session.status = "running"
            yield self._sse("input_timeout", {"step": 3})

    async def _step_review(self, session: AgentSession, guidelines: str) -> AsyncGenerator[str, None]:
        """Step 4: Self-review and improve (max 2 iterations)."""
        session.current_step = 4
        yield self._sse("step_start", {"step": 4, "name": "자기 검토 & 개선"})

        current_draft = session.draft
        max_iterations = 2

        for i in range(max_iterations):
            session.iteration_count = i + 1

            feedback_section = ""
            if session.user_feedback and i == 0:
                feedback_section = f"""
## 반드시 반영할 사항 (사용자 피드백)
다음 피드백을 반드시 반영하세요. 이것은 최우선 수정 사항입니다:
{session.user_feedback}"""

            prompt = f"""다음 LinkedIn 포스트 초안을 검토하고 개선해주세요.

## 현재 초안
{current_draft}
{feedback_section}

## 가이드라인 체크리스트
다음 체크리스트의 모든 항목을 검증하고, 위반 사항을 반드시 수정하세요:

{session.guidelines_checklist}

## 출력 형식
먼저 [검토 노트]를 작성하고, 그 다음 [개선된 초안]을 작성하세요.

### 검토 노트
- 개선이 필요한 부분과 이유를 간략히 나열

### 개선된 초안
개선된 LinkedIn 포스트 본문만 출력 (설명 없이)"""

            result = await self._call_claude_streaming(prompt, session, step=4)

            # Parse review notes and improved draft
            if "### 개선된 초안" in result:
                parts = result.split("### 개선된 초안")
                session.review_notes = parts[0].replace("### 검토 노트", "").strip()
                current_draft = parts[1].strip()
            elif "개선된 초안" in result:
                parts = result.split("개선된 초안", 1)
                session.review_notes = parts[0].strip()
                current_draft = parts[1].strip()
            else:
                current_draft = result

            yield self._sse("step_content", {
                "step": 4,
                "iteration": i + 1,
                "review_notes": session.review_notes,
                "draft_preview": current_draft[:200] + "...",
            })

            # If first iteration and no major issues, skip second
            if "개선이 필요한 부분" not in session.review_notes and i == 0:
                break

        session.improved_draft = current_draft
        yield self._sse("step_complete", {"step": 4, "content": current_draft, "iterations": session.iteration_count})

    async def _step_evaluate(self, session: AgentSession, guidelines: str) -> AsyncGenerator[str, None]:
        """Step 5: Evaluate final draft against guidelines."""
        session.current_step = 5
        yield self._sse("step_start", {"step": 5, "name": "가이드라인 평가"})

        final_draft = session.improved_draft or session.draft
        # 시나리오별 필터링된 지침서 사용
        scenario_guidelines = self._extract_scenario_guidelines(session.scenario, guidelines)
        guidelines_text = scenario_guidelines if scenario_guidelines else (
            guidelines if guidelines else "기본 LinkedIn 포스팅 규칙"
        )

        prompt = f"""다음 LinkedIn 포스트를 지침 항목별로 평가해주세요.

## 최종 초안
{final_draft}

## 지침서
{guidelines_text}

## 출력 형식 (JSON)
다음 JSON 형식으로 평가 결과를 출력해주세요:

```json
{{
  "overall_score": 85,
  "items": [
    {{"category": "문체", "rule": "하십시오체 기본", "pass": true, "comment": "적절히 사용됨"}},
    {{"category": "문체", "rule": "리듬 전환 (해요체)", "pass": true, "comment": "자연스러운 전환"}},
    {{"category": "구조", "rule": "훅 (1-2문장)", "pass": true, "comment": "강력한 숫자 훅"}},
    {{"category": "구조", "rule": "본문 구조", "pass": true, "comment": "시나리오에 맞는 전개"}},
    {{"category": "구조", "rule": "마무리", "pass": true, "comment": "행동 선언으로 마무리"}},
    {{"category": "금지", "rule": "이모지 없음", "pass": true, "comment": "이모지 미사용"}},
    {{"category": "금지", "rule": "여러분 호칭 없음", "pass": true, "comment": "적절한 톤"}},
    {{"category": "금지", "rule": "과장 표현 없음", "pass": true, "comment": "절제된 표현"}},
    {{"category": "금지", "rule": "조언톤 없음", "pass": true, "comment": "1인칭 서술"}},
    {{"category": "형식", "rule": "길이 (1800-2800자)", "pass": true, "comment": "약 2400자"}},
    {{"category": "형식", "rule": "단락 구분", "pass": true, "comment": "명확한 구분"}},
    {{"category": "형식", "rule": "원문 링크 포함", "pass": true, "comment": "링크 포함됨"}}
  ],
  "summary": "전체적으로 지침을 잘 준수한 포스트입니다."
}}
```

JSON만 출력하세요. 다른 설명은 불필요합니다."""

        evaluation_raw = await self._call_claude_streaming(prompt, session, step=5)

        # Extract JSON from response
        try:
            json_start = evaluation_raw.find("{")
            json_end = evaluation_raw.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                evaluation_json = evaluation_raw[json_start:json_end]
                json.loads(evaluation_json)  # validate
                session.evaluation = evaluation_json
            else:
                session.evaluation = json.dumps({"error": "평가 결과 파싱 실패", "raw": evaluation_raw})
        except json.JSONDecodeError:
            session.evaluation = json.dumps({"error": "JSON 파싱 실패", "raw": evaluation_raw})

        yield self._sse("step_complete", {"step": 5, "content": session.evaluation})

    async def _call_claude_streaming(self, prompt: str, session: AgentSession, step: int) -> str:
        """Call Claude API with streaming, yielding partial content via SSE."""
        # Steps 0 (analysis), 3 (draft), 4 (review) use Opus for quality
        model = MODEL_WRITING if step in (0, 3, 4) else MODEL_SUPPORT
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._call_claude_sync(prompt, model=model)
        )
        return result

    def _call_claude_sync(self, prompt: str, model: str = MODEL_WRITING) -> str:
        """Synchronous Claude API call."""
        response = self.client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _save_draft(self, session: AgentSession, article: Article) -> LinkedInDraft:
        """Save the final draft to database."""
        existing_count = (
            self.db.query(LinkedInDraft)
            .filter(LinkedInDraft.article_id == article.id)
            .count()
        )

        final_content = session.improved_draft or session.draft

        draft = LinkedInDraft(
            article_id=article.id,
            scenario=session.scenario,
            draft_content=final_content,
            version=existing_count + 1,
            generation_mode="agent",
            analysis=session.analysis,
            direction=session.selected_direction,
            review_notes=session.review_notes,
            evaluation=session.evaluation,
            user_feedback=session.user_feedback,
            iteration_count=session.iteration_count,
            guidelines_checklist=session.guidelines_checklist,
            status="final",
        )
        self.db.add(draft)
        article.linkedin_status = "generated"
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def chat_refine(self, session: AgentSession, user_message: str) -> dict:
        """Refine draft via chat message. Returns updated draft and chat history."""
        import time as _time

        current_draft = session.improved_draft or session.draft

        # Build chat context
        chat_context = ""
        for msg in session.chat_messages:
            role_label = "사용자" if msg["role"] == "user" else "어시스턴트"
            chat_context += f"\n[{role_label}]: {msg['content']}\n"

        prompt = f"""다음 LinkedIn 포스트를 사용자의 요청에 따라 수정해주세요.

## 현재 초안
{current_draft}

## 기사 분석
{session.analysis}

## 적용된 가이드라인 체크리스트
{session.guidelines_checklist}
{f'''
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

        revised = self._call_claude_sync(prompt)

        # Update session
        session.improved_draft = revised
        timestamp = _time.strftime("%Y-%m-%d %H:%M:%S")
        session.chat_messages.append({"role": "user", "content": user_message, "timestamp": timestamp})
        session.chat_messages.append({"role": "assistant", "content": f"수정 완료 ({len(revised)}자)", "timestamp": timestamp})

        # Update DB
        draft_record = self.db.query(LinkedInDraft).filter(LinkedInDraft.id == session.draft_id).first()
        if draft_record:
            draft_record.draft_content = revised
            draft_record.chat_history = json.dumps(session.chat_messages, ensure_ascii=False)
            self.db.commit()

        return {
            "revised_draft": revised,
            "char_count": len(revised),
            "chat_history": session.chat_messages,
        }

    def _sse(self, event: str, data: dict) -> str:
        """Format an SSE event string."""
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
