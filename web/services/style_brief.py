"""StyleBrief: unified style data assembled once, shared by Writer/Reviewer/Hook.

Data Sources → StyleBriefBuilder.build() → StyleBrief → Consumers
  guidelines.md                                          Hook (Step 0)
  StyleProfile                                           Draft (Step 3)
  ReferencePost[]                                        Review (Step 4)
  Past Learnings                                         Chat Refine
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from web.models import LinkedInDraft, ReferencePost, StyleProfile
from web.config import LINKEDIN_GUIDELINES_PATH


@dataclass
class StyleBrief:
    """Assembled once, shared by Writer/Reviewer/Hook as unified style guide."""

    # Identity
    scenario: str                           # "A"-"F"
    scenario_name: str
    scenario_info: dict                     # SCENARIOS[scenario]

    # Persona & Tone
    persona: str                            # guidelines or default
    tone_guidance: str                      # StyleProfile.tone (if exists)

    # Structure
    scenario_guidelines: str                # scenario section from guidelines.md
    structure_patterns: str                 # StyleProfile.structure_patterns (if exists)

    # Examples & Vocabulary
    reference_examples: str                 # ReferencePost DB + guidelines examples
    preferred_phrases: list = field(default_factory=list)   # StyleProfile
    forbidden_phrases: list = field(default_factory=list)   # StyleProfile

    # Learning
    past_learnings: str = ""                # past FAIL patterns + user feedback
    positive_patterns: list = field(default_factory=list)   # StyleProfile
    negative_patterns: list = field(default_factory=list)   # StyleProfile

    # Raw (review/evaluation needs full guidelines)
    guidelines_raw: str = ""

    def to_writer_prompt_section(self) -> str:
        """Writer(Step 3) prompt block — full style guide assembly."""
        sections = []

        # Persona
        sections.append(f"## 페르소나\n{self.persona}")

        # Tone guidance from StyleProfile
        if self.tone_guidance:
            sections.append(f"## 문체 가이드 (스타일 프로필 기반)\n{self.tone_guidance}")

        # Scenario guidelines
        if self.scenario_guidelines:
            sections.append(f"## 작성 지침서 (반드시 준수)\n\n"
                            f"아래는 시나리오 {self.scenario}에 해당하는 작성 지침입니다. "
                            f"이 지침을 철저히 따라주세요:\n\n{self.scenario_guidelines}")

        # Structure patterns from StyleProfile
        if self.structure_patterns:
            sections.append(f"## 구조 패턴 (스타일 프로필 기반)\n{self.structure_patterns}")

        # Reference examples
        if self.reference_examples:
            sections.append(self.reference_examples)

        # Vocabulary guidance
        vocab_parts = []
        if self.preferred_phrases:
            vocab_parts.append("선호 표현: " + ", ".join(self.preferred_phrases))
        if self.forbidden_phrases:
            vocab_parts.append("금지 표현: " + ", ".join(self.forbidden_phrases))
        if vocab_parts:
            sections.append("## 어휘 가이드 (스타일 프로필 기반)\n" + "\n".join(vocab_parts))

        # Positive/negative patterns
        pattern_parts = []
        if self.positive_patterns:
            pattern_parts.append("효과적인 패턴:\n" + "\n".join(f"- {p}" for p in self.positive_patterns))
        if self.negative_patterns:
            pattern_parts.append("피해야 할 패턴:\n" + "\n".join(f"- {p}" for p in self.negative_patterns))
        if pattern_parts:
            sections.append("## 스타일 패턴 (학습 기반)\n" + "\n\n".join(pattern_parts))

        # Past learnings
        if self.past_learnings:
            sections.append(self.past_learnings)

        return "\n\n".join(sections)

    def to_reviewer_prompt_section(self) -> str:
        """Reviewer(Step 4) prompt block — evaluation criteria focus."""
        sections = []

        # Scenario guidelines as evaluation criteria
        if self.scenario_guidelines:
            sections.append(f"## 평가 기준 지침서\n{self.scenario_guidelines}")
        elif self.guidelines_raw:
            sections.append(f"## 평가 기준 지침서\n{self.guidelines_raw}")

        # Negative patterns as things to check
        if self.negative_patterns:
            sections.append("## 확인할 부정적 패턴\n" + "\n".join(f"- {p}" for p in self.negative_patterns))

        # Forbidden phrases
        if self.forbidden_phrases:
            sections.append("## 금지 표현\n" + "\n".join(f"- {p}" for p in self.forbidden_phrases))

        return "\n\n".join(sections) if sections else "기본 LinkedIn 포스팅 규칙"

    def to_outline_prompt_section(self) -> str:
        """Outline(Step 2) prompt block — structure patterns + reference examples."""
        sections = []
        if self.structure_patterns:
            sections.append(f"## 선호하는 글 구조 패턴\n{self.structure_patterns}")
        if self.positive_patterns:
            sections.append("## 효과적인 패턴\n" + "\n".join(f"- {p}" for p in self.positive_patterns))
        if self.reference_examples:
            sections.append(self.reference_examples)
        return "\n\n".join(sections)

    def to_hook_prompt_section(self) -> str:
        """Hook(Step 0) prompt block — persona + hook style only."""
        sections = []

        sections.append(f"## 페르소나\n{self.persona}")

        if self.tone_guidance:
            sections.append(f"## 문체\n{self.tone_guidance}")

        # Hook-relevant scenario guidelines
        if self.scenario_guidelines:
            sections.append(f"## 지침서 참고 (이 시나리오의 훅 관련 규칙)\n{self.scenario_guidelines}")

        # Preferred phrases for hooks
        if self.preferred_phrases:
            sections.append("## 선호 표현\n" + ", ".join(self.preferred_phrases))

        return "\n\n".join(sections)


class StyleBriefBuilder:
    """guidelines.md + StyleProfile + DB → StyleBrief assembly."""

    def __init__(self, db: Session):
        self.db = db

    def build(self, scenario: str) -> StyleBrief:
        """Build a StyleBrief by assembling all style data sources.

        1. Load guidelines.md (hot-reload)
        2. Query StyleProfile (graceful skip if absent)
        3. Query ReferencePost (scenario filter)
        4. Query past failure patterns
        5. Assemble into StyleBrief
        """
        from web.services.linkedin_service import SCENARIOS

        scenario_info = SCENARIOS.get(scenario, SCENARIOS["A"])
        guidelines = self._load_guidelines()

        # StyleProfile data (graceful skip)
        tone_guidance = ""
        structure_patterns = ""
        preferred_phrases = []
        forbidden_phrases = []
        positive_patterns = []
        negative_patterns = []

        try:
            profile = (
                self.db.query(StyleProfile)
                .order_by(StyleProfile.id.desc())
                .first()
            )
            if profile and profile.profile_data:
                pdata = json.loads(profile.profile_data)
                # Tone
                tone = pdata.get("tone", {})
                if tone:
                    parts = []
                    if tone.get("formality"):
                        parts.append(f"문체: {tone['formality']}")
                    if tone.get("persona_voice"):
                        parts.append(f"페르소나 보이스: {tone['persona_voice']}")
                    tone_guidance = "\n".join(parts)
                # Structure
                sp = pdata.get("structure_patterns", {})
                if sp:
                    parts = []
                    if sp.get("preferred_hooks"):
                        parts.append(f"선호 훅: {', '.join(sp['preferred_hooks'])}")
                    if sp.get("body_flow"):
                        parts.append(f"본문 흐름: {sp['body_flow']}")
                    if sp.get("preferred_closings"):
                        parts.append(f"마무리 패턴: {', '.join(sp['preferred_closings'])}")
                    structure_patterns = "\n".join(parts)
                # Vocabulary
                vocab = pdata.get("vocabulary", {})
                preferred_phrases = vocab.get("preferred_phrases", [])
                forbidden_phrases = vocab.get("forbidden_phrases", [])
                # Patterns
                positive_patterns = pdata.get("positive_patterns", [])
                negative_patterns = pdata.get("negative_patterns", [])
        except Exception:
            pass  # StyleProfile 없거나 파싱 실패 → graceful skip

        return StyleBrief(
            scenario=scenario,
            scenario_name=scenario_info["name"],
            scenario_info=scenario_info,
            persona=self._extract_persona(guidelines),
            tone_guidance=tone_guidance,
            scenario_guidelines=self._extract_scenario_guidelines(scenario, guidelines),
            structure_patterns=structure_patterns,
            reference_examples=self._get_reference_examples(scenario, guidelines),
            preferred_phrases=preferred_phrases,
            forbidden_phrases=forbidden_phrases,
            past_learnings=self._get_past_learnings(),
            positive_patterns=positive_patterns,
            negative_patterns=negative_patterns,
            guidelines_raw=guidelines,
        )

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
        """Extract persona section from guidelines, with default fallback."""
        if guidelines:
            persona_match = re.search(
                r'## Persona\n(.*?)(?=\n---)',
                guidelines, re.DOTALL,
            )
            if persona_match:
                return persona_match.group(1).strip()

        return ("- VC 심사역 + ML 엔지니어 출신 AI 빌더\n"
                "- 최신 AI 기술과 시장 동향에 깊은 이해\n"
                "- 실무 경험을 바탕으로 인사이트 공유")

    def _get_reference_examples(self, scenario: str, guidelines: str) -> str:
        """Get reference post examples for the given scenario (scenario-filtered)."""
        examples = []

        # 1. Same-scenario ReferencePost (up to 2)
        ref_posts = (
            self.db.query(ReferencePost)
            .filter(ReferencePost.scenario == scenario)
            .order_by(ReferencePost.created_at.desc())
            .limit(2)
            .all()
        )
        for post in ref_posts:
            examples.append(post.content)

        # Fallback: other scenarios if insufficient
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

        # 2. Example from guidelines
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

        return f"""## 참고 예시

다음은 좋은 포스팅 예시입니다. 이 스타일과 구조를 참고하세요:
{examples_text}"""

    def _get_past_learnings(self, limit: int = 5) -> str:
        """Extract learnings from past drafts (FAIL patterns, user feedback).

        Returns a formatted string of past mistakes to avoid, limited to ~500 chars.
        """
        try:
            past_drafts = (
                self.db.query(LinkedInDraft)
                .filter(LinkedInDraft.evaluation.isnot(None))
                .order_by(LinkedInDraft.created_at.desc())
                .limit(limit)
                .all()
            )

            if not past_drafts:
                return ""

            fail_patterns = []
            success_patterns = []
            user_corrections = []

            for draft in past_drafts:
                # Extract patterns from evaluation
                if draft.evaluation:
                    try:
                        eval_data = json.loads(draft.evaluation)
                        overall_score = eval_data.get("overall_score", 0)

                        # 실패 패턴 (기존)
                        for item in eval_data.get("items", []):
                            if not item.get("pass", True):
                                fail_msg = f"[{item.get('category', '')}] {item.get('rule', '')}"
                                if fail_msg not in fail_patterns:
                                    fail_patterns.append(fail_msg)

                        # 성공 패턴 (고득점 드래프트)
                        if overall_score >= 80:
                            for item in eval_data.get("items", []):
                                if item.get("pass") and len(item.get("comment", "")) > 5:
                                    msg = f"[{item.get('category', '')}] {item.get('comment', '')}"
                                    if msg not in success_patterns:
                                        success_patterns.append(msg)
                    except (json.JSONDecodeError, KeyError):
                        pass

                # Extract user feedback
                if draft.user_feedback and draft.user_feedback.strip():
                    user_corrections.append(draft.user_feedback.strip()[:100])

                # Extract user corrections from chat history
                if draft.chat_history:
                    try:
                        chats = json.loads(draft.chat_history)
                        for msg in chats:
                            if msg.get("role") == "user":
                                user_corrections.append(msg["content"][:100])
                    except (json.JSONDecodeError, KeyError):
                        pass

            if not fail_patterns and not success_patterns and not user_corrections:
                return ""

            result_parts = []
            if fail_patterns:
                result_parts.append("## 반복 실수 방지 (이전 드래프트에서 FAIL된 항목)")
                for p in fail_patterns[:5]:
                    result_parts.append(f"- {p}")

            if success_patterns:
                result_parts.append("\n## 효과적이었던 패턴 (이전 고득점 드래프트)")
                for p in success_patterns[:3]:
                    result_parts.append(f"- {p}")

            if user_corrections:
                result_parts.append("\n## 사용자 수정 이력 (이전 피드백)")
                for c in user_corrections[:3]:
                    result_parts.append(f"- {c}")

            result = "\n".join(result_parts)
            # 700 char limit (성공 패턴 추가로 한도 증가)
            if len(result) > 700:
                result = result[:697] + "..."

            return result

        except Exception:
            return ""
