# Collector 추가 패턴

## 기본 구조

```python
"""새 데이터 소스 collector"""

import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from .rss_collector import Article  # 표준 데이터클래스 import


class NewSourceCollector:
    """새 소스에서 기사를 수집하는 Collector"""

    def __init__(self):
        self.api_key = os.getenv("NEW_SOURCE_API_KEY")

    def collect(self, hours: int = 48, limit: int = 30) -> list[Article]:
        """기사 수집

        Args:
            hours: 수집할 기간 (시간)
            limit: 최대 수집 수

        Returns:
            Article 리스트
        """
        if not self.api_key:
            print("[NewSource] API 키 없음, 건너뜀")
            return []

        articles = []
        cutoff = datetime.now() - timedelta(hours=hours)

        try:
            # API 호출 또는 스크래핑
            raw_data = self._fetch_data(limit)

            for item in raw_data:
                published = self._parse_date(item)
                if published and published < cutoff:
                    continue

                articles.append(Article(
                    title=item["title"],
                    url=item["url"],
                    summary=item.get("description", ""),
                    source="NewSource",
                    category=self._categorize(item),
                    published=published or datetime.now(),
                ))

            print(f"[NewSource] {len(articles)}개 기사 수집")

        except Exception as e:
            print(f"[NewSource] 수집 실패: {e}")

        return articles

    def _fetch_data(self, limit: int) -> list[dict]:
        """API 호출 또는 스크래핑"""
        # 구현
        return []

    def _parse_date(self, item: dict) -> datetime:
        """날짜 파싱"""
        # 구현
        return datetime.now()

    def _categorize(self, item: dict) -> str:
        """카테고리 분류"""
        return "news"
```

## 체크리스트

- [ ] `Article` 데이터클래스를 `rss_collector`에서 import
- [ ] `collect()` 메서드가 `list[Article]` 반환
- [ ] API 키 없을 때 빈 리스트 반환 (crash 금지)
- [ ] `hours` 파라미터로 기간 필터링
- [ ] 에러 시 try/except로 빈 리스트 반환
- [ ] `print(f"[ModuleName] 메시지")` 형식 로그
- [ ] `src/collectors/__init__.py`에 export 추가
- [ ] `main.py` 수집 단계에서 호출 추가
- [ ] `.env.example`에 API 키 추가 (필요 시)

## 카테고리 목록

| 카테고리 | 용도 |
|----------|------|
| bigtech | 빅테크 뉴스 |
| vc | 벤처/투자 |
| news | 일반 AI/Tech 뉴스 |
| research | 논문/연구 |
| community | 개발자 커뮤니티 |
| korean | 한국 뉴스 |
| media | 영상 콘텐츠 |

## 기존 Collector 참고

| Collector | 소스 | 특징 |
|-----------|------|------|
| `rss_collector.py` | RSS 피드 30+ | feeds.yaml 기반, 카테고리별 분류 |
| `hn_collector.py` | Hacker News API | 상위 30개, 댓글 수 기반 정렬 |
| `youtube_collector.py` | YouTube Data API v3 | 채널 구독 기반 |
| `gmail_collector.py` | Gmail API (OAuth2) | 뉴스레터 파싱 |
| `reddit_collector.py` | Reddit JSON API | 서브레딧별 수집 |
| `github_trending.py` | GitHub 스크래핑 | 트렌딩 레포 |
| `producthunt_collector.py` | Product Hunt | 일일 상위 제품 |
| `twitter_collector.py` | Twitter API v2 | 키워드/리스트 기반 |
