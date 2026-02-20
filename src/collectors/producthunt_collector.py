"""Product Hunt 수집기"""

import httpx
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from typing import Optional
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass
class ProductHuntPost:
    """Product Hunt 제품"""
    id: str
    name: str
    tagline: str
    description: Optional[str]
    url: str
    website: Optional[str]
    votes_count: int
    comments_count: int
    created_at: datetime
    topics: list[str]
    thumbnail_url: Optional[str] = None
    makers: list[str] = None

    def __post_init__(self):
        if self.makers is None:
            self.makers = []


class ProductHuntCollector:
    """Product Hunt GraphQL API 수집"""

    API_URL = "https://api.producthunt.com/v2/api/graphql"

    # 관심 토픽
    AI_TOPICS = [
        "artificial-intelligence", "machine-learning", "chatgpt",
        "ai", "generative-ai", "llm", "gpt", "chatbot"
    ]

    SAAS_TOPICS = [
        "saas", "productivity", "developer-tools", "no-code",
        "marketing", "sales", "analytics", "automation"
    ]

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("PRODUCTHUNT_API_TOKEN")
        self.client = httpx.Client(timeout=30.0)

        if not self.api_token:
            print("[ProductHunt] API 토큰이 없습니다. 스크래핑 모드로 전환합니다.")

    def _graphql_query(self, query: str, variables: dict = None) -> dict:
        """GraphQL 쿼리 실행"""
        if not self.api_token:
            return {}

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = self.client.post(self.API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _scrape_homepage(self) -> list[ProductHuntPost]:
        """Product Hunt 홈페이지 스크래핑 (API 없이)"""
        posts = []

        try:
            resp = self.client.get(
                "https://www.producthunt.com",
                headers={"User-Agent": "ViralDigest/1.0"}
            )
            resp.raise_for_status()

            # JSON 데이터 추출 (Next.js __NEXT_DATA__)
            import re
            import json

            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                resp.text
            )

            if match:
                data = json.loads(match.group(1))
                # props.pageProps.posts 경로로 데이터 추출
                page_props = data.get("props", {}).get("pageProps", {})

                # 다양한 경로 시도
                posts_data = (
                    page_props.get("posts") or
                    page_props.get("homefeed", {}).get("posts") or
                    []
                )

                for p in posts_data[:25]:
                    try:
                        node = p.get("node", p)  # 때때로 edge/node 구조

                        post = ProductHuntPost(
                            id=str(node.get("id", "")),
                            name=node.get("name", ""),
                            tagline=node.get("tagline", ""),
                            description=node.get("description"),
                            url=f"https://www.producthunt.com/posts/{node.get('slug', '')}",
                            website=node.get("website"),
                            votes_count=node.get("votesCount", 0),
                            comments_count=node.get("commentsCount", 0),
                            created_at=datetime.now(timezone.utc),
                            topics=[t.get("name", "") for t in node.get("topics", {}).get("nodes", [])],
                            thumbnail_url=node.get("thumbnail", {}).get("url") if node.get("thumbnail") else None
                        )

                        if post.name:
                            posts.append(post)
                    except Exception:
                        continue

        except Exception as e:
            print(f"[ProductHunt] 스크래핑 실패: {e}")

        return posts

    def get_today_posts(self, limit: int = 20) -> list[ProductHuntPost]:
        """오늘의 포스트 가져오기"""
        if not self.api_token:
            return self._scrape_homepage()

        query = """
        query GetPosts($first: Int, $postedAfter: DateTime) {
            posts(first: $first, postedAfter: $postedAfter) {
                edges {
                    node {
                        id
                        name
                        tagline
                        description
                        url
                        website
                        votesCount
                        commentsCount
                        createdAt
                        topics {
                            nodes {
                                name
                                slug
                            }
                        }
                        thumbnail {
                            url
                        }
                        makers {
                            name
                        }
                    }
                }
            }
        }
        """

        # 24시간 전
        posted_after = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        variables = {
            "first": limit,
            "postedAfter": posted_after
        }

        try:
            result = self._graphql_query(query, variables)
            edges = result.get("data", {}).get("posts", {}).get("edges", [])

            posts = []
            for edge in edges:
                node = edge.get("node", {})

                created_at = datetime.fromisoformat(
                    node.get("createdAt", "").replace("Z", "+00:00")
                ) if node.get("createdAt") else datetime.now(timezone.utc)

                topics = [
                    t.get("name", "")
                    for t in node.get("topics", {}).get("nodes", [])
                ]

                makers = [
                    m.get("name", "")
                    for m in node.get("makers", [])
                ]

                post = ProductHuntPost(
                    id=node.get("id", ""),
                    name=node.get("name", ""),
                    tagline=node.get("tagline", ""),
                    description=node.get("description"),
                    url=node.get("url", ""),
                    website=node.get("website"),
                    votes_count=node.get("votesCount", 0),
                    comments_count=node.get("commentsCount", 0),
                    created_at=created_at,
                    topics=topics,
                    thumbnail_url=node.get("thumbnail", {}).get("url") if node.get("thumbnail") else None,
                    makers=makers
                )
                posts.append(post)

            return posts

        except Exception as e:
            print(f"[ProductHunt] API 조회 실패: {e}")
            return self._scrape_homepage()

    def get_top_posts(self, min_votes: int = 100) -> list[ProductHuntPost]:
        """인기 포스트 (최소 투표 수 이상)"""
        posts = self.get_today_posts(limit=50)
        top = [p for p in posts if p.votes_count >= min_votes]
        top.sort(key=lambda x: x.votes_count, reverse=True)

        print(f"[ProductHunt] {len(top)}개 인기 포스트 (min_votes={min_votes})")
        return top

    def _is_ai_related(self, post: ProductHuntPost) -> bool:
        """AI 관련 제품인지 확인"""
        text = f"{post.name} {post.tagline} {post.description or ''}".lower()
        topics_lower = [t.lower() for t in post.topics]

        # 토픽 체크
        for topic in self.AI_TOPICS:
            if topic in topics_lower:
                return True

        # 텍스트 체크
        ai_keywords = ["ai", "gpt", "llm", "chatbot", "machine learning", "artificial intelligence"]
        return any(kw in text for kw in ai_keywords)

    def _is_saas_related(self, post: ProductHuntPost) -> bool:
        """SaaS 관련 제품인지 확인"""
        text = f"{post.name} {post.tagline} {post.description or ''}".lower()
        topics_lower = [t.lower() for t in post.topics]

        for topic in self.SAAS_TOPICS:
            if topic in topics_lower:
                return True

        saas_keywords = ["saas", "platform", "tool", "app", "software"]
        return any(kw in text for kw in saas_keywords)

    def get_ai_products(self) -> list[ProductHuntPost]:
        """AI 관련 제품"""
        posts = self.get_today_posts(limit=50)
        ai_posts = [p for p in posts if self._is_ai_related(p)]
        ai_posts.sort(key=lambda x: x.votes_count, reverse=True)

        print(f"[ProductHunt] AI 관련 {len(ai_posts)}개")
        return ai_posts

    def get_saas_products(self) -> list[ProductHuntPost]:
        """SaaS 관련 제품"""
        posts = self.get_today_posts(limit=50)
        saas_posts = [p for p in posts if self._is_saas_related(p)]
        saas_posts.sort(key=lambda x: x.votes_count, reverse=True)

        print(f"[ProductHunt] SaaS 관련 {len(saas_posts)}개")
        return saas_posts

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()


if __name__ == "__main__":
    collector = ProductHuntCollector()

    print("=== Today's Products ===")
    posts = collector.get_today_posts()
    for post in posts[:10]:
        print(f"{post.name}")
        print(f"  {post.tagline}")
        print(f"  Votes: {post.votes_count} | Topics: {', '.join(post.topics[:3])}")
        print()

    print("\n=== AI Products ===")
    ai_posts = collector.get_ai_products()
    for post in ai_posts[:5]:
        print(f"{post.name} - {post.votes_count} votes")
