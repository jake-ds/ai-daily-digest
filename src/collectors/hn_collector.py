"""Hacker News 수집기 (바이럴 감지 강화)"""

import httpx
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional
from .rss_collector import Article


@dataclass
class HNStory:
    """Hacker News 스토리 (바이럴 감지용)"""
    id: int
    title: str
    url: str
    score: int
    comments: int
    author: str
    created_at: datetime
    category: str = "tech"

    @property
    def velocity(self) -> float:
        """점수 속도 (점수/시간)"""
        age_hours = (datetime.now(timezone.utc) - self.created_at).total_seconds() / 3600
        if age_hours < 0.1:
            age_hours = 0.1
        return self.score / age_hours


class HackerNewsCollector:
    """Hacker News API에서 AI 관련 기사 수집"""

    BASE_URL = "https://hacker-news.firebaseio.com/v0"

    AI_KEYWORDS = [
        "ai", "gpt", "llm", "openai", "anthropic", "claude", "gemini",
        "machine learning", "deep learning", "neural", "transformer",
        "chatgpt", "copilot", "cursor", "vibe coding", "langchain",
        "rag", "fine-tuning", "embedding", "agent"
    ]

    SAAS_KEYWORDS = [
        "saas", "startup", "launch", "product", "pricing",
        "api", "platform", "tool", "app", "service"
    ]

    VC_KEYWORDS = [
        "funding", "raised", "series", "valuation", "vc",
        "investor", "acquisition", "ipo", "unicorn", "seed"
    ]

    def __init__(self):
        self.client = httpx.Client(timeout=30.0)

    def _is_ai_related(self, title: str) -> bool:
        """제목이 AI 관련인지 확인"""
        title_lower = title.lower()
        return any(kw in title_lower for kw in self.AI_KEYWORDS)

    def _is_saas_related(self, title: str) -> bool:
        """제목이 SaaS 관련인지 확인"""
        title_lower = title.lower()
        return any(kw in title_lower for kw in self.SAAS_KEYWORDS)

    def _is_vc_related(self, title: str) -> bool:
        """제목이 VC/투자 관련인지 확인"""
        title_lower = title.lower()
        return any(kw in title_lower for kw in self.VC_KEYWORDS)

    def _get_category(self, title: str) -> str:
        """카테고리 결정"""
        if self._is_ai_related(title):
            return "ai"
        if self._is_vc_related(title):
            return "vc"
        if self._is_saas_related(title):
            return "saas"
        return "tech"

    def _get_item(self, item_id: int) -> Optional[dict]:
        """개별 아이템 정보 가져오기"""
        try:
            resp = self.client.get(f"{self.BASE_URL}/item/{item_id}.json")
            return resp.json()
        except Exception:
            return None

    def collect(self, limit: int = 50) -> list[Article]:
        """AI 관련 Top 스토리 수집"""
        articles = []

        try:
            # Top 스토리 ID 목록 가져오기
            resp = self.client.get(f"{self.BASE_URL}/topstories.json")
            story_ids = resp.json()[:200]  # 상위 200개 체크

            ai_count = 0
            for story_id in story_ids:
                if ai_count >= limit:
                    break

                item = self._get_item(story_id)
                if not item or item.get("type") != "story":
                    continue

                title = item.get("title", "")
                if not self._is_ai_related(title):
                    continue

                url = item.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                published = datetime.fromtimestamp(
                    item.get("time", 0),
                    tz=timezone.utc
                ) if item.get("time") else None

                article = Article(
                    title=title,
                    url=url,
                    source="Hacker News",
                    category="community",
                    priority="high",
                    published=published,
                    summary=f"Points: {item.get('score', 0)} | Comments: {item.get('descendants', 0)}"
                )

                articles.append(article)
                ai_count += 1

        except Exception as e:
            print(f"Hacker News 수집 실패: {e}")

        print(f"[Hacker News] {len(articles)}개 AI 관련 기사 수집")
        return articles

    def collect_stories(
        self,
        categories: list[str] = None,
        limit: int = 100,
        min_score: int = 10
    ) -> list[HNStory]:
        """HNStory 형태로 수집 (바이럴 감지용)"""
        if categories is None:
            categories = ["ai", "saas", "vc"]

        stories = []

        try:
            # Top + New 스토리
            for endpoint in ["topstories", "newstories"]:
                resp = self.client.get(f"{self.BASE_URL}/{endpoint}.json")
                story_ids = resp.json()[:200]

                for story_id in story_ids:
                    item = self._get_item(story_id)
                    if not item or item.get("type") != "story":
                        continue

                    title = item.get("title", "")
                    score = item.get("score", 0)

                    if score < min_score:
                        continue

                    category = self._get_category(title)
                    if category not in categories and "tech" not in categories:
                        continue

                    url = item.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                    created_at = datetime.fromtimestamp(
                        item.get("time", 0),
                        tz=timezone.utc
                    ) if item.get("time") else datetime.now(timezone.utc)

                    story = HNStory(
                        id=story_id,
                        title=title,
                        url=url,
                        score=score,
                        comments=item.get("descendants", 0),
                        author=item.get("by", ""),
                        created_at=created_at,
                        category=category
                    )
                    stories.append(story)

                    if len(stories) >= limit:
                        break

                if len(stories) >= limit:
                    break

        except Exception as e:
            print(f"[HN] 스토리 수집 실패: {e}")

        # 중복 제거
        seen = set()
        unique = []
        for s in stories:
            if s.id not in seen:
                seen.add(s.id)
                unique.append(s)

        print(f"[HN] {len(unique)}개 스토리 수집")
        return unique

    def get_viral_stories(
        self,
        hours: int = 24,
        min_velocity: float = 20.0
    ) -> list[HNStory]:
        """바이럴 스토리 감지 (높은 velocity)"""
        stories = self.collect_stories(
            categories=["ai", "saas", "vc", "tech"],
            limit=200,
            min_score=20
        )

        now = datetime.now(timezone.utc)
        viral = []

        for story in stories:
            age_hours = (now - story.created_at).total_seconds() / 3600

            # 지정 시간 내의 스토리만
            if age_hours > hours:
                continue

            if story.velocity >= min_velocity:
                viral.append(story)

        # velocity 순 정렬
        viral.sort(key=lambda x: x.velocity, reverse=True)

        print(f"[HN] {len(viral)}개 바이럴 스토리 감지 (velocity >= {min_velocity})")
        return viral

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()


if __name__ == "__main__":
    collector = HackerNewsCollector()

    print("=== AI 관련 기사 ===")
    articles = collector.collect(limit=10)
    for article in articles:
        print(f"- {article.title[:60]}...")
        print(f"  {article.summary}")

    print("\n=== 바이럴 스토리 ===")
    viral = collector.get_viral_stories(hours=24, min_velocity=15.0)
    for story in viral[:10]:
        print(f"- [{story.category}] {story.title[:50]}...")
        print(f"  Score: {story.score} | Velocity: {story.velocity:.1f}/hr")
