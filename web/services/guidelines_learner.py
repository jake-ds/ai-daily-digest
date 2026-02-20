"""Guidelines learning service for analyzing reference posts and suggesting guideline updates."""

import json
from typing import Optional

from anthropic import Anthropic
from sqlalchemy.orm import Session

from web.models import ReferencePost
from web.config import ANTHROPIC_API_KEY, LINKEDIN_GUIDELINES_PATH


class GuidelinesLearner:
    """Service for learning from reference LinkedIn posts and updating guidelines."""

    def __init__(self, db: Session):
        self.db = db
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def _load_guidelines(self) -> str:
        """Load current LinkedIn guidelines."""
        try:
            return LINKEDIN_GUIDELINES_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def analyze_post(self, content: str) -> dict:
        """
        Analyze a reference LinkedIn post to extract patterns and insights.

        Returns analysis dict with writing patterns.
        """
        prompt = f"""다음 LinkedIn 포스트를 분석해주세요. 좋은 포스팅 작성법을 학습하기 위한 분석입니다.

## 포스트 내용
{content}

## 분석 항목 (JSON으로 출력)
```json
{{
  "hook": {{
    "type": "훅 유형 (숫자, 질문, 선언, 스토리 등)",
    "text": "실제 훅 문장",
    "effectiveness": "효과 분석"
  }},
  "structure": {{
    "pattern": "전체 구조 패턴",
    "sections": ["섹션1 설명", "섹션2 설명", ...],
    "flow": "글의 흐름 분석"
  }},
  "tone": {{
    "formality": "문체 수준 (하십시오체/해요체/혼합)",
    "persona": "드러나는 페르소나",
    "voice": "1인칭/3인칭 등"
  }},
  "techniques": [
    "사용된 기법 1",
    "사용된 기법 2"
  ],
  "closing": {{
    "type": "마무리 유형",
    "text": "실제 마무리 문장",
    "call_to_action": "CTA 여부 및 유형"
  }},
  "metrics": {{
    "length": "글자 수 (추정)",
    "paragraph_count": 0,
    "emoji_used": false,
    "link_included": false
  }},
  "strengths": ["강점 1", "강점 2"],
  "patterns_to_learn": ["학습할 패턴 1", "학습할 패턴 2"],
  "overall_assessment": "전체 평가 요약"
}}
```

JSON만 출력하세요."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text

        try:
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(raw[json_start:json_end])
        except json.JSONDecodeError:
            pass

        return {"error": "분석 실패", "raw": raw}

    def suggest_updates(self, analysis: dict) -> dict:
        """
        Compare analysis with current guidelines and suggest updates.

        Returns suggestion dict with proposed changes.
        """
        current_guidelines = self._load_guidelines()

        prompt = f"""현재 LinkedIn 포스팅 지침서와 새 레퍼런스 포스트 분석 결과를 비교하여 지침서 업데이트를 제안해주세요.

## 현재 지침서
{current_guidelines if current_guidelines else "(지침서가 비어있습니다)"}

## 레퍼런스 포스트 분석 결과
{json.dumps(analysis, ensure_ascii=False, indent=2)}

## 출력 형식 (JSON)
지침서에 추가하거나 수정할 내용을 제안해주세요:

```json
{{
  "suggestions": [
    {{
      "type": "add",
      "section": "적용할 섹션명",
      "content": "추가할 내용",
      "reason": "추가 이유"
    }},
    {{
      "type": "modify",
      "section": "수정할 섹션명",
      "original": "기존 내용 (해당되는 경우)",
      "content": "수정된 내용",
      "reason": "수정 이유"
    }}
  ],
  "summary": "전체 제안 요약"
}}
```

JSON만 출력하세요. 기존 지침과 충돌하는 제안은 하지 마세요."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text

        try:
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(raw[json_start:json_end])
        except json.JSONDecodeError:
            pass

        return {"error": "제안 생성 실패", "raw": raw}

    def apply_suggestion(self, suggestion: dict) -> str:
        """
        Apply a single suggestion to the current guidelines.

        Returns the updated guidelines content.
        """
        current = self._load_guidelines()

        prompt = f"""현재 LinkedIn 지침서에 다음 업데이트를 적용해주세요.

## 현재 지침서
{current if current else "(비어있음 - 새로 작성해주세요)"}

## 적용할 업데이트
- 타입: {suggestion.get('type', 'add')}
- 섹션: {suggestion.get('section', '')}
- 내용: {suggestion.get('content', '')}
{f"- 기존 내용: {suggestion.get('original', '')}" if suggestion.get('original') else ''}

## 규칙
1. 기존 내용을 최대한 보존하면서 자연스럽게 병합
2. Markdown 형식 유지
3. 지침서 전체 내용을 출력 (수정된 부분만이 아니라)

업데이트가 적용된 전체 지침서를 Markdown 형식으로 출력하세요."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        updated = response.content[0].text

        # Save backup and write new content
        if LINKEDIN_GUIDELINES_PATH.exists():
            backup_path = LINKEDIN_GUIDELINES_PATH.with_suffix(".md.backup")
            backup_path.write_text(current, encoding="utf-8")

        LINKEDIN_GUIDELINES_PATH.write_text(updated, encoding="utf-8")

        return updated

    def save_reference_post(
        self,
        content: str,
        author: Optional[str] = None,
        source_url: Optional[str] = None,
        analysis: Optional[dict] = None,
    ) -> ReferencePost:
        """Save a reference post to the database."""
        post = ReferencePost(
            content=content,
            author=author,
            source_url=source_url,
            analysis=json.dumps(analysis, ensure_ascii=False) if analysis else None,
        )
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)
        return post
