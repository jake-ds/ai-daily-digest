"""Twitter/X 수집기

주의: Twitter API v2 Basic 플랜은 월 $100부터 시작합니다.
이 모듈은 선택적이며, API 키가 없으면 비활성화됩니다.

대안:
1. Nitter (비공식 프록시) - 불안정할 수 있음
2. RSS 브릿지 서비스
3. 수동 큐레이션 리스트
"""

import os
import httpx
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Tweet:
    """트윗 데이터"""
    id: str
    text: str
    author_id: str
    author_username: str
    author_name: str
    created_at: datetime
    retweet_count: int
    like_count: int
    reply_count: int
    quote_count: int
    url: str
    urls: list[str] = None
    is_retweet: bool = False

    def __post_init__(self):
        if self.urls is None:
            self.urls = []

    @property
    def engagement(self) -> int:
        """총 engagement"""
        return self.retweet_count + self.like_count + self.reply_count + self.quote_count


class TwitterCollector:
    """Twitter API v2 수집기"""

    API_BASE = "https://api.twitter.com/2"

    # AI/Tech 인플루언서 리스트 (선별적 모니터링)
    INFLUENCER_IDS = [
        # 이 ID들은 실제 Twitter 사용자 ID로 교체 필요
        # 예: Elon Musk, Sam Altman, Andrej Karpathy 등
    ]

    # 관심 키워드 (검색용)
    AI_KEYWORDS = [
        "GPT-5", "Claude 4", "Gemini 2",
        "AGI", "AI breakthrough",
        "OpenAI", "Anthropic", "DeepMind",
        "LLM", "transformer"
    ]

    def __init__(self, bearer_token: Optional[str] = None):
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")
        self.enabled = bool(self.bearer_token)

        if not self.enabled:
            print("[Twitter] API 토큰이 없습니다. Twitter 수집이 비활성화됩니다.")
            return

        self.client = httpx.Client(
            timeout=30.0,
            headers={"Authorization": f"Bearer {self.bearer_token}"}
        )

    def _parse_tweet(self, tweet: dict, includes: dict = None) -> Optional[Tweet]:
        """API 응답을 Tweet 객체로 변환"""
        try:
            # 사용자 정보 매칭
            author_id = tweet.get("author_id", "")
            author_username = ""
            author_name = ""

            if includes and "users" in includes:
                for user in includes["users"]:
                    if user.get("id") == author_id:
                        author_username = user.get("username", "")
                        author_name = user.get("name", "")
                        break

            # 생성 시간
            created_at = datetime.now(timezone.utc)
            if tweet.get("created_at"):
                created_at = datetime.fromisoformat(
                    tweet["created_at"].replace("Z", "+00:00")
                )

            # 메트릭스
            metrics = tweet.get("public_metrics", {})

            # URL 추출
            urls = []
            entities = tweet.get("entities", {})
            for url_entity in entities.get("urls", []):
                expanded = url_entity.get("expanded_url")
                if expanded:
                    urls.append(expanded)

            return Tweet(
                id=tweet.get("id", ""),
                text=tweet.get("text", ""),
                author_id=author_id,
                author_username=author_username,
                author_name=author_name,
                created_at=created_at,
                retweet_count=metrics.get("retweet_count", 0),
                like_count=metrics.get("like_count", 0),
                reply_count=metrics.get("reply_count", 0),
                quote_count=metrics.get("quote_count", 0),
                url=f"https://twitter.com/{author_username}/status/{tweet.get('id', '')}",
                urls=urls,
                is_retweet=tweet.get("text", "").startswith("RT @")
            )

        except Exception as e:
            print(f"[Twitter] 트윗 파싱 실패: {e}")
            return None

    def search_recent(
        self,
        query: str,
        max_results: int = 100,
        hours: int = 24
    ) -> list[Tweet]:
        """최근 트윗 검색"""
        if not self.enabled:
            return []

        tweets = []

        try:
            start_time = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).strftime("%Y-%m-%dT%H:%M:%SZ")

            params = {
                "query": f"{query} -is:retweet lang:en",
                "max_results": min(max_results, 100),
                "start_time": start_time,
                "tweet.fields": "created_at,public_metrics,entities,author_id",
                "user.fields": "username,name",
                "expansions": "author_id"
            }

            resp = self.client.get(
                f"{self.API_BASE}/tweets/search/recent",
                params=params
            )

            if resp.status_code == 429:
                print("[Twitter] Rate limit 도달")
                return []

            resp.raise_for_status()
            data = resp.json()

            includes = data.get("includes", {})

            for tweet_data in data.get("data", []):
                tweet = self._parse_tweet(tweet_data, includes)
                if tweet and not tweet.is_retweet:
                    tweets.append(tweet)

        except Exception as e:
            print(f"[Twitter] 검색 실패: {e}")

        return tweets

    def get_viral_tweets(
        self,
        keywords: list[str] = None,
        min_engagement: int = 1000,
        hours: int = 24
    ) -> list[Tweet]:
        """바이럴 트윗 수집"""
        if not self.enabled:
            return []

        if keywords is None:
            keywords = self.AI_KEYWORDS

        all_tweets = []

        for keyword in keywords:
            tweets = self.search_recent(keyword, max_results=100, hours=hours)
            all_tweets.extend(tweets)

        # engagement 필터링 및 중복 제거
        seen_ids = set()
        viral = []

        for tweet in all_tweets:
            if tweet.id in seen_ids:
                continue
            if tweet.engagement < min_engagement:
                continue

            seen_ids.add(tweet.id)
            viral.append(tweet)

        # engagement 순 정렬
        viral.sort(key=lambda x: x.engagement, reverse=True)

        print(f"[Twitter] {len(viral)}개 바이럴 트윗 수집")
        return viral

    def get_user_timeline(
        self,
        user_id: str,
        max_results: int = 10
    ) -> list[Tweet]:
        """특정 사용자의 타임라인"""
        if not self.enabled:
            return []

        tweets = []

        try:
            params = {
                "max_results": max_results,
                "tweet.fields": "created_at,public_metrics,entities",
                "user.fields": "username,name",
                "expansions": "author_id"
            }

            resp = self.client.get(
                f"{self.API_BASE}/users/{user_id}/tweets",
                params=params
            )
            resp.raise_for_status()
            data = resp.json()

            includes = data.get("includes", {})

            for tweet_data in data.get("data", []):
                tweet = self._parse_tweet(tweet_data, includes)
                if tweet:
                    tweets.append(tweet)

        except Exception as e:
            print(f"[Twitter] 타임라인 조회 실패: {e}")

        return tweets

    def is_enabled(self) -> bool:
        """Twitter 수집 활성화 여부"""
        return self.enabled

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()


# Nitter 대안 (무료, 비공식)
class NitterCollector:
    """Nitter를 통한 Twitter 스크래핑 (대안)

    주의: Nitter 인스턴스는 불안정할 수 있습니다.
    https://github.com/zedeus/nitter/wiki/Instances
    """

    # 공개 Nitter 인스턴스 (변경될 수 있음)
    INSTANCES = [
        "https://nitter.net",
        "https://nitter.privacydev.net",
    ]

    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "ViralDigest/1.0"}
        )
        self.working_instance = None

    def _find_working_instance(self) -> Optional[str]:
        """동작하는 인스턴스 찾기"""
        for instance in self.INSTANCES:
            try:
                resp = self.client.get(f"{instance}/", timeout=5.0)
                if resp.status_code == 200:
                    return instance
            except Exception:
                continue
        return None

    def search(self, query: str) -> list[dict]:
        """검색 (간단한 결과)"""
        if not self.working_instance:
            self.working_instance = self._find_working_instance()

        if not self.working_instance:
            print("[Nitter] 동작하는 인스턴스가 없습니다.")
            return []

        # Nitter 스크래핑 로직 (필요시 구현)
        # BeautifulSoup 사용하여 HTML 파싱
        return []

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()


if __name__ == "__main__":
    collector = TwitterCollector()

    if collector.is_enabled():
        print("=== Viral Tweets ===")
        tweets = collector.get_viral_tweets(
            keywords=["GPT-5", "Claude"],
            min_engagement=500
        )
        for tweet in tweets[:10]:
            print(f"@{tweet.author_username}: {tweet.text[:100]}...")
            print(f"  Engagement: {tweet.engagement:,}")
            print()
    else:
        print("Twitter API 토큰을 설정하세요 (TWITTER_BEARER_TOKEN)")
        print("참고: Twitter API Basic 플랜은 월 $100부터 시작합니다.")
