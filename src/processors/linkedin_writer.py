"""링크드인 포스트 작성 Agent - 웹 리서치 기반"""

import os
import re
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    import httpx
except ImportError:
    httpx = None

if TYPE_CHECKING:
    from ..collectors.rss_collector import Article
    from .evaluator import ArticleEvaluation


@dataclass
class LinkedInPost:
    """링크드인 포스트"""
    article_title: str
    article_url: str
    evaluation_score: float
    post_content: str
    hashtags: list[str]
    estimated_read_time: str
    call_to_action: str
    # 신규 필드
    is_synthesis: bool = False          # 종합 포스트 여부
    source_articles: list[str] = None   # 종합 시 원본 기사들
    trend_keyword: str = ""             # 트렌드 키워드


class LinkedInWriter:
    """평가된 기사를 기반으로 링크드인 포스트 작성"""

    POST_PROMPT = """당신은 흥미로운 걸 발견하면 나누고 싶어하는 사람입니다.
잘난 척 하지 않고, "오 이런 게 있네요?" 하는 톤으로 겸손하게 공유합니다.

## 작성자 프로필
- AI와 스타트업에 관심이 많은 사람
- 발견한 것을 독자와 함께 생각하며 공유하는 스타일
- 정보를 충실히 전달하되, 혼자 떠드는 게 아니라 대화하는 느낌
- 과장 없이 사실 위주, 하지만 "사람"이 느껴지는 글

## 포스트 대상 기사
제목: {title}
출처: {source}
요약: {summary}

## 평가 정보
- 추천 각도: {angle}
- 핵심 인사이트: {insight}
- 타겟 독자: {audience}
- 오프닝 훅: {hook}

## 글쓰기 원칙 (매우 중요)

### 1. Hook (첫 3줄) - 스크롤을 멈추게 하기
LinkedIn에서 첫 3줄이 "더보기" 전에 보입니다. 이 3줄이 클릭을 결정합니다.

효과적인 Hook 패턴:
- 숫자로 시작: "M4 Max에서 초당 464 토큰." / "3일 만에 10만 다운로드."
- 의외성/질문: "AI에게 SSH 권한 줘도 될까?" / "왜 다들 RAG를 버리고 있을까?"
- 대비: "기존에는 3시간. 이제는 3분." / "작년엔 불가능했던 게 올해는 기본이 됐습니다."
- 상황 공감: "팀마다 다른 AI 도구, 다른 방식으로 사용하는 문제. 혹시 이런 고민 있으신가요?"
- 직접적 발견: "흥미로운 연구를 발견했습니다." / "이런 접근이 있네요."

피해야 할 Hook:
- ❌ "AI 시대, 팀의 똑똑한 기술 활용법" (2015년 제목 같음)
- ❌ "~가 주목됩니다" (피동형, 누가 주목?)
- ❌ "새로운 지평을 열다" (거창함)

### 2. 글 구조 (문단 흐름 중심)
- Hook (3줄) → 맥락/배경 → 핵심 내용 (문단 흐름) → **나의 생각** → 질문
- 번호 리스트는 3개 이상의 독립적 포인트가 있을 때만, 그래도 최대 3개까지
- 가능하면 "첫째, 둘째" 대신 문단으로 자연스럽게 연결
- 문단 사이 여백으로 가독성 확보

### 3. 문체
- "~입니다", "~합니다" 종결어 사용
- 짧은 문장과 긴 문장을 섞어서 리듬감 있게
- 연결어로 논리 전개: "하지만", "그래서", "흥미로운 건"
- 이모지는 제목에만 1개, 본문에서는 사용 안 함

### 4. 톤 (핵심: 겸손한 발견 공유)

권장하는 톤:
- 겸손한 발견: "이런 연구가 나왔습니다", "흥미로운 접근이네요"
- 정보 충실: 배경, 맥락, 구체적 숫자 등 정보량 높게
- 함께 생각하기: "저도 궁금한 부분이 있는데요", "이 부분은 어떨까요?"
- 솔직한 한계 인정: "아직 정답이 있는 주제는 아닌 것 같습니다"
- 진정성 있는 마무리: 형식적이지 않은 자연스러운 질문

예시:
- "흥미로운 인사이트가 많아서 정리해봤습니다."
- "여러분 팀에서는 이 문제를 어떻게 다루고 계신가요?"
- "저도 아직 답을 모르겠는데, 경험 공유해주시면 감사하겠습니다."

### 5. 피해야 할 것 (절대 사용 금지)

잘난 척 표현:
- "제가 봤을 때", "이건 확실히", "내가 딱 보니까"

과장 수식어:
- "혁신적인", "획기적인", "게임체인저", "패러다임 전환"
- "전례 없는", "완전히 새로운", "인류 역사상"

거창한 예고:
- "새 시대를 열다", "역사를 쓰다", "미래를 바꾸다"

형식적인 마무리:
- "귀추가 주목됩니다", "앞으로가 기대됩니다"
- (단, "여러분은 어떻게 생각하세요?"는 맥락에 맞으면 사용 가능)

기타:
- 번호 리스트 4개 이상
- 해시태그 본문에 섞기
- 피동형 남용: "~가 주목됩니다", "~가 기대됩니다"

### 6. 내용
- "왜 이게 나왔는지" 배경 설명
- 기존에는 어땠는지, 뭐가 달라졌는지
- 구체적인 숫자가 있으면 언급
- 비유는 필요할 때만 간결하게

### 7. 마무리 인사이트 (필수)
포스트 마지막에 작성자 본인의 생각 1-2문장을 반드시 포함하세요.

형식 (이 중 하나 사용):
- "이 뉴스를 보면서 드는 생각은..."
- "개인적으로 주목하는 포인트는..."
- "이게 의미하는 바는..."

예시:
- "이 뉴스를 보면서 드는 생각은, 결국 'AI Native 제품'의 정의가 바뀌고 있다는 것입니다."
- "개인적으로 주목하는 포인트는, 이제 '빠른 추론'이 기본이 되고 있다는 점입니다."

금지:
- 뻔한 결론 ("앞으로가 기대됩니다", "귀추가 주목됩니다")
- 과장된 예측 ("혁명이 될 것입니다", "판도가 바뀔 것입니다")

## 좋은 예시 vs 나쁜 예시

❌ 건조하고 형식적인 글:
```
# AI 시대, 팀의 똑똑한 기술 활용법

커뮤니티에서 공유된 AI 활용 통찰이 주목됩니다.
팀 단위로 AI를 어떻게 효과적으로 도입할 수 있을까요?

주요 포인트는 세 가지입니다:
1. AI 사용 표준화
2. 맥락 특화 UX 설계
3. 초기 성과 지표 추적

당신의 팀에서는 AI 도구를 어떻게 사용하고 계신가요?
```

✅ 사람이 느껴지는 담백한 글:
```
팀마다 다른 AI 도구, 다른 방식으로 사용하는 문제.
혹시 이런 고민 있으신가요?

Lenny's Newsletter 커뮤니티에서 이 주제로 논의가 있었습니다.
흥미로운 인사이트가 많아서 정리해봤습니다.

가장 많이 언급된 문제는 '파편화'입니다.
팀원 10명이 10개의 다른 도구를 쓰면, 결과물도 제각각이 됩니다.
누가 뭘 하는지 파악하기도 어렵고요.

커뮤니티에서 제안된 해결책은 크게 세 가지였습니다.

첫째, 도구 표준화입니다. 팀에서 사용할 AI 도구를 미리 정해두는 거죠.
둘째, 가이드라인 수립입니다. 어떤 작업에 AI를 쓸지, 결과물은 어디에 모을지 등.
셋째, 성과 측정입니다. AI 도입 효과를 어떻게 측정할지 미리 정해두면 좋다고 합니다.

아직 정답이 있는 주제는 아닌 것 같습니다.
여러분 팀에서는 이 문제를 어떻게 다루고 계신가요?
```

❌ 느끼한 도입부:
"인간의 뇌는 수백만 년에 걸쳐 진화한 가장 정교한 컴퓨터입니다."

✅ 담백한 도입부:
"머지 랩스가 3700억 원 투자를 유치했습니다. 오픈AI가 최대 투자자입니다."

## 글 길이
- 1200-1800자 (충분한 깊이를 위해)
- 스크롤 5-7번 정도

## 응답 형식
[포스트 본문]

---
해시태그: #tag1 #tag2 #tag3 (3-5개, 핵심 키워드만)
핵심질문: [독자가 자연스럽게 의견을 남기고 싶어지는 진정성 있는 질문]"""

    RESEARCH_PROMPT = """다음 기사/논문에 대해 배경 맥락을 조사해주세요.

## 대상
제목: {title}
출처: {source}
카테고리: {category}
요약: {summary}

## 조사할 내용
1. **기존 접근법**: 이 분야에서 기존에는 어떤 방법들이 있었는가?
2. **문제점/한계**: 기존 방법의 어떤 문제를 해결하려는 것인가?
3. **새로운 점**: 이 연구/제품/발표의 핵심 차별점은?
4. **관련 동향**: 최근 이 분야의 주요 트렌드나 경쟁 상황

## 응답 형식
- 기존 접근법: [2-3문장]
- 해결하려는 문제: [1-2문장]
- 핵심 차별점: [2-3문장]
- 관련 맥락: [1-2문장]

간결하게 핵심만 답변해주세요."""

    SYNTHESIS_PROMPT = """당신은 AI 업계 트렌드를 관찰하고 정리하는 사람입니다.
오늘 수집된 여러 뉴스를 종합하여 하나의 관점으로 정리합니다.

## 작성자 프로필
- AI와 스타트업에 관심이 많은 사람
- 여러 소식을 보고 흐름을 읽어내는 스타일
- 과장 없이 사실 위주, 하지만 인사이트가 있는 글

## 오늘의 주요 뉴스
{articles_summary}

## 트렌드 키워드
{trend_keyword}

## 작성 가이드

### 구조
1. Hook (3줄): "이번 주 AI 소식을 보면..." 또는 "요즘 AI 업계를 보면..." 형태로 시작
2. 개별 뉴스 요약: 각 뉴스를 2-3문장으로 소개 (문단으로 자연스럽게)
3. 연결고리: "이 뉴스들의 공통점은..." 또는 "이 흐름을 보면..."
4. 나의 해석: "이 흐름을 보면서 드는 생각은..." (필수, 1-2문장)
5. 마무리 질문

### 톤
- "이번 주 AI 소식 몇 가지를 모아봤습니다"
- "각각 다른 뉴스지만, 공통점이 보입니다"
- "개별적으로는 작은 소식이지만, 모아보면 트렌드가 보입니다"

### 금지
- "혁명", "패러다임 전환" 등 과장
- "귀추가 주목됩니다" 등 형식적 마무리
- 번호 리스트 4개 이상

### 글 길이
- 1500-2000자

## 응답 형식
[포스트 본문]

---
해시태그: #tag1 #tag2 #tag3 (3-5개)
핵심질문: [독자가 의견을 남기고 싶어지는 질문]"""

    def __init__(self):
        self.client = None
        if Anthropic and os.getenv("ANTHROPIC_API_KEY"):
            self.client = Anthropic()

    def _research_context(self, article: "Article") -> str:
        """기사에 대한 배경 맥락 조사"""
        if not self.client:
            return ""

        prompt = self.RESEARCH_PROMPT.format(
            title=article.title,
            source=article.source,
            category=article.category,
            summary=article.ai_summary or article.summary or "요약 없음"
        )

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"  리서치 실패: {e}")
            return ""

    def write_post(
        self,
        article: "Article",
        evaluation: "ArticleEvaluation",
        with_research: bool = True
    ) -> Optional[LinkedInPost]:
        """단일 기사에 대한 링크드인 포스트 작성 (리서치 포함)"""
        if not self.client:
            return None

        # 배경 맥락 리서치
        research_context = ""
        if with_research:
            print(f"    → 배경 리서치 중...")
            research_context = self._research_context(article)

        # 리서치 결과를 포함한 프롬프트 구성
        base_prompt = self.POST_PROMPT.format(
            title=article.title,
            source=article.source,
            summary=article.ai_summary or article.summary or "요약 없음",
            angle=evaluation.recommended_angle,
            insight=evaluation.key_insight,
            audience=evaluation.target_audience,
            hook=evaluation.hook_suggestion
        )

        # 리서치 결과 추가
        if research_context:
            prompt = f"""{base_prompt}

## 배경 리서치 결과 (중요: 이 맥락을 바탕으로 "새로운 점"을 강조해서 작성)
{research_context}

위 리서치 결과를 참고해서, 기존과 비교해 무엇이 새롭고 왜 중요한지 설명하는 포스트를 작성해주세요."""
        else:
            prompt = base_prompt

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.content[0].text.strip()

            # 해시태그와 CTA 파싱
            parts = result.split("---")
            post_content = parts[0].strip()

            hashtags = []
            cta = ""

            if len(parts) > 1:
                metadata = parts[1]
                for line in metadata.split("\n"):
                    if "해시태그:" in line:
                        tags = line.replace("해시태그:", "").strip()
                        hashtags = [t.strip() for t in tags.split("#") if t.strip()]
                    elif "핵심질문:" in line:
                        cta = line.replace("핵심질문:", "").strip()
                    elif "CTA:" in line:
                        cta = line.replace("CTA:", "").strip()

            # 예상 읽기 시간
            char_count = len(post_content)
            read_time = f"{max(1, char_count // 500)}분"

            return LinkedInPost(
                article_title=article.title,
                article_url=article.url,
                evaluation_score=evaluation.ai_score,
                post_content=post_content,
                hashtags=hashtags[:7],
                estimated_read_time=read_time,
                call_to_action=cta
            )

        except Exception as e:
            print(f"포스트 작성 실패 [{article.title[:30]}]: {e}")
            return None

    def write_synthesis_post(
        self,
        articles: list["Article"],
        trend_keyword: str = ""
    ) -> Optional[LinkedInPost]:
        """여러 기사를 종합한 인사이트 포스트 작성

        Args:
            articles: 종합할 기사들
            trend_keyword: 트렌드 키워드 (예: "Agent", "LLM")

        Returns:
            종합 인사이트 포스트
        """
        if not self.client or len(articles) < 2:
            return None

        # 기사 요약 정리
        articles_summary = []
        source_urls = []
        for i, article in enumerate(articles, 1):
            summary = article.ai_summary or article.summary or ""
            summary = summary[:200].replace("\n", " ")
            articles_summary.append(f"{i}. {article.title}")
            articles_summary.append(f"   출처: {article.source}")
            articles_summary.append(f"   요약: {summary}")
            articles_summary.append("")
            source_urls.append(article.url)

        prompt = self.SYNTHESIS_PROMPT.format(
            articles_summary="\n".join(articles_summary),
            trend_keyword=trend_keyword or "AI 트렌드"
        )

        try:
            print(f"    → 종합 포스트 작성 중 ({len(articles)}개 기사)...")
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.content[0].text.strip()

            # 해시태그와 CTA 파싱
            parts = result.split("---")
            post_content = parts[0].strip()

            hashtags = []
            cta = ""

            if len(parts) > 1:
                metadata = parts[1]
                for line in metadata.split("\n"):
                    if "해시태그:" in line:
                        tags = line.replace("해시태그:", "").strip()
                        hashtags = [t.strip() for t in tags.split("#") if t.strip()]
                    elif "핵심질문:" in line:
                        cta = line.replace("핵심질문:", "").strip()

            # 예상 읽기 시간
            char_count = len(post_content)
            read_time = f"{max(1, char_count // 500)}분"

            # 첫 번째 기사 제목을 대표로 사용
            combined_title = f"[종합] {trend_keyword or 'AI'} 트렌드 분석"

            return LinkedInPost(
                article_title=combined_title,
                article_url=source_urls[0] if source_urls else "",
                evaluation_score=8.0,  # 종합 포스트는 고정 점수
                post_content=post_content,
                hashtags=hashtags[:7],
                estimated_read_time=read_time,
                call_to_action=cta,
                is_synthesis=True,
                source_articles=source_urls,
                trend_keyword=trend_keyword
            )

        except Exception as e:
            print(f"종합 포스트 작성 실패: {e}")
            return None

    def write_posts_for_candidates(
        self,
        candidates: list[tuple["Article", "ArticleEvaluation"]],
        top_n: int = 3
    ) -> list[LinkedInPost]:
        """상위 후보들에 대한 포스트 작성"""
        posts = []

        print(f"\n링크드인 포스트 작성 중 (상위 {min(top_n, len(candidates))}개)...")

        for i, (article, evaluation) in enumerate(candidates[:top_n]):
            print(f"  [{i+1}] {article.title[:40]}...")
            post = self.write_post(article, evaluation)
            if post:
                posts.append(post)

        print(f"포스트 작성 완료: {len(posts)}개")
        return posts

    def format_post_for_output(self, post: LinkedInPost, index: int = 1) -> str:
        """출력용 포스트 포맷팅"""
        lines = [
            f"### 포스트 #{index} (평가점수: {post.evaluation_score}/10)",
            f"**원문:** [{post.article_title[:50]}...]({post.article_url})",
            f"**예상 읽기 시간:** {post.estimated_read_time}",
            "",
            "```",
            post.post_content,
            "```",
            "",
            f"**해시태그:** {' '.join(['#' + t for t in post.hashtags])}",
            f"**CTA:** {post.call_to_action}",
            ""
        ]
        return "\n".join(lines)
