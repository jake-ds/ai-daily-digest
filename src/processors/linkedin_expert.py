"""링크드인 콘텐츠 전문가 Agent - 글감 선정 전문"""

import os
import json
from typing import TYPE_CHECKING, Optional
from dataclasses import dataclass

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

if TYPE_CHECKING:
    from ..collectors.rss_collector import Article


@dataclass
class LinkedInCandidate:
    """링크드인 글감 후보"""
    article_url: str
    score: float          # 0-10
    verdict: str          # "추천", "보류", "탈락"
    reason: str           # 한 줄 이유
    angle: str            # 추천 각도
    hook: str             # 오프닝 훅 아이디어


class LinkedInExpert:
    """링크드인 콘텐츠 큐레이터 - 글감 선정 전문가

    초기 단계에서 대량의 기사를 빠르게 스크리닝하여
    링크드인에 적합한 글감을 선별합니다.
    """

    # 1차 스크리닝: 빠른 필터링 (배치 처리)
    SCREENING_PROMPT = """당신은 링크드인 콘텐츠 큐레이터입니다.
AI/Tech 업계 종사자들이 관심 가질 만한 글감을 찾아야 합니다.

## 당신의 기준
- 빅테크의 새 기능/발표보다 "왜 이게 나왔는지" 맥락이 있는 것
- 논문 중에서도 실무자가 이해하고 적용할 수 있는 것
- 업계 트렌드를 보여주는 숫자나 사례가 있는 것
- 논쟁거리가 있어서 댓글이 달릴 만한 것
- "그래서 뭐?" 하고 넘기지 않을 만한 것

## 탈락 기준 (이런 건 바로 탈락)
- 단순 제품 출시 발표 (새 버전, 새 기능)
- 너무 기술적이라 설명이 어려운 논문
- 이미 많이 알려진 뻔한 내용
- 한국 독자가 관심 없을 지역 뉴스
- 스캔들/가십성 기사 (단, 업계 시사점이 있으면 예외)

## 평가할 기사들
{articles}

## 응답 형식 (JSON 배열)
각 기사에 대해:
```json
[
  {{
    "index": 0,
    "score": 7.5,
    "verdict": "추천",
    "reason": "한 줄로 왜 추천/탈락인지"
  }},
  ...
]
```

verdict는 "추천"(7점 이상), "보류"(5-7점), "탈락"(5점 미만) 중 하나.
JSON만 응답해주세요."""

    # 2차 심층 평가: 상위 후보 정밀 분석
    DEEP_EVAL_PROMPT = """당신은 링크드인 콘텐츠 전문가입니다.
이 기사가 링크드인 포스트로 얼마나 좋은 글감인지 심층 평가해주세요.

## 기사 정보
제목: {title}
출처: {source}
카테고리: {category}
요약: {summary}

## 평가 기준

### 1. 토론 유발력 (0-10)
- 사람들이 자기 경험/의견을 댓글로 달고 싶어질까?
- "나도 그런 경험 있어", "나는 다르게 생각해" 반응이 나올까?

### 2. 설명 가능성 (0-10)
- 비전문가에게 쉽게 설명할 수 있는 주제인가?
- 복잡한 배경지식 없이 핵심을 전달할 수 있나?

### 3. 시의성 (0-10) - 데일리 포스트의 핵심!
- 오늘/이번 주에 나온 뉴스인가? (최근 48시간이면 가산점)
- 다른 매체에서도 다루고 있는 화제인가?
- "지금 안 올리면 늦는다"는 느낌이 있나?

점수 기준:
- 9-10: 오늘 터진 빅뉴스
- 7-8: 이번 주 핫이슈
- 5-6: 관심 가는 주제지만 급하지 않음
- 3-4: evergreen 콘텐츠

### 4. 독창적 각도 (0-10)
- 뻔하지 않은 관점으로 풀어낼 수 있나?
- 남들이 안 하는 이야기를 할 수 있나?

### 5. 공유 욕구 (0-10)
- 읽고 나서 동료에게 "이거 봤어?" 하고 보내고 싶나?
- 내 프로필에 올려서 전문성을 보여주고 싶나?

## Hook 작성 가이드 (매우 중요)
LinkedIn에서 첫 3줄이 "더보기" 전에 보입니다. 스크롤을 멈추게 하는 Hook이 필요합니다.

효과적인 Hook 패턴 (이 중 하나 사용):
1. 숫자로 시작: "M4 Max에서 초당 464 토큰." / "3일 만에 10만 다운로드."
2. 의외성/질문: "AI에게 SSH 권한 줘도 될까?" / "왜 다들 RAG를 버리고 있을까?"
3. 대비: "기존에는 3시간. 이제는 3분."
4. 상황 공감: "팀마다 다른 AI 도구, 다른 방식. 혹시 이런 고민 있으신가요?"
5. 직접적 발견: "흥미로운 연구를 발견했습니다."

피해야 할 Hook (절대 사용 금지):
- ❌ "AI 시대, ~의 활용법" (2015년 제목 같음)
- ❌ "~가 주목됩니다", "~가 화제입니다" (피동형)
- ❌ "새로운 지평을 열다", "패러다임 전환" (거창함)
- ❌ "오늘은 ~에 대해 이야기해보겠습니다" (지루함)

## 응답 형식 (JSON)
```json
{{
  "discussion_trigger": 8,
  "explainability": 7,
  "timeliness": 6,
  "unique_angle": 7,
  "shareability": 8,
  "total_score": 7.2,
  "verdict": "추천",
  "angle": "이 기사를 어떤 관점/질문으로 풀어갈지 (1문장)",
  "hook": "위 패턴 중 하나로 작성한 Hook (1-2문장, 구체적 숫자나 질문 포함)",
  "reason": "왜 이 글감이 좋은지/아쉬운지 솔직하게 (1-2문장)"
}}
```

JSON만 응답해주세요."""

    # 기사 그룹핑: 연관 주제 분석
    GROUPING_PROMPT = """당신은 AI/Tech 뉴스 분석가입니다.
아래 기사들을 연관 주제별로 그룹핑해주세요.

## 기사 목록
{articles}

## 그룹핑 기준
- 같은 기술 분야 (예: LLM, Agent, Vision)
- 같은 회사/조직 관련
- 같은 트렌드/흐름 (예: 오픈소스 경쟁, 모델 경량화)
- 같은 문제/과제 (예: 비용 절감, 성능 개선)

## 응답 형식 (JSON)
```json
{{
  "groups": [
    {{
      "theme": "그룹 주제 (예: 'AI Agent 경쟁 심화')",
      "keyword": "핵심 키워드 (예: 'Agent')",
      "article_indices": [0, 2, 5],
      "connection": "이 기사들의 연결고리 설명 (1문장)"
    }},
    ...
  ],
  "ungrouped": [1, 3]
}}
```

규칙:
- 최소 3개 이상 기사가 묶여야 그룹으로 인정
- 2개 이하는 ungrouped로 분류
- 하나의 기사는 하나의 그룹에만 속함
- 가장 큰 그룹을 첫 번째로 배치

JSON만 응답해주세요."""

    def __init__(self):
        self.client = None
        if Anthropic and os.getenv("ANTHROPIC_API_KEY"):
            self.client = Anthropic()

    def _format_articles_for_screening(self, articles: list["Article"]) -> str:
        """스크리닝용 기사 목록 포맷"""
        lines = []
        for i, article in enumerate(articles):
            summary = article.ai_summary or article.summary or ""
            summary = summary[:200].replace("\n", " ")
            lines.append(f"[{i}] {article.title}")
            lines.append(f"    출처: {article.source} | 카테고리: {article.category}")
            lines.append(f"    요약: {summary}")
            lines.append("")
        return "\n".join(lines)

    def screen_articles(
        self,
        articles: list["Article"],
        batch_size: int = 15
    ) -> list[tuple["Article", dict]]:
        """1차 스크리닝: 대량 기사 빠르게 필터링

        Args:
            articles: 스크리닝할 기사 목록
            batch_size: 한 번에 처리할 기사 수

        Returns:
            (기사, 평가결과) 튜플 리스트 (점수순 정렬)
        """
        if not self.client:
            print("  LinkedIn Expert: API 키 없음, 스킵")
            return [(a, {"score": 5, "verdict": "보류", "reason": "API 없음"}) for a in articles]

        all_results = []

        # 배치 처리
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i+batch_size]
            batch_text = self._format_articles_for_screening(batch)

            prompt = self.SCREENING_PROMPT.format(articles=batch_text)

            try:
                response = self.client.messages.create(
                    model="claude-3-5-haiku-20241022",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}]
                )

                result_text = response.content[0].text.strip()

                # JSON 파싱
                if "```json" in result_text:
                    result_text = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    result_text = result_text.split("```")[1].split("```")[0]

                evaluations = json.loads(result_text.strip())

                # 결과 매핑
                for eval_item in evaluations:
                    idx = eval_item.get("index", 0)
                    if idx < len(batch):
                        all_results.append((batch[idx], eval_item))

            except Exception as e:
                print(f"  스크리닝 배치 실패: {e}")
                # 실패한 배치는 기본 점수로
                for article in batch:
                    all_results.append((article, {
                        "score": 5,
                        "verdict": "보류",
                        "reason": "평가 실패"
                    }))

        # 점수순 정렬
        all_results.sort(key=lambda x: x[1].get("score", 0), reverse=True)

        return all_results

    # 평가 가중치
    EVAL_WEIGHTS = {
        "timeliness": 2.5,        # 시의성 2.5배 강화
        "discussion_trigger": 1.5,
        "shareability": 1.5,
        "explainability": 1.0,
        "unique_angle": 1.0,
    }

    def deep_evaluate(self, article: "Article") -> Optional[LinkedInCandidate]:
        """2차 심층 평가: 개별 기사 정밀 분석"""
        if not self.client:
            return None

        prompt = self.DEEP_EVAL_PROMPT.format(
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

            result_text = response.content[0].text.strip()

            # JSON 파싱
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            data = json.loads(result_text.strip())

            # 가중치 적용된 점수 계산
            weighted_score = self._calculate_weighted_score(data)

            return LinkedInCandidate(
                article_url=article.url,
                score=weighted_score,
                verdict=data.get("verdict", "보류"),
                reason=data.get("reason", ""),
                angle=data.get("angle", ""),
                hook=data.get("hook", "")
            )

        except Exception as e:
            print(f"  심층평가 실패 [{article.title[:30]}]: {e}")
            return None

    def _calculate_weighted_score(self, data: dict) -> float:
        """가중치 적용된 점수 계산"""
        scores = {
            "timeliness": data.get("timeliness", 5),
            "discussion_trigger": data.get("discussion_trigger", 5),
            "shareability": data.get("shareability", 5),
            "explainability": data.get("explainability", 5),
            "unique_angle": data.get("unique_angle", 5),
        }

        total_weight = sum(self.EVAL_WEIGHTS.values())
        weighted_sum = sum(
            scores[key] * self.EVAL_WEIGHTS[key]
            for key in scores
        )

        return round(weighted_sum / total_weight, 1)

    def group_articles_by_theme(
        self,
        candidates: list[tuple["Article", "LinkedInCandidate"]],
        min_group_size: int = 3
    ) -> list[list[tuple["Article", "LinkedInCandidate"]]]:
        """연관 주제별 기사 그룹핑

        Args:
            candidates: (기사, 평가결과) 튜플 리스트
            min_group_size: 그룹으로 인정할 최소 기사 수

        Returns:
            그룹별 기사 리스트 (크기 순 정렬)
        """
        if not self.client or len(candidates) < min_group_size:
            return [candidates]

        # 기사 목록 포맷
        articles_text = []
        for i, (article, _) in enumerate(candidates):
            summary = article.ai_summary or article.summary or ""
            summary = summary[:150].replace("\n", " ")
            articles_text.append(f"[{i}] {article.title}")
            articles_text.append(f"    요약: {summary}")
            articles_text.append("")

        prompt = self.GROUPING_PROMPT.format(articles="\n".join(articles_text))

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()

            # JSON 파싱
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            data = json.loads(result_text.strip())

            # 그룹별 기사 매핑
            groups = []
            used_indices = set()

            for group_info in data.get("groups", []):
                indices = group_info.get("article_indices", [])
                if len(indices) >= min_group_size:
                    group = []
                    for idx in indices:
                        if idx < len(candidates) and idx not in used_indices:
                            group.append(candidates[idx])
                            used_indices.add(idx)
                    if len(group) >= min_group_size:
                        # 그룹에 테마 정보 저장 (첫 번째 아이템의 candidate에)
                        groups.append((group, group_info.get("keyword", "")))

            # 그룹에 속하지 않은 기사들
            ungrouped = [
                candidates[i] for i in range(len(candidates))
                if i not in used_indices
            ]

            # 크기 순 정렬 (큰 그룹 먼저)
            groups.sort(key=lambda x: len(x[0]), reverse=True)

            # 결과 반환 (그룹만, 키워드 정보는 별도 저장)
            result = []
            self._group_keywords = {}  # 그룹별 키워드 저장
            for i, (group, keyword) in enumerate(groups):
                result.append(group)
                self._group_keywords[i] = keyword

            if ungrouped:
                result.append(ungrouped)
                self._group_keywords[len(result) - 1] = ""

            print(f"   그룹핑 완료: {len(groups)}개 그룹, {len(ungrouped)}개 미분류")
            for i, (group, keyword) in enumerate(groups):
                print(f"     그룹 {i+1} ({keyword}): {len(group)}개 기사")

            return result

        except Exception as e:
            print(f"   그룹핑 실패: {e}")
            return [candidates]

    def get_group_keyword(self, group_index: int) -> str:
        """그룹의 트렌드 키워드 반환"""
        return getattr(self, '_group_keywords', {}).get(group_index, "")

    def curate_linkedin_candidates(
        self,
        articles: list["Article"],
        screen_top_n: int = 50,
        final_top_n: int = 5,
        ensure_diversity: bool = True
    ) -> list[tuple["Article", LinkedInCandidate]]:
        """링크드인 글감 큐레이션 전체 파이프라인

        Args:
            articles: 전체 기사 목록
            screen_top_n: 1차 스크리닝 대상 수
            final_top_n: 최종 선정 수
            ensure_diversity: 카테고리 다양성 보장 여부

        Returns:
            (기사, 평가결과) 튜플 리스트
        """
        print(f"\n📋 LinkedIn Expert: 글감 큐레이션 시작")
        print(f"   대상: {len(articles)}개 → 스크리닝: {screen_top_n}개 → 최종: {final_top_n}개")

        # 1단계: 스크리닝 대상 선정 (키워드 점수 상위 + 카테고리 다양성)
        screening_pool = self._select_screening_pool(articles, screen_top_n)
        print(f"   1차 풀 선정: {len(screening_pool)}개")

        # 2단계: 1차 스크리닝
        print(f"   1차 스크리닝 중...")
        screened = self.screen_articles(screening_pool)

        # "추천" 또는 "보류" 중 상위 점수 기사 선별 (기준 완화)
        recommended = [
            (a, e) for a, e in screened
            if e.get("verdict") in ["추천", "보류"] or e.get("score", 0) >= 5.5
        ]
        print(f"   1차 통과: {len(recommended)}개")

        # 3단계: 다양성 보장하며 심층 평가 대상 선정
        if ensure_diversity:
            deep_eval_targets = self._ensure_diversity(recommended, final_top_n * 2)
        else:
            deep_eval_targets = [a for a, _ in recommended[:final_top_n * 2]]

        # 4단계: 심층 평가
        print(f"   2차 심층 평가 중... ({len(deep_eval_targets)}개)")
        final_candidates = []
        news_categories = {"bigtech", "vc", "news", "community", "korean"}

        for article in deep_eval_targets:
            candidate = self.deep_evaluate(article)
            if candidate:
                # 뉴스 카테고리는 좀 더 관대하게 (다양성 확보)
                if article.category in news_categories:
                    # 탈락이어도 점수 페널티만 주고 포함
                    if candidate.verdict == "탈락":
                        candidate.score = max(4.0, candidate.score - 2)
                    final_candidates.append((article, candidate))
                else:
                    # research는 추천/보류만
                    if candidate.verdict in ["추천", "보류"]:
                        final_candidates.append((article, candidate))

        # 점수순 정렬
        final_candidates.sort(key=lambda x: x[1].score, reverse=True)

        # 최종 다양성 보장
        if ensure_diversity:
            final_candidates = self._final_diversity_filter(
                final_candidates, final_top_n
            )
        else:
            final_candidates = final_candidates[:final_top_n]

        print(f"   ✅ 최종 선정: {len(final_candidates)}개")

        return final_candidates

    def _select_screening_pool(
        self,
        articles: list["Article"],
        n: int
    ) -> list["Article"]:
        """스크리닝 대상 선정 (카테고리 다양성 고려)"""
        from collections import defaultdict

        # 카테고리별 그룹화
        by_category = defaultdict(list)
        for article in articles:
            by_category[article.category].append(article)

        # 각 카테고리에서 점수순 정렬
        for cat in by_category:
            by_category[cat].sort(key=lambda x: x.score, reverse=True)

        # 카테고리별 최소 할당
        min_per_category = {
            "bigtech": 8,
            "vc": 8,
            "news": 10,
            "research": 10,
            "community": 8,
            "korean": 8,
        }

        selected = []
        used_urls = set()

        # 1단계: 카테고리별 최소 할당
        for cat, min_count in min_per_category.items():
            for article in by_category.get(cat, [])[:min_count]:
                if article.url not in used_urls:
                    selected.append(article)
                    used_urls.add(article.url)

        # 2단계: 나머지는 점수순
        all_sorted = sorted(articles, key=lambda x: x.score, reverse=True)
        for article in all_sorted:
            if len(selected) >= n:
                break
            if article.url not in used_urls:
                selected.append(article)
                used_urls.add(article.url)

        return selected

    def _ensure_diversity(
        self,
        candidates: list[tuple["Article", dict]],
        n: int
    ) -> list["Article"]:
        """심층 평가 대상 다양성 보장

        research 최소 3개, news 최소 3개 포함
        """
        # 뉴스 그룹 (research 제외)
        news_categories = {"bigtech", "vc", "news", "community", "korean"}

        selected = []
        used_urls = set()

        # research 최소 3개
        research_count = 0
        for article, _ in candidates:
            if article.category == "research" and research_count < 3:
                selected.append(article)
                used_urls.add(article.url)
                research_count += 1

        # news 최소 3개 (더 적극적으로)
        news_count = 0
        for article, _ in candidates:
            if article.category in news_categories and news_count < 3:
                if article.url not in used_urls:
                    selected.append(article)
                    used_urls.add(article.url)
                    news_count += 1

        print(f"   다양성 보장: research {research_count}개, news {news_count}개")

        # 나머지는 점수순
        for article, _ in candidates:
            if len(selected) >= n:
                break
            if article.url not in used_urls:
                selected.append(article)
                used_urls.add(article.url)

        return selected

    def _final_diversity_filter(
        self,
        candidates: list[tuple["Article", "LinkedInCandidate"]],
        n: int
    ) -> list[tuple["Article", "LinkedInCandidate"]]:
        """최종 선정 다양성 필터

        최소 1개 research, 최소 1개 news 보장
        """
        news_categories = {"bigtech", "vc", "news", "community", "korean"}

        selected = []
        has_research = False
        has_news = False
        used_urls = set()

        # 1단계: research 1개 보장 (점수 상관없이)
        for article, candidate in candidates:
            if article.category == "research" and not has_research:
                selected.append((article, candidate))
                used_urls.add(article.url)
                has_research = True
                break

        # 2단계: news 1개 보장 (점수 상관없이)
        for article, candidate in candidates:
            if article.category in news_categories and not has_news:
                if article.url not in used_urls:
                    selected.append((article, candidate))
                    used_urls.add(article.url)
                    has_news = True
                    break

        # 뉴스가 candidates에 없으면 경고
        if not has_news:
            print(f"   ⚠️ 경고: 뉴스 카테고리 후보가 없습니다")

        # 3단계: 나머지 점수순
        for article, candidate in candidates:
            if len(selected) >= n:
                break
            if article.url not in used_urls:
                selected.append((article, candidate))
                used_urls.add(article.url)

        # 점수순 재정렬
        selected.sort(key=lambda x: x[1].score, reverse=True)

        return selected

    def print_curation_report(
        self,
        candidates: list[tuple["Article", "LinkedInCandidate"]]
    ):
        """큐레이션 결과 리포트"""
        print("\n" + "=" * 60)
        print("📊 LinkedIn Expert 큐레이션 리포트")
        print("=" * 60)

        for i, (article, candidate) in enumerate(candidates, 1):
            print(f"\n🎯 #{i} (점수: {candidate.score}/10) [{candidate.verdict}]")
            print(f"제목: {article.title[:55]}...")
            print(f"카테고리: {article.category} | 출처: {article.source}")
            print(f"├─ 이유: {candidate.reason[:60]}...")
            print(f"├─ 각도: {candidate.angle[:60]}...")
            print(f"└─ 훅: {candidate.hook[:60]}...")

        print("\n" + "=" * 60)
