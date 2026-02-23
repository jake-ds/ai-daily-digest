"""기사 평가 Agent - 링크드인 포스팅 가치 분석"""

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
class ArticleEvaluation:
    """기사 평가 결과"""
    article_title: str
    article_url: str

    # 평가 점수 (0-10) — 7차원 통일
    curiosity: float               # 클릭/관심 유발력
    insight: float                 # 실질적 인사이트 깊이
    relevance: float               # AI/Tech 업계 관련성
    timeliness: float              # 시의성
    discussion: float              # 토론 유발 가능성
    shareability: float            # 공유 가치
    depth: float                   # 맥락/시사점 해석 가능성

    # 종합
    ai_score: float                # 가중 평균 종합 점수
    linkedin_potential: float      # LinkedIn 특화 가중 평균
    key_insight: str               # 핵심 인사이트
    hook_suggestion: str           # 오프닝 훅 제안


class ArticleEvaluator:
    """기사를 다양한 관점에서 평가하는 전문 Agent"""

    EVALUATION_PROMPT = """당신은 AI/Tech 트렌드를 팔로우하는 사람입니다. 링크드인에서 공유할 만한 콘텐츠인지 평가합니다.

## 평가 대상
제목: {title}
출처: {source}
카테고리: {category}
요약: {summary}

## 평가자 프로필
- AI와 스타트업에 관심이 많은 사람
- 과장된 마케팅 톤 싫어함
- 실용적인 인사이트와 흥미로운 발견을 좋아함
- "혁신적", "획기적" 같은 단어 쓰는 글은 패스

## 평가 기준 (각 0-10점)

1. curiosity: 제목만 봐도 "어? 이거 뭐지?" 하고 궁금해지는가?
   - 높음: 클릭 안 하고는 못 배기는 주제
   - 낮음: "그렇구나" 하고 스크롤

2. insight: 읽는 사람이 뭔가 얻어가는 게 있는가?
   - 높음: 새로운 시각, 유용한 정보, 써먹을 수 있는 팁
   - 낮음: 그냥 뉴스 전달

3. relevance: AI/Tech 업계 종사자에게 관련 있는가?
   - 높음: 업계 전반에 영향, 실무에 바로 적용 가능
   - 낮음: 특수한 니치 주제

4. timeliness: 지금 이 타이밍에 공유해야 하는 이유가 있는가?
   - 높음: 방금 나온 소식, 업계에서 화제인 주제
   - 낮음: 언제 올려도 상관없는 내용

5. discussion: 사람들이 자기 의견을 말하고 싶어질 만한가?
   - 높음: "나는 좀 다르게 생각하는데...", "이거 써봤는데..."
   - 낮음: 동의/반대할 여지가 없는 팩트 나열

6. shareability: 다른 사람에게 "이거 봤어?" 하고 공유하고 싶은가?
   - 높음: 동료한테 슬랙으로 보내고 싶음
   - 낮음: 혼자 읽고 끝

7. depth: 단순 요약을 넘어서 "왜 중요한지" 설명할 수 있는가?
   - 높음: 맥락과 시사점을 풀어낼 수 있음
   - 낮음: 있는 그대로 전달하는 게 전부

## 응답 형식 (JSON)
```json
{{
  "curiosity": 7,
  "insight": 8,
  "relevance": 7,
  "timeliness": 6,
  "discussion": 7,
  "shareability": 6,
  "depth": 8,
  "key_insight": "뻔하지 않은, 이 기사만의 핵심 포인트 한 문장",
  "hook_suggestion": "스크롤 멈추게 하는 첫 문장 (과장 없이, 호기심 유발)"
}}
```

JSON만 응답해주세요."""

    # ai_score 가중치
    AI_SCORE_WEIGHTS = {
        "curiosity": 1.5,
        "insight": 2.0,
        "relevance": 1.5,
        "timeliness": 1.0,
        "discussion": 1.0,
        "shareability": 1.0,
        "depth": 1.5,
    }

    # linkedin_potential 가중치
    LINKEDIN_WEIGHTS = {
        "curiosity": 1.5,
        "insight": 1.0,
        "discussion": 2.0,
        "shareability": 2.0,
        "depth": 1.0,
    }

    def __init__(self):
        self.client = None
        if Anthropic and os.getenv("ANTHROPIC_API_KEY"):
            self.client = Anthropic()

    @staticmethod
    def calculate_scores(data: dict) -> tuple:
        """(ai_score, linkedin_potential) 가중 평균 계산"""
        # ai_score: 전체 7차원 가중 평균
        ai_weights = ArticleEvaluator.AI_SCORE_WEIGHTS
        ai_total_weight = sum(ai_weights.values())
        ai_score = sum(
            data.get(key, 5) * weight
            for key, weight in ai_weights.items()
        ) / ai_total_weight

        # linkedin_potential: LinkedIn engagement 특화 가중 평균
        li_weights = ArticleEvaluator.LINKEDIN_WEIGHTS
        li_total_weight = sum(li_weights.values())
        linkedin_potential = sum(
            data.get(key, 5) * weight
            for key, weight in li_weights.items()
        ) / li_total_weight

        return round(ai_score, 1), round(linkedin_potential, 1)

    def evaluate_article(self, article: "Article") -> Optional[ArticleEvaluation]:
        """단일 기사 평가"""
        if not self.client:
            return None

        prompt = self.EVALUATION_PROMPT.format(
            title=article.title,
            source=article.source,
            category=article.category,
            summary=article.ai_summary or article.summary or "요약 없음"
        )

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()

            # JSON 파싱
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            data = json.loads(result_text.strip())

            ai_score, linkedin_potential = self.calculate_scores(data)

            return ArticleEvaluation(
                article_title=article.title,
                article_url=article.url,
                curiosity=data.get("curiosity", 5),
                insight=data.get("insight", 5),
                relevance=data.get("relevance", 5),
                timeliness=data.get("timeliness", 5),
                discussion=data.get("discussion", 5),
                shareability=data.get("shareability", 5),
                depth=data.get("depth", 5),
                ai_score=ai_score,
                linkedin_potential=linkedin_potential,
                key_insight=data.get("key_insight", ""),
                hook_suggestion=data.get("hook_suggestion", "")
            )

        except Exception as e:
            print(f"평가 실패 [{article.title[:30]}]: {e}")
            return None

    def evaluate_all(self, articles: list["Article"]) -> list[ArticleEvaluation]:
        """모든 기사 평가 및 정렬"""
        evaluations = []

        print(f"기사 평가 시작 ({len(articles)}개)...")

        for i, article in enumerate(articles):
            evaluation = self.evaluate_article(article)
            if evaluation:
                evaluations.append(evaluation)

            if (i + 1) % 5 == 0:
                print(f"평가 진행 중: {i + 1}/{len(articles)}")

        # 총점 기준 내림차순 정렬
        evaluations.sort(key=lambda x: x.ai_score, reverse=True)

        print(f"평가 완료: {len(evaluations)}개 기사")

        return evaluations

    def get_top_candidates(
        self,
        articles: list["Article"],
        top_n: int = 5,
        ensure_diversity: bool = True
    ) -> list[tuple["Article", ArticleEvaluation]]:
        """링크드인 포스팅 상위 후보 선정 (카테고리 다양성 보장)"""
        evaluations = self.evaluate_all(articles)

        # 평가 결과와 원본 기사 매칭
        article_map = {a.url: a for a in articles}

        # URL로 카테고리 찾기
        url_to_category = {a.url: a.category for a in articles}

        if not ensure_diversity:
            # 기존 방식: 단순 점수 순
            candidates = []
            for eval in evaluations[:top_n]:
                if eval.article_url in article_map:
                    candidates.append((article_map[eval.article_url], eval))
            return candidates

        # 다양성 보장 방식
        candidates = []
        used_urls = set()

        # 필수 카테고리 (각 1개 이상)
        # news 카테고리에는 bigtech, news, community, korean 포함
        required_categories = {
            "research": 1,      # 연구 논문 최소 1개
            "news": 1,          # AI 뉴스 최소 1개
        }

        # 뉴스 카테고리 그룹 (research 외 모든 것)
        news_categories = {"bigtech", "news", "community", "korean"}

        # 1단계: 필수 카테고리에서 최고 점수 선정
        for category, min_count in required_categories.items():
            if category == "news":
                # 뉴스는 여러 카테고리에서 선택
                category_evals = [
                    e for e in evaluations
                    if url_to_category.get(e.article_url) in news_categories
                    and e.article_url not in used_urls
                ]
            else:
                category_evals = [
                    e for e in evaluations
                    if url_to_category.get(e.article_url) == category
                    and e.article_url not in used_urls
                ]

            for eval in category_evals[:min_count]:
                if eval.article_url in article_map:
                    candidates.append((article_map[eval.article_url], eval))
                    used_urls.add(eval.article_url)

        # 2단계: 나머지는 점수 순으로 채우기
        remaining_slots = top_n - len(candidates)
        for eval in evaluations:
            if remaining_slots <= 0:
                break
            if eval.article_url not in used_urls and eval.article_url in article_map:
                candidates.append((article_map[eval.article_url], eval))
                used_urls.add(eval.article_url)
                remaining_slots -= 1

        # 점수 순 정렬
        candidates.sort(key=lambda x: x[1].ai_score, reverse=True)

        return candidates

    def print_evaluation_report(self, evaluations: list[ArticleEvaluation], top_n: int = 5):
        """평가 리포트 출력"""
        print("\n" + "=" * 60)
        print("📊 링크드인 포스팅 후보 평가 리포트")
        print("=" * 60)

        for i, eval in enumerate(evaluations[:top_n], 1):
            print(f"\n🏆 #{i} (AI: {eval.ai_score}/10, LI: {eval.linkedin_potential}/10)")
            print(f"제목: {eval.article_title[:60]}...")
            print(f"├─ 호기심: {eval.curiosity}/10")
            print(f"├─ 인사이트: {eval.insight}/10")
            print(f"├─ 관련성: {eval.relevance}/10")
            print(f"├─ 토론유발: {eval.discussion}/10")
            print(f"├─ 공유가치: {eval.shareability}/10")
            print(f"└─ 핵심 인사이트: {eval.key_insight[:50]}...")

        print("\n" + "=" * 60)
