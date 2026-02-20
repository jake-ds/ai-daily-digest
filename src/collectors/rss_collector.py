"""RSS 피드 수집기"""

import feedparser
from datetime import datetime, timedelta, timezone
from dateutil import parser as date_parser
from dataclasses import dataclass
from typing import Optional
import yaml
from pathlib import Path


@dataclass
class Article:
    """수집된 기사 데이터"""
    title: str
    url: str
    source: str
    category: str
    priority: str
    published: Optional[datetime]
    summary: Optional[str] = None
    authors: Optional[str] = None  # 저자/기관 정보
    score: float = 0.0
    ai_summary: Optional[str] = None


class RSSCollector:
    """RSS 피드에서 기사를 수집하는 클래스"""

    def __init__(self, feeds_path: str = "data/feeds.yaml"):
        self.feeds_path = Path(feeds_path)
        self.feeds = self._load_feeds()

    def _load_feeds(self) -> dict:
        """피드 설정 파일 로드"""
        with open(self.feeds_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _parse_date(self, entry: dict) -> Optional[datetime]:
        """피드 엔트리에서 날짜 파싱"""
        date_fields = ["published", "updated", "created"]

        for field in date_fields:
            if field in entry:
                try:
                    parsed = date_parser.parse(entry[field])
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    return parsed
                except (ValueError, TypeError):
                    continue
        return None

    def _is_recent(self, published: Optional[datetime], hours: int = 48) -> bool:
        """최근 기사인지 확인 (기본 48시간)"""
        if published is None:
            return True  # 날짜 없으면 일단 포함

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)
        return published > cutoff

    def _extract_authors(self, entry: dict, category: str) -> Optional[str]:
        """저자/기관 정보 추출"""
        # arXiv 등 연구 논문의 경우
        if category == "research":
            # authors 필드 확인 (arXiv)
            if "authors" in entry:
                authors = entry["authors"]
                if isinstance(authors, list):
                    # 처음 3명만 표시
                    names = [a.get("name", "") for a in authors[:3]]
                    result = ", ".join(names)
                    if len(authors) > 3:
                        result += f" 외 {len(authors) - 3}명"
                    return result
            # author 필드 확인
            if "author" in entry:
                return entry["author"][:100]
        return None

    def collect_from_feed(self, feed_config: dict, hours: int = 48) -> list[Article]:
        """단일 피드에서 기사 수집"""
        articles = []

        try:
            feed = feedparser.parse(feed_config["url"])

            for entry in feed.entries:
                published = self._parse_date(entry)

                if not self._is_recent(published, hours):
                    continue

                # 저자 정보 추출
                authors = self._extract_authors(entry, feed_config["category"])

                article = Article(
                    title=entry.get("title", "").strip(),
                    url=entry.get("link", ""),
                    source=feed_config["name"],
                    category=feed_config["category"],
                    priority=feed_config["priority"],
                    published=published,
                    summary=entry.get("summary", "")[:500] if entry.get("summary") else None,
                    authors=authors
                )

                if article.title and article.url:
                    articles.append(article)

        except Exception as e:
            print(f"피드 수집 실패 [{feed_config['name']}]: {e}")

        return articles

    def collect_all(self, hours: int = 48) -> list[Article]:
        """모든 피드에서 기사 수집"""
        all_articles = []

        for category, feeds in self.feeds.get("feeds", {}).items():
            for feed_config in feeds:
                articles = self.collect_from_feed(feed_config, hours)
                all_articles.extend(articles)
                print(f"[{feed_config['name']}] {len(articles)}개 기사 수집")

        print(f"\n총 {len(all_articles)}개 기사 수집 완료")
        return all_articles


if __name__ == "__main__":
    collector = RSSCollector()
    articles = collector.collect_all(hours=48)

    for article in articles[:10]:
        print(f"- [{article.source}] {article.title[:50]}...")
