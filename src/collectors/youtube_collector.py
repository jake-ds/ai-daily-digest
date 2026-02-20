"""YouTube 채널 영상 수집기"""

import os
import yaml
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .rss_collector import Article


class YouTubeCollector:
    """YouTube Data API v3 기반 영상 수집"""

    API_BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, channels_path: str = "data/youtube_channels.yaml"):
        self.api_key = os.getenv("YOUTUBE_API_KEY")
        self.channels_path = Path(channels_path)
        self.channels = self._load_channels()

    def _load_channels(self) -> list[dict]:
        """채널 설정 파일 로드"""
        if not self.channels_path.exists():
            print(f"채널 설정 파일 없음: {self.channels_path}")
            return []

        with open(self.channels_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("channels", [])

    def _search_channel_videos(
        self, channel_id: str, published_after: datetime, max_results: int = 5
    ) -> list[dict]:
        """채널의 최신 영상 검색 (Search API)"""
        url = f"{self.API_BASE_URL}/search"
        params = {
            "key": self.api_key,
            "channelId": channel_id,
            "order": "date",
            "type": "video",
            "part": "snippet",
            "maxResults": max_results,
            "publishedAfter": published_after.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])
        except requests.RequestException as e:
            print(f"YouTube Search API 오류: {e}")
            return []

    def _get_video_details(self, video_ids: list[str]) -> dict[str, dict]:
        """영상 상세 정보 조회 (Videos API) - description 전체"""
        if not video_ids:
            return {}

        url = f"{self.API_BASE_URL}/videos"
        params = {
            "key": self.api_key,
            "id": ",".join(video_ids),
            "part": "snippet",
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            result = {}
            for item in data.get("items", []):
                video_id = item["id"]
                snippet = item.get("snippet", {})
                result[video_id] = {
                    "description": snippet.get("description", ""),
                    "publishedAt": snippet.get("publishedAt"),
                }
            return result
        except requests.RequestException as e:
            print(f"YouTube Videos API 오류: {e}")
            return {}

    def _parse_datetime(self, dt_str: str) -> Optional[datetime]:
        """ISO 8601 날짜 문자열 파싱"""
        if not dt_str:
            return None
        try:
            # ISO 8601 형식: 2024-01-15T10:30:00Z
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt
        except ValueError:
            return None

    def collect_from_channel(
        self, channel_config: dict, hours: int = 48, limit: int = 5
    ) -> list[Article]:
        """단일 채널에서 영상 수집"""
        channel_id = channel_config["id"]
        channel_name = channel_config["name"]
        category = channel_config["category"]
        priority = channel_config["priority"]

        # 기준 시간 계산
        published_after = datetime.now(timezone.utc) - timedelta(hours=hours)

        # 1. 최신 영상 검색
        search_results = self._search_channel_videos(
            channel_id, published_after, max_results=limit
        )

        if not search_results:
            return []

        # 2. 영상 ID 추출
        video_ids = []
        video_snippets = {}
        for item in search_results:
            video_id = item.get("id", {}).get("videoId")
            if video_id:
                video_ids.append(video_id)
                video_snippets[video_id] = item.get("snippet", {})

        # 3. 상세 정보 조회 (description 전체)
        video_details = self._get_video_details(video_ids)

        # 4. Article 객체 생성
        articles = []
        for video_id in video_ids:
            snippet = video_snippets.get(video_id, {})
            details = video_details.get(video_id, {})

            title = snippet.get("title", "")
            # 상세 정보의 description 사용 (전체), 없으면 검색 결과의 description
            description = details.get("description") or snippet.get("description", "")

            # 날짜 파싱 (상세 정보 우선)
            published_str = details.get("publishedAt") or snippet.get("publishedAt")
            published = self._parse_datetime(published_str)

            article = Article(
                title=title,
                url=f"https://www.youtube.com/watch?v={video_id}",
                source=f"YouTube - {channel_name}",
                category=category,
                priority=priority,
                published=published,
                summary=description[:500] if description else None,
            )

            if article.title and article.url:
                articles.append(article)

        return articles

    def collect(self, hours: int = 48, limit_per_channel: int = 5) -> list[Article]:
        """모든 채널에서 최신 영상 수집"""
        if not self.api_key:
            print("YOUTUBE_API_KEY가 설정되지 않았습니다.")
            return []

        if not self.channels:
            print("수집할 YouTube 채널이 없습니다.")
            return []

        all_articles = []

        for channel_config in self.channels:
            articles = self.collect_from_channel(
                channel_config, hours=hours, limit=limit_per_channel
            )
            all_articles.extend(articles)
            print(f"[YouTube - {channel_config['name']}] {len(articles)}개 영상 수집")

        print(f"\nYouTube 총 {len(all_articles)}개 영상 수집 완료")
        return all_articles


if __name__ == "__main__":
    collector = YouTubeCollector()
    articles = collector.collect(hours=48)

    for article in articles[:10]:
        print(f"- [{article.source}] {article.title[:50]}...")
