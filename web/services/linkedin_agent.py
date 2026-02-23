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

from web.models import Article, LinkedInDraft
from web.config import ANTHROPIC_API_KEY
from web.services.linkedin_service import SCENARIOS, MODEL_WRITING
from web.services.source_fetcher import fetch as fetch_source_content
from web.services.web_researcher import research_article
from web.services.style_brief import StyleBriefBuilder
from web.services.article_context import build_article_context
from web.services.evaluator import LinkedInEvaluator


# Agent step definitions
AGENT_STEPS = [
    {"id": 0, "name": "Hook 생성", "description": "5개 훅을 생성하고 선택합니다", "needs_input": True},
    {"id": 1, "name": "소스 보강 리서치", "description": "원문 추출 + 웹 리서치 + 팩트체크"},
    {"id": 2, "name": "글 흐름 구성", "description": "포스트 골격을 설계합니다", "needs_input": True},
    {"id": 3, "name": "초안 작성", "description": "훅+리서치+아웃라인으로 초안을 작성합니다"},
    {"id": 4, "name": "검토 & 개선", "description": "자동 평가-수정 루프 + 사용자 피드백", "needs_input": True},
    {"id": 5, "name": "최종 발행", "description": "최종 평가 후 저장합니다"},
]


@dataclass
class AgentSession:
    """In-memory session for agent execution."""
    session_id: str
    article_id: int
    scenario: str
    current_step: int = -1
    status: str = "running"  # running, waiting, completed, error
    # Step 0: Hook
    hooks: list = field(default_factory=list)
    selected_hook: str = ""
    # Step 1: Research
    source_content: str = ""
    research_context: str = ""
    analysis: str = ""
    # Step 2: Outline
    outline: str = ""
    # Step 3: Draft
    draft: str = ""
    # Step 4: Review
    improved_draft: str = ""
    evaluation: str = ""
    review_notes: str = ""
    user_feedback: str = ""
    guidelines_checklist: str = ""
    iteration_count: int = 0
    # Session meta
    created_at: float = field(default_factory=time.time)
    input_event: asyncio.Event = field(default_factory=asyncio.Event)
    input_data: dict = field(default_factory=dict)
    guidelines_raw: str = ""
    reference_examples: str = ""
    style_brief: Optional[object] = None  # StyleBrief object
    chat_messages: list = field(default_factory=list)
    draft_id: int = 0
    hook: str = ""  # 사전 선택된 훅 (Hook Lab에서)
    additional_instructions: str = ""


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

    async def run(
        self,
        article_id: int,
        scenario: Optional[str] = None,
        hook: Optional[str] = None,
        instructions: Optional[str] = None,
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
            additional_instructions=instructions or "",
        )
        _sessions[session_id] = session

        # Send session info
        yield self._sse("session_created", {
            "session_id": session_id,
            "steps": [{"id": s["id"], "name": s["name"], "description": s["description"]} for s in AGENT_STEPS],
        })

        # StyleBrief 빌드 (guidelines + StyleProfile + references)
        builder = StyleBriefBuilder(self.db)
        session.style_brief = builder.build(scenario)
        session.guidelines_raw = session.style_brief.guidelines_raw
        session.reference_examples = session.style_brief.reference_examples

        scenario_info = session.style_brief.scenario_info

        try:
            # Step 0: Hook 생성 (사용자 선택 대기)
            async for event in self._step_hooks(session, article, scenario_info):
                yield event

            # Step 1: 소스 보강 리서치
            async for event in self._step_research(session, article, scenario_info):
                yield event

            # Step 2: 글 흐름 구성 (사용자 피드백 대기)
            async for event in self._step_outline(session, article, scenario_info):
                yield event

            # Step 3: 초안 작성
            async for event in self._step_draft(session, article, scenario_info):
                yield event

            # Step 4: 검토 & 개선 (자동 루프 + 사용자 피드백)
            async for event in self._step_review(session):
                yield event

            # Step 5: 최종 발행
            async for event in self._step_finalize(session, article):
                yield event

            session.status = "completed"
            yield self._sse("agent_complete", {
                "session_id": session_id,
                "draft_id": session.draft_id,
                "final_draft": session.improved_draft or session.draft,
            })

        except Exception as e:
            session.status = "error"
            yield self._sse("agent_error", {"message": str(e), "session_id": session_id})

    # ── Step 0: Hook 생성 ──────────────────────────────────────────────

    async def _step_hooks(self, session: AgentSession, article: Article, scenario_info: dict) -> AsyncGenerator[str, None]:
        """Step 0: Generate 5 hooks and wait for user selection."""
        session.current_step = 0
        yield self._sse("step_start", {"step": 0, "name": "Hook 생성"})

        # Fast path: Hook Lab에서 사전 선택된 훅이 있으면 skip
        if session.hook:
            session.selected_hook = session.hook
            yield self._sse("step_complete", {
                "step": 0,
                "content": f"사전 선택된 훅 사용:\n\n{session.hook}",
                "skipped": True,
            })
            return

        # 추가 지시 섹션
        instructions_section = ""
        if session.additional_instructions:
            instructions_section = f"""
## 추가 지시 (사용자 요청)
{session.additional_instructions}

위 지시 사항을 훅 생성에 반영하세요.
"""

        # StyleBrief 훅 프롬프트
        hook_style_section = session.style_brief.to_hook_prompt_section() if session.style_brief else ""

        prompt = f"""다음 기사에 대한 LinkedIn 포스트 훅(오프닝) 5개를 생성해주세요.

## 기사 정보
- 제목: {article.title}
- 출처: {article.source}
- 요약: {article.ai_summary or article.summary or '없음'}
- URL: {article.url}

## 시나리오: {session.scenario} - {scenario_info['name']}
- 훅 스타일: {scenario_info['hook_style']}

{hook_style_section}
{instructions_section}
## 훅 작성 원칙
1. 첫 1-3줄로 스크롤을 멈추게 하는 강력한 오프닝
2. 구체적 수치/이름/대비를 포함
3. 각 훅은 서로 다른 접근 (수치, 질문, 선언, 대비, 인용)
4. "~에 대해 이야기하겠습니다" 같은 약한 오프닝 금지
5. 이모지 사용 금지

## 출력 형식
각 훅을 다음 형식으로 출력:

---HOOK 1---
[훅 텍스트 1-3줄]
---HOOK 2---
[훅 텍스트 1-3줄]
---HOOK 3---
[훅 텍스트 1-3줄]
---HOOK 4---
[훅 텍스트 1-3줄]
---HOOK 5---
[훅 텍스트 1-3줄]"""

        result = await self._call_claude(prompt, session)

        # Parse hooks
        hooks = []
        hook_parts = re.split(r'---HOOK \d+---', result)
        for part in hook_parts:
            part = part.strip()
            if part:
                hooks.append(part)

        # fallback: 파싱 실패 시 전체를 하나의 훅으로
        if not hooks:
            hooks = [result.strip()]

        session.hooks = hooks

        yield self._sse("step_complete", {
            "step": 0,
            "content": result,
        })

        # Wait for user to select a hook
        session.status = "waiting"
        yield self._sse("waiting_for_input", {
            "step": 0,
            "prompt": "사용할 훅을 선택해주세요",
            "type": "hook_select",
            "hooks": hooks,
        })

        try:
            session.input_event.clear()
            await asyncio.wait_for(session.input_event.wait(), timeout=600)
            hook_index = session.input_data.get("hook_index", 0)
            if isinstance(hook_index, int) and 0 <= hook_index < len(hooks):
                session.selected_hook = hooks[hook_index]
            else:
                session.selected_hook = hooks[0]
            session.status = "running"
            yield self._sse("input_received", {"step": 0, "selected_hook": session.selected_hook})
        except asyncio.TimeoutError:
            session.selected_hook = hooks[0] if hooks else ""
            session.status = "running"
            yield self._sse("input_timeout", {"step": 0, "default": 0})

    # ── Step 1: 소스 보강 리서치 ──────────────────────────────────────

    async def _step_research(self, session: AgentSession, article: Article, scenario_info: dict) -> AsyncGenerator[str, None]:
        """Step 1: Fetch source content + web research + synthesis."""
        session.current_step = 1
        yield self._sse("step_start", {"step": 1, "name": "소스 보강 리서치"})

        # Fetch source content and run research in parallel
        loop = asyncio.get_event_loop()

        async def fetch_source():
            try:
                return await loop.run_in_executor(
                    None, lambda: fetch_source_content(article.url) or ""
                )
            except Exception:
                return ""

        async def run_research():
            try:
                return await loop.run_in_executor(
                    None, lambda: research_article(
                        title=article.title,
                        summary=article.ai_summary or article.summary or "",
                    ) or ""
                )
            except Exception:
                return ""

        source_content, research_result = await asyncio.gather(
            fetch_source(), run_research()
        )

        session.source_content = source_content
        session.research_context = research_result

        # 추가 지시 섹션
        instructions_section = ""
        if session.additional_instructions:
            instructions_section = f"""
## 추가 지시 (사용자 요청)
{session.additional_instructions}

위 지시 사항을 분석에 반영하세요.
"""

        article_context = build_article_context(
            article,
            source_content=session.source_content,
            research_context=session.research_context,
        )

        # Claude로 종합 분석
        prompt = f"""다음 기사와 리서치 결과를 종합 분석해주세요.

{article_context}
{instructions_section}
## 분석 항목
1. **핵심 팩트/수치**: 기사의 주요 사실과 구체적 숫자 3-5개
2. **팩트체크 결과**: 원문 주장의 신뢰도 평가
3. **교차 소스 데이터**: 다른 출처에서 확인된 정보
4. **업계 맥락/경쟁사 비교**: 관련 기업, 기술, 시장 맥락
5. **인사이트 포인트**: LinkedIn 포스팅으로 발전시킬 수 있는 관점 2-3개
6. **추천 시나리오**: {session.scenario} ({scenario_info['name']})에 적합한 이유

간결하고 구조화된 형태로 분석해주세요."""

        analysis = await self._call_claude(prompt, session)
        session.analysis = analysis

        yield self._sse("step_complete", {
            "step": 1,
            "content": analysis,
            "reference_data": {"article_context": article_context},
        })

    # ── Step 2: 글 흐름 구성 ──────────────────────────────────────────

    async def _step_outline(self, session: AgentSession, article: Article, scenario_info: dict) -> AsyncGenerator[str, None]:
        """Step 2: Design post outline and wait for user feedback."""
        session.current_step = 2
        yield self._sse("step_start", {"step": 2, "name": "글 흐름 구성"})

        # StyleBrief 아웃라인 프롬프트
        outline_style = session.style_brief.to_outline_prompt_section() if session.style_brief else ""

        prompt = f"""선택된 훅과 리서치 결과를 바탕으로 LinkedIn 포스트의 글 흐름(아웃라인)을 설계해주세요.

## 선택된 훅
{session.selected_hook}

## 리서치 분석 결과
{session.analysis}

{outline_style}

## 시나리오: {session.scenario} - {scenario_info['name']}
- 훅 스타일: {scenario_info['hook_style']}
- 본문 구조: {scenario_info['structure']}
- 마무리: {scenario_info['closing']}

## 출력 형식 (이 구조를 정확히 따르세요)

1. **훅 (1-3줄)**: {session.selected_hook}
   → 본문 연결 방식: [어떻게 자연스럽게 본문으로 이어질지]

2. **전환부**: [핵심 테제를 한 문장으로 선언]

3. **본문 1**:
   - 목적: [이 섹션이 하는 역할]
   - 핵심 포인트: [전달할 내용]
   - 활용할 데이터: [리서치에서 가져올 수치/사례]

4. **본문 2**:
   - 목적: [이 섹션이 하는 역할]
   - 핵심 포인트: [전달할 내용]
   - 활용할 데이터: [리서치에서 가져올 수치/사례]

5. **본문 3**:
   - 목적: [이 섹션이 하는 역할]
   - 핵심 포인트: [전달할 내용]
   - 활용할 데이터: [리서치에서 가져올 수치/사례]

6. **마무리**: [{scenario_info['closing']}]

7. **원문 링크**: {article.url}"""

        outline = await self._call_claude(prompt, session)
        session.outline = outline

        yield self._sse("step_complete", {
            "step": 2,
            "content": outline,
        })

        # Wait for user feedback on outline
        session.status = "waiting"
        yield self._sse("waiting_for_input", {
            "step": 2,
            "prompt": "아웃라인을 검토하고 수정 요청이 있으면 입력해주세요",
            "type": "outline_feedback",
        })

        try:
            session.input_event.clear()
            await asyncio.wait_for(session.input_event.wait(), timeout=600)
            outline_feedback = session.input_data.get("feedback", "")
            session.status = "running"
            yield self._sse("input_received", {"step": 2, "feedback": outline_feedback})

            # 피드백이 있으면 아웃라인 수정
            if outline_feedback and outline_feedback.strip():
                revise_prompt = f"""다음 아웃라인을 사용자 피드백에 따라 수정해주세요.

## 현재 아웃라인
{session.outline}

## 사용자 피드백
{outline_feedback}

## 중요
- 사용자 피드백만 반영하고 나머지는 유지
- 같은 출력 형식으로 수정된 아웃라인을 출력"""

                revised_outline = await self._call_claude(revise_prompt, session)
                session.outline = revised_outline

        except asyncio.TimeoutError:
            session.status = "running"
            yield self._sse("input_timeout", {"step": 2})

    # ── Step 3: 초안 작성 ──────────────────────────────────────────────

    async def _step_draft(self, session: AgentSession, article: Article, scenario_info: dict) -> AsyncGenerator[str, None]:
        """Step 3: Write the draft using hook + research + outline + StyleBrief."""
        session.current_step = 3
        yield self._sse("step_start", {"step": 3, "name": "초안 작성"})

        # StyleBrief에서 통합 스타일 가이드 생성
        brief = session.style_brief
        style_section = brief.to_writer_prompt_section() if brief else "지침서가 설정되지 않았습니다."

        # 추가 지시 섹션
        instructions_section = ""
        if session.additional_instructions:
            instructions_section = f"""
## 추가 지시 (반드시 반영)
{session.additional_instructions}

"""

        prompt = f"""다음 정보를 바탕으로 LinkedIn 포스트 초안을 작성해주세요.

## 사용할 훅 (반드시 이 훅으로 시작)
{session.selected_hook}

이 훅을 그대로 사용하되, 문맥에 맞게 미세 조정은 허용됩니다. 의미나 구조를 변경하지 마세요.

## 리서치 분석 결과
{session.analysis}

## 글 흐름 (아웃라인)
{session.outline}

{style_section}

## 시나리오 {session.scenario}: {scenario_info['name']}
- 훅 스타일: {scenario_info['hook_style']}
- 본문 구조: {scenario_info['structure']}
- 마무리: {scenario_info['closing']}

{build_article_context(article, source_content=session.source_content, research_context=session.research_context)}
{instructions_section}
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

        draft = await self._call_claude(prompt, session)
        session.draft = draft

        yield self._sse("step_complete", {
            "step": 3,
            "content": draft,
            "reference_data": {"reference_examples": brief.reference_examples},
        })

    # ── Step 4: 검토 & 개선 ──────────────────────────────────────────

    async def _step_review(self, session: AgentSession) -> AsyncGenerator[str, None]:
        """Step 4: Auto evaluate-fix loop (max 3x) + user feedback."""
        session.current_step = 4
        yield self._sse("step_start", {"step": 4, "name": "검토 & 개선"})

        brief = session.style_brief
        guidelines_text = brief.to_reviewer_prompt_section() if brief else "기본 LinkedIn 포스팅 규칙"

        current_draft = session.draft
        max_iterations = 3

        # Phase A: 자동 평가-수정 루프
        for i in range(max_iterations):
            session.iteration_count = i + 1

            # 1. 평가
            eval_result = await self._evaluate_draft_async(current_draft, session, mode="full")

            try:
                eval_data = json.loads(eval_result)
                overall_score = eval_data.get("overall_score", 100)
                fail_items = [item for item in eval_data.get("items", []) if not item.get("pass", True)]
            except (json.JSONDecodeError, KeyError):
                # 평가 파싱 실패 → 루프 종료
                session.evaluation = eval_result
                yield self._sse("step_content", {
                    "step": 4,
                    "iteration": i + 1,
                    "score": 0,
                    "fail_count": 0,
                    "message": "평가 파싱 실패, 루프 종료",
                })
                break

            session.evaluation = eval_result

            yield self._sse("step_content", {
                "step": 4,
                "iteration": i + 1,
                "score": overall_score,
                "fail_count": len(fail_items),
                "message": f"점수 {overall_score}, FAIL {len(fail_items)}개",
            })

            # 2. 통과 조건: score >= 70 and FAIL < 3
            if overall_score >= 70 and len(fail_items) < 3:
                yield self._sse("step_content", {
                    "step": 4,
                    "iteration": i + 1,
                    "score": overall_score,
                    "fail_count": len(fail_items),
                    "message": "통과",
                    "passed": True,
                })
                break

            # 3. FAIL 항목 타겟 수정
            fail_descriptions = "\n".join(
                f"- [{item.get('category', '')}] {item.get('rule', '')}: {item.get('comment', '')}"
                for item in fail_items
            )
            fix_prompt = f"""다음 LinkedIn 포스트에서 평가에서 FAIL된 항목만 수정해주세요.

## 현재 초안
{current_draft}

## FAIL 항목 (반드시 수정)
{fail_descriptions}

## 중요
- FAIL 항목만 수정하고, 잘 된 부분은 그대로 유지하세요
- LinkedIn 포스트 본문만 출력하세요
- 설명 없이 바로 사용 가능한 형태"""

            current_draft = await self._call_claude(fix_prompt, session)

        session.improved_draft = current_draft

        # 가이드라인 체크리스트 (Step 4에서 내부 생성)
        checklist_prompt = f"""다음 지침서에서 이번 포스팅에 적용된 규칙을 체크리스트로 정리해주세요.

## 지침서
{guidelines_text}

## 현재 초안
{current_draft}

적용된 규칙을 간략히 정리:"""

        session.guidelines_checklist = await self._call_claude(checklist_prompt, session)

        # Phase B: 사용자 피드백
        session.status = "waiting"
        yield self._sse("step_complete", {
            "step": 4,
            "content": current_draft,
            "evaluation": session.evaluation,
            "iterations": session.iteration_count,
        })

        yield self._sse("waiting_for_input", {
            "step": 4,
            "prompt": "초안에 대한 피드백을 입력하세요 (없으면 건너뛰기)",
            "type": "draft_feedback",
        })

        try:
            session.input_event.clear()
            await asyncio.wait_for(session.input_event.wait(), timeout=600)
            session.user_feedback = session.input_data.get("feedback", "")
            session.status = "running"
            yield self._sse("input_received", {"step": 4, "feedback": session.user_feedback})

            # 피드백 있으면 1회 추가 수정
            if session.user_feedback and session.user_feedback.strip():
                feedback_prompt = f"""다음 LinkedIn 포스트를 사용자 피드백에 따라 수정해주세요.

## 현재 초안
{session.improved_draft}

## 사용자 피드백 (반드시 반영)
{session.user_feedback}

## 중요
- 사용자의 피드백만 반영하고, 나머지는 그대로 유지하세요
- LinkedIn 포스트 본문만 출력하세요
- 설명 없이 바로 사용 가능한 형태"""

                session.improved_draft = await self._call_claude(feedback_prompt, session)
                session.review_notes = f"사용자 피드백 반영 완료: {session.user_feedback[:100]}"

        except asyncio.TimeoutError:
            session.user_feedback = ""
            session.status = "running"
            yield self._sse("input_timeout", {"step": 4})

    async def _evaluate_draft_async(self, content: str, session: AgentSession, mode: str = "full") -> str:
        """Run evaluation via LinkedInEvaluator in executor thread."""
        evaluator = LinkedInEvaluator(self.db, session.style_brief)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: evaluator.evaluate(content, mode=mode)
        )

    # ── Step 5: 최종 발행 ──────────────────────────────────────────────

    async def _step_finalize(self, session: AgentSession, article: Article) -> AsyncGenerator[str, None]:
        """Step 5: Final evaluation + save to DB."""
        session.current_step = 5
        yield self._sse("step_start", {"step": 5, "name": "최종 발행"})

        # 최종 평가 1회
        final_draft = session.improved_draft or session.draft
        session.evaluation = await self._evaluate_draft_async(final_draft, session, mode="full")

        # Save to database
        draft_record = self._save_draft(session, article)
        session.draft_id = draft_record.id

        yield self._sse("step_complete", {"step": 5, "content": session.evaluation})

    # ── Claude 호출 ──────────────────────────────────────────────────

    async def _call_claude(self, prompt: str, session: AgentSession) -> str:
        """Call Claude API (always Opus)."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._call_claude_sync(prompt)
        )
        return result

    def _call_claude_sync(self, prompt: str) -> str:
        """Synchronous Claude API call (always MODEL_WRITING/Opus)."""
        response = self.client.messages.create(
            model=MODEL_WRITING,
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
            direction=session.selected_hook,
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
