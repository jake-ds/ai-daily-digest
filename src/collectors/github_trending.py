"""GitHub Trending 수집기"""

import re
import httpx
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional
from bs4 import BeautifulSoup


@dataclass
class TrendingRepo:
    """GitHub Trending 저장소"""
    name: str  # owner/repo
    url: str
    description: Optional[str]
    language: Optional[str]
    stars: int
    stars_today: int
    forks: int
    built_by: list[str]


class GitHubTrendingCollector:
    """GitHub Trending 페이지 스크래핑"""

    BASE_URL = "https://github.com/trending"

    # 관심 언어
    LANGUAGES = ["python", "typescript", "javascript", "rust", "go"]

    # AI/SaaS 관련 키워드
    AI_KEYWORDS = [
        "ai", "llm", "gpt", "agent", "rag", "embedding", "vector",
        "machine-learning", "deep-learning", "neural", "transformer",
        "openai", "anthropic", "langchain", "llamaindex",
        "chatbot", "copilot", "assistant", "automation"
    ]

    SAAS_KEYWORDS = [
        "saas", "api", "backend", "frontend", "fullstack",
        "dashboard", "analytics", "auth", "payment", "stripe",
        "nextjs", "react", "vue", "svelte", "tailwind"
    ]

    def __init__(self):
        self.client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": "ViralDigest/1.0"}
        )

    def _parse_stars(self, text: str) -> int:
        """스타 수 파싱 (예: '1,234' → 1234, '5.2k' → 5200)"""
        if not text:
            return 0

        text = text.strip().lower().replace(",", "")

        if "k" in text:
            return int(float(text.replace("k", "")) * 1000)
        elif "m" in text:
            return int(float(text.replace("m", "")) * 1000000)

        try:
            return int(text)
        except ValueError:
            return 0

    def _parse_repo(self, article) -> Optional[TrendingRepo]:
        """HTML 요소에서 저장소 정보 파싱"""
        try:
            # 저장소 이름
            h2 = article.select_one("h2 a")
            if not h2:
                return None

            name = h2.get_text(strip=True).replace(" ", "").replace("\n", "")
            url = f"https://github.com{h2.get('href', '')}"

            # 설명
            p = article.select_one("p")
            description = p.get_text(strip=True) if p else None

            # 언어
            lang_span = article.select_one("[itemprop='programmingLanguage']")
            language = lang_span.get_text(strip=True) if lang_span else None

            # 스타 수
            stars = 0
            star_link = article.select_one("a[href$='/stargazers']")
            if star_link:
                stars = self._parse_stars(star_link.get_text())

            # 오늘 스타 수
            stars_today = 0
            today_span = article.select_one("span.d-inline-block.float-sm-right")
            if today_span:
                today_text = today_span.get_text(strip=True)
                match = re.search(r"([\d,]+)", today_text)
                if match:
                    stars_today = self._parse_stars(match.group(1))

            # 포크 수
            forks = 0
            fork_link = article.select_one("a[href$='/forks']")
            if fork_link:
                forks = self._parse_stars(fork_link.get_text())

            # 기여자
            built_by = []
            contributors = article.select("span.d-inline-block a img")
            for img in contributors[:5]:
                alt = img.get("alt", "")
                if alt.startswith("@"):
                    built_by.append(alt[1:])

            return TrendingRepo(
                name=name,
                url=url,
                description=description,
                language=language,
                stars=stars,
                stars_today=stars_today,
                forks=forks,
                built_by=built_by
            )

        except Exception as e:
            print(f"[GitHub] 저장소 파싱 실패: {e}")
            return None

    def get_trending(
        self,
        language: Optional[str] = None,
        since: str = "daily"
    ) -> list[TrendingRepo]:
        """Trending 저장소 가져오기"""
        repos = []

        try:
            url = self.BASE_URL
            if language:
                url = f"{url}/{language}"

            params = {"since": since}
            resp = self.client.get(url, params=params)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article.Box-row")

            for article in articles:
                repo = self._parse_repo(article)
                if repo:
                    repos.append(repo)

        except Exception as e:
            print(f"[GitHub] Trending 수집 실패: {e}")

        return repos

    def get_all_trending(self, since: str = "daily") -> list[TrendingRepo]:
        """전체 + 언어별 Trending 수집"""
        all_repos = []
        seen = set()

        # 전체 Trending
        repos = self.get_trending(since=since)
        for repo in repos:
            if repo.name not in seen:
                seen.add(repo.name)
                all_repos.append(repo)

        # 언어별 Trending
        for lang in self.LANGUAGES:
            repos = self.get_trending(language=lang, since=since)
            for repo in repos:
                if repo.name not in seen:
                    seen.add(repo.name)
                    all_repos.append(repo)

        # stars_today 순 정렬
        all_repos.sort(key=lambda x: x.stars_today, reverse=True)

        print(f"[GitHub] 총 {len(all_repos)}개 Trending 저장소 수집")
        return all_repos

    def _is_ai_related(self, repo: TrendingRepo) -> bool:
        """AI 관련 저장소인지 확인"""
        text = f"{repo.name} {repo.description or ''}".lower()
        return any(kw in text for kw in self.AI_KEYWORDS)

    def _is_saas_related(self, repo: TrendingRepo) -> bool:
        """SaaS 관련 저장소인지 확인"""
        text = f"{repo.name} {repo.description or ''}".lower()
        return any(kw in text for kw in self.SAAS_KEYWORDS)

    def get_ai_trending(self, since: str = "daily") -> list[TrendingRepo]:
        """AI 관련 Trending 저장소"""
        all_repos = self.get_all_trending(since)
        ai_repos = [r for r in all_repos if self._is_ai_related(r)]
        print(f"[GitHub] AI 관련 {len(ai_repos)}개")
        return ai_repos

    def get_saas_trending(self, since: str = "daily") -> list[TrendingRepo]:
        """SaaS 관련 Trending 저장소"""
        all_repos = self.get_all_trending(since)
        saas_repos = [r for r in all_repos if self._is_saas_related(r)]
        print(f"[GitHub] SaaS 관련 {len(saas_repos)}개")
        return saas_repos

    def get_hot_new_repos(
        self,
        min_stars_today: int = 100
    ) -> list[TrendingRepo]:
        """오늘 급상승 저장소"""
        all_repos = self.get_all_trending(since="daily")
        hot = [r for r in all_repos if r.stars_today >= min_stars_today]
        return hot

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()


if __name__ == "__main__":
    collector = GitHubTrendingCollector()

    print("=== All Trending ===")
    repos = collector.get_all_trending()
    for repo in repos[:10]:
        print(f"{repo.name}")
        print(f"  {repo.description[:60] if repo.description else 'No description'}...")
        print(f"  Stars: {repo.stars:,} (+{repo.stars_today} today) | Lang: {repo.language}")
        print()

    print("\n=== AI Trending ===")
    ai_repos = collector.get_ai_trending()
    for repo in ai_repos[:5]:
        print(f"{repo.name} - +{repo.stars_today} today")
