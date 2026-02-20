"""LinkedIn 포스팅 초안 생성기 - Notion 연동용"""

import os
from pathlib import Path
from typing import Optional

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None


class LinkedInGenerator:
    """LinkedIn 포스팅 초안 생성기

    Notion에서 선택한 기사에 대해 지침서 기반으로 초안 생성
    """

    # 시나리오 판별 프롬프트
    SCENARIO_DETECT_PROMPT = """당신은 LinkedIn 콘텐츠 전략가입니다.
아래 기사를 분석하여 가장 적합한 포스팅 시나리오를 판별해주세요.

## 기사 정보
제목: {title}
출처: {source}
카테고리: {category}
요약: {summary}

## 시나리오 정의

**A: 빅뉴스 속보**
- 빅테크의 중요 발표, 대형 투자/인수, 업계 판도를 바꿀 뉴스
- 예: GPT-5 출시, Google의 대형 인수, 규제 변화

**B: 연구/논문 해설**
- 학술 논문, 기술 보고서, 벤치마크 결과
- 예: arXiv 논문, 모델 성능 비교, 새로운 기법 제안

**C: 트렌드 분석**
- 여러 소식을 종합한 업계 흐름 분석
- 예: Agent 경쟁 심화, 오픈소스 LLM 성장세

**D: 실무 인사이트**
- 도구 사용법, 팁, 실제 적용 사례
- 예: 프롬프트 엔지니어링 팁, 도구 비교 리뷰

**E: 오피니언/토론**
- 논쟁적 주제, 미래 예측, 의견 제시
- 예: AI 윤리 논쟁, 일자리 영향, 기술 방향성

## 응답 형식
시나리오: [A/B/C/D/E]
이유: [한 줄 설명]"""

    # 초안 생성 프롬프트 (시나리오별로 다르게 적용)
    DRAFT_PROMPTS = {
        "A": """당신은 LinkedIn에서 AI 뉴스를 공유하는 사람입니다.

## 시나리오 A: 빅뉴스 속보
빠르게 핵심만 전달하되, "왜 중요한지" 맥락을 덧붙입니다.

## 기사 정보
제목: {title}
출처: {source}
요약: {summary}

## 작성 구조
1. Hook (3줄): 숫자나 핵심 팩트로 시작
2. 핵심 내용: 무슨 일인지 2-3문장
3. 왜 중요한지: 업계 맥락에서 의미
4. 나의 생각: 1-2문장
5. 마무리 질문

## 톤
- 속보지만 차분하게
- "혁명적", "획기적" 금지
- 구체적 숫자 활용

{guidelines}

## 응답
LinkedIn 포스트 본문만 작성해주세요. (1200-1500자)""",

        "B": """당신은 LinkedIn에서 AI 연구를 쉽게 설명하는 사람입니다.

## 시나리오 B: 연구/논문 해설
어려운 내용을 비전문가도 이해할 수 있게 풀어씁니다.

## 기사 정보
제목: {title}
출처: {source}
요약: {summary}

## 작성 구조
1. Hook: 이 연구가 해결하는 문제 또는 놀라운 결과
2. 기존 방법의 한계: 왜 새로운 접근이 필요했는지
3. 핵심 아이디어: 비유를 활용해 쉽게 설명
4. 결과/성능: 구체적 숫자
5. 실무 시사점: 우리에게 어떤 의미인지
6. 나의 생각: 1-2문장

## 톤
- "흥미로운 연구를 발견했습니다" 스타일
- 겸손하게, 함께 배우는 느낌
- 전문용어는 꼭 필요할 때만, 설명과 함께

{guidelines}

## 응답
LinkedIn 포스트 본문만 작성해주세요. (1300-1800자)""",

        "C": """당신은 LinkedIn에서 AI 트렌드를 정리하는 사람입니다.

## 시나리오 C: 트렌드 분석
여러 소식의 공통점을 찾아 큰 그림을 그려줍니다.

## 기사 정보
제목: {title}
출처: {source}
요약: {summary}

## 작성 구조
1. Hook: "요즘 AI 업계를 보면..." 또는 "이번 주 소식들의 공통점은..."
2. 개별 사례들: 관련 사례 2-3개 언급
3. 연결고리: 이것들이 보여주는 흐름
4. 의미: 왜 이 트렌드가 중요한지
5. 나의 해석: 1-2문장
6. 마무리 질문

## 톤
- 관찰자 시점
- "주목됩니다" 대신 "흥미롭습니다"
- 과장 없이 팩트 기반

{guidelines}

## 응답
LinkedIn 포스트 본문만 작성해주세요. (1300-1800자)""",

        "D": """당신은 LinkedIn에서 AI 실무 팁을 공유하는 사람입니다.

## 시나리오 D: 실무 인사이트
실제로 써볼 수 있는 구체적 정보를 전달합니다.

## 기사 정보
제목: {title}
출처: {source}
요약: {summary}

## 작성 구조
1. Hook: 문제 상황 또는 "이런 경험 있으신가요?"
2. 해결책/도구 소개
3. 구체적 사용법 또는 팁 (문단으로 자연스럽게)
4. 주의점 또는 한계
5. 나의 경험/생각: 1-2문장
6. "여러분은 어떻게 사용하시나요?"

## 톤
- 실용적, 구체적
- 직접 써본 것처럼 (가능하면)
- 번호 리스트는 3개까지만

{guidelines}

## 응답
LinkedIn 포스트 본문만 작성해주세요. (1200-1600자)""",

        "E": """당신은 LinkedIn에서 AI 주제로 토론을 이끄는 사람입니다.

## 시나리오 E: 오피니언/토론
다양한 의견이 나올 수 있는 주제로 대화를 유도합니다.

## 기사 정보
제목: {title}
출처: {source}
요약: {summary}

## 작성 구조
1. Hook: 논쟁적 질문 또는 의외의 관점
2. 배경: 이 주제가 왜 나왔는지
3. 한쪽 관점: 찬성/긍정적 시각
4. 다른 관점: 반대/우려 시각
5. 나의 생각: 어느 쪽에 가까운지, 왜 그런지
6. 열린 질문: "여러분은 어떻게 생각하시나요?"

## 톤
- 단정 짓지 않기
- "저도 정답은 모르겠지만..."
- 솔직한 고민 공유

{guidelines}

## 응답
LinkedIn 포스트 본문만 작성해주세요. (1300-1800자)"""
    }

    def __init__(self, guidelines_path: str = "data/linkedin_guidelines.md"):
        self.client = None
        if Anthropic and os.getenv("ANTHROPIC_API_KEY"):
            self.client = Anthropic()

        self.guidelines_path = Path(guidelines_path)
        self.guidelines = self._load_guidelines()

    def _load_guidelines(self) -> str:
        """LinkedIn 지침서 로드"""
        if self.guidelines_path.exists():
            try:
                content = self.guidelines_path.read_text(encoding="utf-8")
                return f"\n## 추가 지침\n{content}"
            except Exception as e:
                print(f"지침서 로드 실패: {e}")
        return ""

    def is_available(self) -> bool:
        """API 사용 가능 여부"""
        return self.client is not None

    def detect_scenario(self, article: dict) -> str:
        """기사 특성에 따라 시나리오 A~E 판별

        Args:
            article: 기사 데이터 딕셔너리
                - title: 기사 제목
                - source: 출처
                - category: 카테고리
                - summary: 요약

        Returns:
            시나리오 문자 (A, B, C, D, E)
        """
        if not self.client:
            # API 없으면 카테고리 기반 기본 판별
            category = article.get("category", "").lower()
            if category == "research":
                return "B"
            elif category in ("bigtech", "news", "vc"):
                return "A"
            else:
                return "D"

        prompt = self.SCENARIO_DETECT_PROMPT.format(
            title=article.get("title", ""),
            source=article.get("source", ""),
            category=article.get("category", ""),
            summary=article.get("summary", "")[:500]
        )

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.content[0].text.strip()

            # 시나리오 추출
            for line in result.split("\n"):
                if "시나리오:" in line:
                    scenario = line.split(":")[-1].strip().upper()
                    if scenario in ["A", "B", "C", "D", "E"]:
                        return scenario

            # 첫 글자가 A-E인 경우
            first_char = result[0].upper() if result else "D"
            if first_char in ["A", "B", "C", "D", "E"]:
                return first_char

            return "D"  # 기본값

        except Exception as e:
            print(f"시나리오 판별 실패: {e}")
            return "D"

    def generate_draft(self, article: dict, scenario: str = None) -> tuple[str, str]:
        """지침서에 따라 LinkedIn 초안 생성

        Args:
            article: 기사 데이터 딕셔너리
            scenario: 시나리오 (None이면 자동 판별)

        Returns:
            (초안 텍스트, 시나리오) 튜플
        """
        if not self.client:
            return ("API 키가 설정되지 않았습니다.", "D")

        # 시나리오 자동 판별
        if not scenario:
            scenario = self.detect_scenario(article)
            print(f"  시나리오 판별: {scenario}")

        # 해당 시나리오의 프롬프트 선택
        prompt_template = self.DRAFT_PROMPTS.get(scenario, self.DRAFT_PROMPTS["D"])

        prompt = prompt_template.format(
            title=article.get("title", ""),
            source=article.get("source", ""),
            summary=article.get("summary", "")[:1000],
            guidelines=self.guidelines
        )

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}]
            )

            draft = response.content[0].text.strip()
            return (draft, scenario)

        except Exception as e:
            print(f"초안 생성 실패: {e}")
            return (f"초안 생성 중 오류 발생: {e}", scenario)

    def generate_draft_with_context(
        self,
        article: dict,
        additional_context: str = "",
        scenario: str = None
    ) -> tuple[str, str]:
        """추가 맥락을 포함한 LinkedIn 초안 생성

        Args:
            article: 기사 데이터 딕셔너리
            additional_context: 추가 맥락 (예: 관련 기사 요약)
            scenario: 시나리오 (None이면 자동 판별)

        Returns:
            (초안 텍스트, 시나리오) 튜플
        """
        if not self.client:
            return ("API 키가 설정되지 않았습니다.", "D")

        # 시나리오 자동 판별
        if not scenario:
            scenario = self.detect_scenario(article)

        # 기본 프롬프트
        prompt_template = self.DRAFT_PROMPTS.get(scenario, self.DRAFT_PROMPTS["D"])

        prompt = prompt_template.format(
            title=article.get("title", ""),
            source=article.get("source", ""),
            summary=article.get("summary", "")[:1000],
            guidelines=self.guidelines
        )

        # 추가 맥락 포함
        if additional_context:
            prompt += f"\n\n## 추가 맥락\n{additional_context}"

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}]
            )

            draft = response.content[0].text.strip()
            return (draft, scenario)

        except Exception as e:
            print(f"초안 생성 실패: {e}")
            return (f"초안 생성 중 오류 발생: {e}", scenario)
