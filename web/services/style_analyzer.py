"""Style analyzer service for building and maintaining dynamic writing style profiles."""

import json
from datetime import datetime
from typing import Optional

from anthropic import Anthropic
from sqlalchemy.orm import Session

from web.models import ReferencePost, LinkedInDraft, StyleProfile
from web.config import ANTHROPIC_API_KEY


class StyleAnalyzer:
    """Service for analyzing writing style from reference posts and building style profiles."""

    def __init__(self, db: Session):
        self.db = db
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def get_current_profile(self) -> Optional[dict]:
        """최신 StyleProfile 반환. 없으면 None (guidelines fallback)."""
        profile = (
            self.db.query(StyleProfile)
            .order_by(StyleProfile.id.desc())
            .first()
        )
        if not profile:
            return None
        return profile.to_dict()

    def build_profile(self) -> dict:
        """모든 ReferencePost 분석 + 승인된 드래프트 → 통합 스타일 프로필 생성.

        - ReferencePost.analysis JSON들을 수집
        - 승인/발행된 LinkedInDraft 수집 (최근 10개)
        - Claude Sonnet으로 종합 → StyleProfile 저장
        """
        # 레퍼런스 포스트 수집
        ref_posts = self.db.query(ReferencePost).all()
        analyses = []
        for post in ref_posts:
            entry = {
                "content_preview": post.content[:500] if post.content else "",
                "author": post.author,
                "scenario": post.scenario,
            }
            if post.analysis:
                try:
                    entry["analysis"] = json.loads(post.analysis)
                except json.JSONDecodeError:
                    entry["analysis_raw"] = post.analysis
            analyses.append(entry)

        # 승인/발행된 드래프트 수집
        approved_drafts = (
            self.db.query(LinkedInDraft)
            .filter(LinkedInDraft.status.in_(["final", "published"]))
            .order_by(LinkedInDraft.created_at.desc())
            .limit(10)
            .all()
        )
        draft_samples = []
        for draft in approved_drafts:
            draft_samples.append({
                "content_preview": draft.draft_content[:500] if draft.draft_content else "",
                "scenario": draft.scenario,
            })

        if not analyses and not draft_samples:
            return {"error": "레퍼런스 포스트와 승인된 드래프트가 없습니다."}

        prompt = f"""다음 레퍼런스 포스트 분석 결과와 승인된 드래프트를 종합하여 통합 스타일 프로필을 생성하세요.

## 레퍼런스 포스트 분석 ({len(analyses)}개)
{json.dumps(analyses, ensure_ascii=False, indent=2)}

## 승인/발행된 드래프트 ({len(draft_samples)}개)
{json.dumps(draft_samples, ensure_ascii=False, indent=2)}

## 출력 형식 (JSON)
```json
{{
  "tone": {{
    "formality": "기본 문체 (하십시오체/해요체/혼합)",
    "persona_voice": "페르소나 분석"
  }},
  "structure_patterns": {{
    "preferred_hooks": ["자주 사용되는 훅 유형"],
    "body_flow": "본문 전개 패턴",
    "preferred_closings": ["마무리 패턴"]
  }},
  "vocabulary": {{
    "preferred_phrases": ["자주 사용되는 표현"],
    "forbidden_phrases": ["피해야 할 표현"]
  }},
  "metrics": {{
    "avg_length": 0,
    "avg_paragraph_count": 0
  }},
  "positive_patterns": ["효과적인 패턴 분석"],
  "negative_patterns": ["피해야 할 패턴"]
}}
```

JSON만 출력하세요."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        profile_data = self._parse_json(raw)

        if "error" not in profile_data:
            # 기존 프로필의 최신 버전 조회
            latest = (
                self.db.query(StyleProfile)
                .order_by(StyleProfile.id.desc())
                .first()
            )
            new_version = (latest.version + 1) if latest else 1

            profile = StyleProfile(
                profile_data=json.dumps(profile_data, ensure_ascii=False),
                version=new_version,
                source_post_count=len(analyses) + len(draft_samples),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)

            return profile.to_dict()

        return profile_data

    def update_from_post(self, content: str, feedback: str = "") -> dict:
        """새 레퍼런스 추가 시 증분 프로필 업데이트."""
        current = self.get_current_profile()
        if not current:
            return self.build_profile()

        current_data = current.get("profile_data", {})

        prompt = f"""현재 스타일 프로필에 새 레퍼런스 포스트를 반영하여 업데이트하세요.

## 현재 프로필
{json.dumps(current_data, ensure_ascii=False, indent=2)}

## 새 레퍼런스 포스트
{content[:2000]}

{f"## 사용자 피드백: {feedback}" if feedback else ""}

## 규칙
1. 기존 프로필을 기반으로 새 포스트의 패턴을 병합
2. 새 패턴이 기존과 충돌하면 빈도 기반으로 판단
3. 같은 JSON 구조 유지

JSON만 출력하세요."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        updated_data = self._parse_json(raw)

        if "error" not in updated_data:
            latest = (
                self.db.query(StyleProfile)
                .order_by(StyleProfile.id.desc())
                .first()
            )
            new_version = (latest.version + 1) if latest else 1
            source_count = (latest.source_post_count + 1) if latest else 1

            profile = StyleProfile(
                profile_data=json.dumps(updated_data, ensure_ascii=False),
                version=new_version,
                source_post_count=source_count,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)

            return profile.to_dict()

        return updated_data

    def learn_from_feedback(self, draft_content: str, feedback: str, is_positive: bool) -> dict:
        """사용자 피드백 → positive/negative 패턴 업데이트."""
        current = self.get_current_profile()
        if not current:
            return {"error": "스타일 프로필이 없습니다. 먼저 프로필을 빌드하세요."}

        current_data = current.get("profile_data", {})
        feedback_type = "긍정적" if is_positive else "부정적"

        prompt = f"""사용자 피드백을 스타일 프로필에 반영하세요.

## 현재 프로필
{json.dumps(current_data, ensure_ascii=False, indent=2)}

## 드래프트 내용
{draft_content[:1500]}

## 사용자 피드백 ({feedback_type})
{feedback}

## 규칙
1. {feedback_type} 피드백을 {"positive_patterns" if is_positive else "negative_patterns"}에 반영
2. 기존 패턴과 중복되면 강화/구체화
3. 같은 JSON 구조 유지

JSON만 출력하세요."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        updated_data = self._parse_json(raw)

        if "error" not in updated_data:
            latest = (
                self.db.query(StyleProfile)
                .order_by(StyleProfile.id.desc())
                .first()
            )
            new_version = (latest.version + 1) if latest else 1

            profile = StyleProfile(
                profile_data=json.dumps(updated_data, ensure_ascii=False),
                version=new_version,
                source_post_count=latest.source_post_count if latest else 0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)

            return profile.to_dict()

        return updated_data

    def learn_from_draft(self, draft_id: int) -> dict:
        """Learn from a published/finalized draft: evaluation score + user_feedback → pattern update.

        Called after publish or manual trigger. Determines positive/negative based on
        eval score and collects feedback from user_feedback + chat_history.
        """
        draft = self.db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
        if not draft:
            return {"error": f"Draft {draft_id} not found"}

        if not draft.draft_content:
            return {"error": "Draft has no content"}

        # Determine score from evaluation
        eval_score = 0
        if draft.evaluation:
            try:
                eval_data = json.loads(draft.evaluation)
                eval_score = eval_data.get("overall_score", 0)
            except (json.JSONDecodeError, KeyError):
                pass

        is_positive = eval_score >= 70

        # Collect feedback from user_feedback + chat_history
        feedback_parts = []
        if draft.user_feedback and draft.user_feedback.strip():
            feedback_parts.append(draft.user_feedback.strip())

        if draft.chat_history:
            try:
                chats = json.loads(draft.chat_history)
                for msg in chats:
                    if msg.get("role") == "user":
                        feedback_parts.append(msg["content"][:200])
            except (json.JSONDecodeError, KeyError):
                pass

        feedback = "\n".join(feedback_parts)

        # No feedback + positive → update_from_post (general style learning)
        if not feedback and is_positive:
            return self.update_from_post(draft.draft_content)

        # Has feedback or negative → learn_from_feedback
        if feedback:
            return self.learn_from_feedback(draft.draft_content, feedback, is_positive)

        # Negative but no feedback → still learn negative patterns
        return self.learn_from_feedback(
            draft.draft_content,
            f"평가 점수 {eval_score}/100 — 자동 학습",
            is_positive,
        )

    def _parse_json(self, raw: str) -> dict:
        """Extract JSON from Claude response."""
        try:
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(raw[json_start:json_end])
        except json.JSONDecodeError:
            pass
        return {"error": "JSON 파싱 실패", "raw": raw}
