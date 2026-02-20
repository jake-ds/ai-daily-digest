"""바이럴 콘텐츠 통합 수집기

모든 플랫폼에서 바이럴 콘텐츠를 수집하고 통합합니다.
- Hacker News
- Reddit
- GitHub Trending
- Product Hunt
- Twitter/X (선택적)
"""

from datetime import datetime, timezone
from typing import Optional

from .hn_collector import HackerNewsCollector, HNStory
from .reddit_collector import RedditCollector, RedditPost
from .github_trending import GitHubTrendingCollector, TrendingRepo
from .producthunt_collector import ProductHuntCollector, ProductHuntPost
from .twitter_collector import TwitterCollector, Tweet

from ..processors.viral_detector import ViralContent, ViralDetector, ViralDigest


class ViralAggregator:
    """모든 플랫폼에서 바이럴 콘텐츠 통합 수집"""

    def __init__(self):
        self.hn = HackerNewsCollector()
        self.reddit = RedditCollector()
        self.github = GitHubTrendingCollector()
        self.producthunt = ProductHuntCollector()
        self.twitter = TwitterCollector()
        self.detector = ViralDetector()

    def _hn_to_viral(self, story: HNStory) -> ViralContent:
        """HN 스토리를 ViralContent로 변환"""
        return ViralContent(
            id=f"hn_{story.id}",
            title=story.title,
            url=story.url,
            source="hn",
            category=story.category,
            score=story.score,
            velocity=story.velocity,
            created_at=story.created_at,
            description=f"Points: {story.score} | Comments: {story.comments}",
            comments_count=story.comments
        )

    def _reddit_to_viral(self, post: RedditPost) -> ViralContent:
        """Reddit 포스트를 ViralContent로 변환"""
        # 카테고리 결정
        subreddit_lower = post.subreddit.lower()
        category = "tech"

        ai_subs = ["artificial", "machinelearning", "localllama", "chatgpt", "openai", "claudeai"]
        saas_subs = ["saas", "startups", "entrepreneur", "microsaas", "indiehackers"]
        vc_subs = ["venturecapital", "investing"]

        if subreddit_lower in ai_subs:
            category = "ai"
        elif subreddit_lower in saas_subs:
            category = "saas"
        elif subreddit_lower in vc_subs:
            category = "vc"

        # velocity 계산
        age_hours = (datetime.now(timezone.utc) - post.created_utc).total_seconds() / 3600
        velocity = post.score / max(age_hours, 0.1)

        return ViralContent(
            id=f"reddit_{post.id}",
            title=post.title,
            url=post.url if not post.is_self else post.permalink,
            source="reddit",
            category=category,
            score=post.score,
            velocity=velocity,
            created_at=post.created_utc,
            description=post.selftext[:200] if post.selftext else f"r/{post.subreddit}",
            comments_count=post.num_comments
        )

    def _github_to_viral(self, repo: TrendingRepo) -> ViralContent:
        """GitHub 저장소를 ViralContent로 변환"""
        # 카테고리 결정
        text = f"{repo.name} {repo.description or ''}".lower()

        category = "tech"
        if any(kw in text for kw in ["ai", "llm", "gpt", "ml", "neural", "transformer"]):
            category = "ai"
        elif any(kw in text for kw in ["saas", "api", "platform", "dashboard"]):
            category = "saas"

        return ViralContent(
            id=f"github_{repo.name.replace('/', '_')}",
            title=repo.name,
            url=repo.url,
            source="github",
            category=category,
            score=repo.stars,
            velocity=repo.stars_today,  # 오늘 스타 수를 velocity로 사용
            created_at=datetime.now(timezone.utc),  # GitHub는 정확한 시간 없음
            description=repo.description,
            relevance_tags=[repo.language] if repo.language else []
        )

    def _producthunt_to_viral(self, post: ProductHuntPost) -> ViralContent:
        """Product Hunt 포스트를 ViralContent로 변환"""
        # 카테고리 결정
        text = f"{post.name} {post.tagline} {post.description or ''}".lower()
        topics_lower = [t.lower() for t in post.topics]

        category = "saas"  # PH는 대부분 SaaS
        if any(kw in text or kw in topics_lower for kw in ["ai", "gpt", "llm", "machine-learning"]):
            category = "ai"

        # velocity (출시 당일 기준)
        age_hours = (datetime.now(timezone.utc) - post.created_at).total_seconds() / 3600
        velocity = post.votes_count / max(age_hours, 0.1)

        return ViralContent(
            id=f"ph_{post.id}",
            title=post.name,
            url=post.url,
            source="producthunt",
            category=category,
            score=post.votes_count,
            velocity=velocity,
            created_at=post.created_at,
            description=post.tagline,
            comments_count=post.comments_count,
            relevance_tags=post.topics[:5]
        )

    def _tweet_to_viral(self, tweet: Tweet) -> ViralContent:
        """트윗을 ViralContent로 변환"""
        # 카테고리 결정
        text = tweet.text.lower()

        category = "tech"
        if any(kw in text for kw in ["ai", "gpt", "llm", "claude", "openai"]):
            category = "ai"
        elif any(kw in text for kw in ["raised", "funding", "series", "valuation"]):
            category = "vc"
        elif any(kw in text for kw in ["saas", "startup", "launch", "product"]):
            category = "saas"

        # velocity
        age_hours = (datetime.now(timezone.utc) - tweet.created_at).total_seconds() / 3600
        velocity = tweet.engagement / max(age_hours, 0.1)

        return ViralContent(
            id=f"twitter_{tweet.id}",
            title=tweet.text[:100],
            url=tweet.url,
            source="twitter",
            category=category,
            score=tweet.engagement,
            velocity=velocity,
            created_at=tweet.created_at,
            description=f"@{tweet.author_username}: {tweet.text[:200]}",
            relevance_tags=[]
        )

    def collect_from_hn(
        self,
        hours: int = 24,
        min_velocity: float = 15.0
    ) -> list[ViralContent]:
        """Hacker News에서 수집"""
        print("\n[Aggregator] Hacker News 수집 중...")
        stories = self.hn.get_viral_stories(hours=hours, min_velocity=min_velocity)
        return [self._hn_to_viral(s) for s in stories]

    def collect_from_reddit(
        self,
        min_score: int = 100
    ) -> list[ViralContent]:
        """Reddit에서 수집"""
        print("[Aggregator] Reddit 수집 중...")
        posts = self.reddit.get_viral_posts(hours=24, min_score=min_score)
        return [self._reddit_to_viral(p) for p in posts]

    def collect_from_github(
        self,
        min_stars_today: int = 50
    ) -> list[ViralContent]:
        """GitHub Trending에서 수집"""
        print("[Aggregator] GitHub Trending 수집 중...")
        repos = self.github.get_hot_new_repos(min_stars_today=min_stars_today)
        return [self._github_to_viral(r) for r in repos]

    def collect_from_producthunt(
        self,
        min_votes: int = 50
    ) -> list[ViralContent]:
        """Product Hunt에서 수집"""
        print("[Aggregator] Product Hunt 수집 중...")
        posts = self.producthunt.get_top_posts(min_votes=min_votes)
        return [self._producthunt_to_viral(p) for p in posts]

    def collect_from_twitter(
        self,
        min_engagement: int = 1000
    ) -> list[ViralContent]:
        """Twitter에서 수집 (활성화된 경우만)"""
        if not self.twitter.is_enabled():
            return []

        print("[Aggregator] Twitter 수집 중...")
        tweets = self.twitter.get_viral_tweets(min_engagement=min_engagement)
        return [self._tweet_to_viral(t) for t in tweets]

    def collect_all(
        self,
        include_twitter: bool = True,
        hn_min_velocity: float = 15.0,
        reddit_min_score: int = 100,
        github_min_stars: int = 50,
        ph_min_votes: int = 50,
        twitter_min_engagement: int = 1000
    ) -> list[ViralContent]:
        """모든 플랫폼에서 수집"""
        all_contents = []

        # HN
        try:
            contents = self.collect_from_hn(min_velocity=hn_min_velocity)
            all_contents.extend(contents)
        except Exception as e:
            print(f"[Aggregator] HN 수집 실패: {e}")

        # Reddit
        try:
            contents = self.collect_from_reddit(min_score=reddit_min_score)
            all_contents.extend(contents)
        except Exception as e:
            print(f"[Aggregator] Reddit 수집 실패: {e}")

        # GitHub
        try:
            contents = self.collect_from_github(min_stars_today=github_min_stars)
            all_contents.extend(contents)
        except Exception as e:
            print(f"[Aggregator] GitHub 수집 실패: {e}")

        # Product Hunt
        try:
            contents = self.collect_from_producthunt(min_votes=ph_min_votes)
            all_contents.extend(contents)
        except Exception as e:
            print(f"[Aggregator] Product Hunt 수집 실패: {e}")

        # Twitter (선택적)
        if include_twitter:
            try:
                contents = self.collect_from_twitter(min_engagement=twitter_min_engagement)
                all_contents.extend(contents)
            except Exception as e:
                print(f"[Aggregator] Twitter 수집 실패: {e}")

        print(f"\n[Aggregator] 총 {len(all_contents)}개 콘텐츠 수집 완료")
        return all_contents

    def create_digest(
        self,
        top_n: int = 20,
        include_twitter: bool = True
    ) -> ViralDigest:
        """바이럴 다이제스트 생성"""
        contents = self.collect_all(include_twitter=include_twitter)
        return self.detector.create_digest(contents, top_n=top_n)

    def get_cross_platform_viral(
        self,
        include_twitter: bool = True
    ) -> list[ViralContent]:
        """크로스 플랫폼 바이럴 콘텐츠"""
        contents = self.collect_all(include_twitter=include_twitter)
        return self.detector.detect_cross_platform(contents)


if __name__ == "__main__":
    aggregator = ViralAggregator()

    print("=" * 60)
    print("바이럴 콘텐츠 수집 시작")
    print("=" * 60)

    digest = aggregator.create_digest(top_n=10, include_twitter=False)

    print(f"\n총 수집: {digest.total_collected}개")
    print(f"크로스 플랫폼: {len(digest.cross_platform_hits)}개")

    print("\n=== Top 10 Viral Contents ===")
    for i, content in enumerate(digest.top_viral[:10], 1):
        print(f"\n{i}. [{content.source}][{content.category}] {content.title[:60]}...")
        print(f"   Score: {content.score} | Velocity: {content.velocity:.1f}")
        if content.platforms_found:
            print(f"   Cross-platform: {', '.join(content.platforms_found)}")

    print("\n=== By Category ===")
    for category, contents in digest.by_category.items():
        print(f"\n{category.upper()}: {len(contents)}개")
        for c in contents[:3]:
            print(f"  - {c.title[:50]}...")
