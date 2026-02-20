"""관심도 점수 매기기 모듈"""

import yaml
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..collectors.rss_collector import Article


class Scorer:
    """키워드 기반 관심도 점수 계산"""

    def __init__(self, feeds_path: str = "data/feeds.yaml"):
        self.feeds_path = Path(feeds_path)
        self.keywords = self._load_keywords()

    def _load_keywords(self) -> dict:
        """키워드 설정 로드"""
        with open(self.feeds_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config.get("keywords", {})

    def _count_keyword_matches(self, text: str, keywords: list) -> int:
        """텍스트에서 키워드 매칭 수 계산"""
        text_lower = text.lower()
        return sum(1 for kw in keywords if kw.lower() in text_lower)

    def calculate_score(self, article: "Article") -> float:
        """기사의 관심도 점수 계산"""
        score = 0.0

        # 검색 대상 텍스트
        search_text = f"{article.title} {article.summary or ''}"

        # 우선순위 키워드 (높은 점수)
        high_priority = self.keywords.get("high_priority", [])
        score += self._count_keyword_matches(search_text, high_priority) * 3.0

        # 주제별 키워드
        topics = self.keywords.get("topics", {})
        for topic_name, topic_keywords in topics.items():
            matches = self._count_keyword_matches(search_text, topic_keywords)
            score += matches * 1.5

        # 소스 우선순위 보너스
        if article.priority == "high":
            score += 2.0
        elif article.priority == "medium":
            score += 1.0

        # 빅테크 소스 보너스
        if article.category == "bigtech":
            score += 3.0

        # VC/투자 소스 보너스
        if article.category == "vc":
            score += 3.0

        # 미디어 콘텐츠 보너스 (접근성 낮은 소스)
        if article.category in ("podcast", "newsletter"):
            score += 2.0
        if article.source.lower().startswith("youtube"):
            score += 2.0

        return round(score, 2)

    def score_articles(self, articles: list["Article"]) -> list["Article"]:
        """모든 기사에 점수 부여"""
        for article in articles:
            article.score = self.calculate_score(article)

        # 점수 기준 내림차순 정렬
        articles.sort(key=lambda x: x.score, reverse=True)

        print(f"점수 부여 완료 (최고점: {articles[0].score if articles else 0})")
        return articles

    def get_top_articles(self, articles: list["Article"], n: int = 20) -> list["Article"]:
        """상위 N개 기사 반환"""
        scored = self.score_articles(articles)
        return scored[:n]

    def get_balanced_articles(self, articles: list["Article"], total: int = 20) -> list["Article"]:
        """카테고리별 균형있게 기사 선택 (레거시 - 하위 호환용)"""
        return self.get_all_articles_with_research_limit(articles, research_limit=3)

    def get_all_articles_with_research_limit(
        self,
        articles: list["Article"],
        research_limit: int = 3
    ) -> list["Article"]:
        """모든 기사 반환, research(arXiv)만 제한

        Args:
            articles: 전체 기사 목록
            research_limit: research 카테고리 최대 개수

        Returns:
            필터링된 기사 목록
        """
        from collections import defaultdict

        # 먼저 점수 부여
        self.score_articles(articles)

        # 카테고리별 그룹화
        by_category = defaultdict(list)
        for article in articles:
            by_category[article.category].append(article)

        # 각 카테고리별 점수순 정렬
        for category in by_category:
            by_category[category].sort(key=lambda x: x.score, reverse=True)

        selected = []
        used_urls = set()

        # research 카테고리만 제한, 나머지는 전부 포함
        for category, category_articles in by_category.items():
            if category == "research":
                # research는 상위 N개만
                for article in category_articles[:research_limit]:
                    if article.url not in used_urls:
                        selected.append(article)
                        used_urls.add(article.url)
            else:
                # 나머지는 전부 포함
                for article in category_articles:
                    if article.url not in used_urls:
                        selected.append(article)
                        used_urls.add(article.url)

        # 최종 점수순 정렬
        selected.sort(key=lambda x: x.score, reverse=True)

        # 카테고리별 개수 출력
        category_counts = defaultdict(int)
        for article in selected:
            category_counts[article.category] += 1

        print(f"카테고리별 선택: {dict(category_counts)}")

        return selected
