"""Unified LinkedIn draft evaluator.

Consolidates three evaluation modes:
  - validate()  : regex-based rule checks (no LLM, fast)
  - evaluate()  : AI-based evaluation (quick=Haiku, full=Opus)
"""

import json
import re
import unicodedata
from typing import Optional

from anthropic import Anthropic
from sqlalchemy.orm import Session

from web.config import ANTHROPIC_API_KEY
from web.services.style_brief import StyleBrief


# Models (imported here to avoid circular dependency with linkedin_service)
MODEL_WRITING = "claude-opus-4-20250514"
MODEL_CLASSIFY = "claude-haiku-4-5-20251001"


# 금지어 목록
FORBIDDEN_WORDS = [
    "여러분", "혁명", "패러다임 시프트", "게임체인저",
    "하세요", "해보세요", "읽어주셔서 감사",
    "전환점", "돌풍", "대전환",
]

# 조언톤 패턴
ADVICE_PATTERNS = [
    r"~하세요", r"~해보세요", r"~해볼까요", r"~합시다",
    r"해보시기", r"시작하세요", r"도전하세요", r"고민하세요",
]

# 공포마케팅 패턴
FEAR_PATTERNS = [
    r"뒤처", r"늦으면", r"지금 안 하면", r"놓치면",
    r"도태", r"살아남", r"따라잡",
]


class LinkedInEvaluator:
    """Unified evaluation for LinkedIn drafts."""

    def __init__(self, db: Session, brief: Optional[StyleBrief] = None):
        self.db = db
        self.brief = brief
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)

    def validate(self, content: str, article_url: str) -> dict:
        """Regex-based rule validation (no LLM). Fast quality gate."""
        issues = []
        char_count = len(content)

        # 1. 글자수 검증 (1800-2800)
        if char_count < 1800:
            issues.append(f"글자수 부족: {char_count}자 (최소 1800자 필요)")
        elif char_count > 2800:
            issues.append(f"글자수 초과: {char_count}자 (최대 2800자)")

        # 2. 금지어 체크
        for word in FORBIDDEN_WORDS:
            if word in content:
                issues.append(f"금지어 포함: '{word}'")

        # 3. 조언톤 정규식 체크
        for pattern in ADVICE_PATTERNS:
            if re.search(pattern, content):
                issues.append(f"조언톤 감지: '{pattern}'")

        # 4. 공포마케팅 패턴 체크
        for pattern in FEAR_PATTERNS:
            if re.search(pattern, content):
                issues.append(f"공포마케팅 감지: '{pattern}'")

        # 5. 이모지 체크
        for char in content:
            if unicodedata.category(char).startswith("So"):
                issues.append("이모지 포함됨")
                break

        # 6. 원문 링크 포함 여부
        if article_url and article_url not in content:
            issues.append("원문 링크가 포함되지 않음")

        # 7. 구조 체크: 단락 수 최소 3개
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if len(paragraphs) < 3:
            issues.append(f"단락 수 부족: {len(paragraphs)}개 (최소 3개 필요)")

        # 8. 훅(첫 줄) 210자 이내
        first_line = content.strip().split("\n")[0] if content.strip() else ""
        if len(first_line) > 210:
            issues.append(f"훅이 너무 김: {len(first_line)}자 (최대 210자)")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "char_count": char_count,
        }

    def evaluate(self, content: str, mode: str = "quick") -> str:
        """AI-based evaluation. mode: 'quick' (Haiku) / 'full' (Opus).

        Returns JSON string with evaluation results.
        """
        guidelines_text = self.brief.to_reviewer_prompt_section() if self.brief else "기본 LinkedIn 포스팅 규칙"
        model = MODEL_CLASSIFY if mode == "quick" else MODEL_WRITING

        if mode == "quick":
            prompt = f"""다음 LinkedIn 포스트를 간략히 평가해주세요.

## 포스트
{content}

## 평가 기준
{guidelines_text}

## 평가 항목
1. 문체 (하십시오체 준수)
2. 금지어 사용 여부 (이모지, 여러분, 과장표현)
3. 구조 (훅-본문-마무리)
4. 길이 (1800-2800자)
5. 조언톤 여부

## 출력 형식 (JSON만)
{{"overall_score": 85, "items": [{{"category": "문체", "rule": "하십시오체", "pass": true, "comment": "적절"}}], "summary": "한 줄 요약"}}"""
        else:
            prompt = f"""다음 LinkedIn 포스트를 지침 항목별로 평가해주세요.

## 최종 초안
{content}

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

        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=1000 if mode == "quick" else 2000,
                messages=[{"role": "user", "content": prompt}],
            )

            raw = response.content[0].text

            # Extract JSON from response
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                evaluation_json = raw[json_start:json_end]
                json.loads(evaluation_json)  # validate
                return evaluation_json

            return json.dumps({"overall_score": 0, "error": "평가 결과 파싱 실패"})
        except Exception as e:
            return json.dumps({"overall_score": 0, "error": str(e)})
