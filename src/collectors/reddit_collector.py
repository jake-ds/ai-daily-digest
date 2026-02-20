"""Reddit 바이럴 콘텐츠 수집기"""

import httpx
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional


@dataclass
class RedditPost:
    """Reddit 포스트 데이터"""
    id: str
    title: str
    url: str
    subreddit: str
    score: int
    num_comments: int
    created_utc: datetime
    author: str
    selftext: Optional[str] = None
    permalink: str = ""
    upvote_ratio: float = 0.0
    is_self: bool = False


class RedditCollector:
    """Reddit API를 통한 바이럴 콘텐츠 수집"""

    BASE_URL = "https://www.reddit.com"

    # 타겟 서브레딧 (AI, SaaS, VC/투자)
    TARGET_SUBREDDITS = {
        "ai": [
            "artificial",
            "MachineLearning",
            "LocalLLaMA",
            "ChatGPT",
            "OpenAI",
            "ClaudeAI",
            "singularity",
            "StableDiffusion",
        ],
        "saas": [
            "SaaS",
            "startups",
            "Entrepreneur",
            "microsaas",
            "indiehackers",
        ],
        "vc": [
            "venturecapital",
            "investing",
            "SecurityAnalysis",
            "stocks",
        ],
        "tech": [
            "technology",
            "programming",
            "webdev",
            "devops",
        ]
    }

    def __init__(self, user_agent: str = "ViralDigest/1.0"):
        self.headers = {"User-Agent": user_agent}
        self.client = httpx.Client(headers=self.headers, timeout=30.0)

    def _parse_post(self, data: dict) -> Optional[RedditPost]:
        """API 응답을 RedditPost로 변환"""
        try:
            post_data = data.get("data", {})

            created_utc = datetime.fromtimestamp(
                post_data.get("created_utc", 0),
                tz=timezone.utc
            )

            return RedditPost(
                id=post_data.get("id", ""),
                title=post_data.get("title", ""),
                url=post_data.get("url", ""),
                subreddit=post_data.get("subreddit", ""),
                score=post_data.get("score", 0),
                num_comments=post_data.get("num_comments", 0),
                created_utc=created_utc,
                author=post_data.get("author", ""),
                selftext=post_data.get("selftext", ""),
                permalink=f"https://reddit.com{post_data.get('permalink', '')}",
                upvote_ratio=post_data.get("upvote_ratio", 0.0),
                is_self=post_data.get("is_self", False)
            )
        except Exception as e:
            print(f"[Reddit] 포스트 파싱 실패: {e}")
            return None

    def get_hot_posts(
        self,
        subreddit: str,
        limit: int = 25
    ) -> list[RedditPost]:
        """서브레딧의 Hot 포스트 가져오기"""
        posts = []

        try:
            url = f"{self.BASE_URL}/r/{subreddit}/hot.json"
            params = {"limit": limit, "raw_json": 1}

            resp = self.client.get(url, params=params)
            resp.raise_for_status()

            data = resp.json()
            children = data.get("data", {}).get("children", [])

            for child in children:
                post = self._parse_post(child)
                if post:
                    posts.append(post)

        except Exception as e:
            print(f"[Reddit] r/{subreddit} Hot 수집 실패: {e}")

        return posts

    def get_rising_posts(
        self,
        subreddit: str,
        limit: int = 25
    ) -> list[RedditPost]:
        """서브레딧의 Rising 포스트 가져오기 (바이럴 초기 감지)"""
        posts = []

        try:
            url = f"{self.BASE_URL}/r/{subreddit}/rising.json"
            params = {"limit": limit, "raw_json": 1}

            resp = self.client.get(url, params=params)
            resp.raise_for_status()

            data = resp.json()
            children = data.get("data", {}).get("children", [])

            for child in children:
                post = self._parse_post(child)
                if post:
                    posts.append(post)

        except Exception as e:
            print(f"[Reddit] r/{subreddit} Rising 수집 실패: {e}")

        return posts

    def collect_category(
        self,
        category: str,
        mode: str = "hot",
        limit_per_sub: int = 10
    ) -> list[RedditPost]:
        """카테고리의 모든 서브레딧에서 수집"""
        subreddits = self.TARGET_SUBREDDITS.get(category, [])
        all_posts = []

        for subreddit in subreddits:
            if mode == "hot":
                posts = self.get_hot_posts(subreddit, limit_per_sub)
            else:
                posts = self.get_rising_posts(subreddit, limit_per_sub)

            all_posts.extend(posts)

        return all_posts

    def collect_all(
        self,
        mode: str = "hot",
        limit_per_sub: int = 10,
        min_score: int = 50
    ) -> list[RedditPost]:
        """모든 타겟 서브레딧에서 수집"""
        all_posts = []

        for category in self.TARGET_SUBREDDITS:
            posts = self.collect_category(category, mode, limit_per_sub)
            all_posts.extend(posts)

        # 점수 필터링 및 중복 제거
        seen_ids = set()
        filtered = []

        for post in all_posts:
            if post.id in seen_ids:
                continue
            if post.score < min_score:
                continue

            seen_ids.add(post.id)
            filtered.append(post)

        # 점수순 정렬
        filtered.sort(key=lambda x: x.score, reverse=True)

        print(f"[Reddit] 총 {len(filtered)}개 포스트 수집 (min_score={min_score})")
        return filtered

    def get_viral_posts(
        self,
        hours: int = 24,
        min_score: int = 100,
        min_velocity: float = 10.0
    ) -> list[RedditPost]:
        """바이럴 포스트 감지 (높은 점수 상승률)"""
        all_posts = self.collect_all(mode="hot", min_score=min_score)

        now = datetime.now(timezone.utc)
        viral = []

        for post in all_posts:
            # 게시 후 경과 시간 (시간)
            age_hours = (now - post.created_utc).total_seconds() / 3600

            if age_hours > hours:
                continue

            if age_hours < 0.1:  # 너무 최신은 제외
                age_hours = 0.1

            # 점수 속도 (점수/시간)
            velocity = post.score / age_hours

            if velocity >= min_velocity:
                viral.append((post, velocity))

        # 속도순 정렬
        viral.sort(key=lambda x: x[1], reverse=True)

        print(f"[Reddit] {len(viral)}개 바이럴 포스트 감지")
        return [p for p, v in viral]

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()


if __name__ == "__main__":
    collector = RedditCollector()

    print("=== Hot Posts ===")
    posts = collector.collect_all(mode="hot", min_score=100)
    for post in posts[:10]:
        print(f"[{post.subreddit}] {post.title[:50]}...")
        print(f"  Score: {post.score} | Comments: {post.num_comments}")
        print()

    print("\n=== Viral Posts ===")
    viral = collector.get_viral_posts(hours=24, min_score=50)
    for post in viral[:5]:
        print(f"[{post.subreddit}] {post.title[:50]}...")
        print(f"  Score: {post.score}")
