"""바이럴 콘텐츠 감지 및 크로스 플랫폼 분석"""

import os
import json
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, Union
from pathlib import Path
from urllib.parse import urlparse
from collections import defaultdict

import anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ViralContent:
    """바이럴 콘텐츠"""
    id: str
    title: str
    url: str
    source: str  # reddit, hn, github, producthunt, twitter
    category: str  # ai, saas, vc
    score: int  # 플랫폼별 점수 (upvote, stars 등)
    velocity: float  # 점수/시간 (바이럴 속도)
    created_at: datetime
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: Optional[str] = None
    comments_count: int = 0
    cross_platform_score: float = 0.0  # 크로스 플랫폼 점수
    platforms_found: list[str] = field(default_factory=list)
    ai_summary: Optional[str] = None
    relevance_tags: list[str] = field(default_factory=list)

    @property
    def viral_score(self) -> float:
        """종합 바이럴 점수"""
        base_score = min(self.velocity / 10, 10)  # 속도 점수 (0-10)
        cross_bonus = self.cross_platform_score * 5  # 크로스 플랫폼 보너스
        return base_score + cross_bonus


@dataclass
class ViralDigest:
    """바이럴 다이제스트"""
    date: datetime
    top_viral: list[ViralContent]
    by_category: dict  # category -> list[ViralContent]
    by_platform: dict  # platform -> list[ViralContent]
    cross_platform_hits: list[ViralContent]  # 여러 플랫폼에서 발견된 콘텐츠
    total_collected: int


class ViralDetector:
    """바이럴 콘텐츠 감지 및 분석"""

    # URL 정규화를 위한 도메인 매핑
    DOMAIN_ALIASES = {
        "youtu.be": "youtube.com",
        "www.youtube.com": "youtube.com",
        "m.youtube.com": "youtube.com",
        "old.reddit.com": "reddit.com",
        "www.reddit.com": "reddit.com",
        "mobile.twitter.com": "twitter.com",
        "www.twitter.com": "twitter.com",
        "x.com": "twitter.com",
    }

    def __init__(self, history_path: str = "data/viral_history.json"):
        self.history_path = Path(history_path)
        self.history: dict[str, dict] = self._load_history()
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.claude = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None

    def _load_history(self) -> dict:
        """과거 수집 기록 로드"""
        if self.history_path.exists():
            try:
                with open(self.history_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"urls": {}, "last_scores": {}}

    def _save_history(self):
        """기록 저장"""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump(self.history, f, indent=2, default=str)

    def _normalize_url(self, url: str) -> str:
        """URL 정규화 (비교용)"""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # 도메인 별칭 처리
        domain = self.DOMAIN_ALIASES.get(domain, domain)

        # www 제거
        if domain.startswith("www."):
            domain = domain[4:]

        # 경로 정규화
        path = parsed.path.rstrip("/").lower()

        # 쿼리 파라미터 중 중요한 것만 유지
        # (대부분의 트래킹 파라미터 제거)
        important_params = []
        if parsed.query:
            for param in parsed.query.split("&"):
                key = param.split("=")[0].lower()
                if key in ["v", "id", "p"]:  # 유지할 파라미터
                    important_params.append(param)

        query = "&".join(sorted(important_params))

        return f"{domain}{path}{'?' + query if query else ''}"

    def _extract_canonical_url(self, content: ViralContent) -> Optional[str]:
        """콘텐츠에서 외부 URL 추출 (크로스 플랫폼 매칭용)"""
        # Reddit, HN 등에서 공유된 실제 URL
        if content.source in ["reddit", "hn"]:
            url = content.url

            # HN 자체 링크인 경우 건너뛰기
            if "news.ycombinator.com" in url:
                return None
            if "reddit.com" in url:
                return None

            return self._normalize_url(url)

        # GitHub 저장소
        if content.source == "github":
            return self._normalize_url(content.url)

        return None

    def calculate_velocity(
        self,
        current_score: int,
        created_at: datetime,
        previous_score: int = 0
    ) -> float:
        """점수 속도 계산 (점수/시간)"""
        now = datetime.now(timezone.utc)
        age_hours = (now - created_at).total_seconds() / 3600

        if age_hours < 0.1:
            age_hours = 0.1

        # 이전 점수가 있으면 증가분 기준
        score_diff = current_score - previous_score if previous_score else current_score

        return score_diff / age_hours

    def detect_cross_platform(
        self,
        contents: list[ViralContent]
    ) -> list[ViralContent]:
        """크로스 플랫폼 감지 - 여러 플랫폼에서 언급된 콘텐츠"""
        # URL → 콘텐츠 목록 매핑
        url_to_contents: dict[str, list[ViralContent]] = defaultdict(list)

        for content in contents:
            canonical = self._extract_canonical_url(content)
            if canonical:
                url_to_contents[canonical].append(content)

        # 2개 이상 플랫폼에서 발견된 콘텐츠
        cross_platform = []

        for url, content_list in url_to_contents.items():
            platforms = set(c.source for c in content_list)

            if len(platforms) >= 2:
                # 가장 높은 점수의 콘텐츠를 대표로 선택
                best = max(content_list, key=lambda x: x.score)
                best.platforms_found = list(platforms)
                best.cross_platform_score = len(platforms) / 5  # 최대 5개 플랫폼 기준

                cross_platform.append(best)

        # 크로스 플랫폼 점수순 정렬
        cross_platform.sort(key=lambda x: x.cross_platform_score, reverse=True)

        return cross_platform

    def rank_viral_content(
        self,
        contents: list[ViralContent],
        top_n: int = 20
    ) -> list[ViralContent]:
        """바이럴 점수 기준 랭킹"""
        # viral_score 계산 및 정렬
        ranked = sorted(contents, key=lambda x: x.viral_score, reverse=True)
        return ranked[:top_n]

    def categorize_content(
        self,
        contents: list[ViralContent]
    ) -> dict[str, list[ViralContent]]:
        """카테고리별 분류"""
        by_category = defaultdict(list)

        for content in contents:
            by_category[content.category].append(content)

        # 각 카테고리 내 정렬
        for category in by_category:
            by_category[category].sort(key=lambda x: x.viral_score, reverse=True)

        return dict(by_category)

    def generate_ai_summary(
        self,
        content: ViralContent,
        context: str = ""
    ) -> str:
        """AI로 콘텐츠 요약 생성"""
        if not self.claude:
            return ""

        try:
            prompt = f"""다음 바이럴 콘텐츠를 한국어로 2-3문장으로 요약해주세요.
왜 주목받고 있는지, 핵심 내용이 무엇인지 설명해주세요.

제목: {content.title}
출처: {content.source}
카테고리: {content.category}
점수: {content.score}
설명: {content.description or 'N/A'}
{f'추가 컨텍스트: {context}' if context else ''}

요약:"""

            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        except Exception as e:
            print(f"[ViralDetector] AI 요약 실패: {e}")
            return ""

    def analyze_trend(
        self,
        contents: list[ViralContent]
    ) -> dict:
        """트렌드 분석"""
        if not contents:
            return {}

        # 카테고리별 분포
        category_counts = defaultdict(int)
        for c in contents:
            category_counts[c.category] += 1

        # 플랫폼별 분포
        platform_counts = defaultdict(int)
        for c in contents:
            platform_counts[c.source] += 1

        # 평균 velocity
        avg_velocity = sum(c.velocity for c in contents) / len(contents)

        # 상위 키워드 추출
        all_text = " ".join(
            f"{c.title} {c.description or ''}" for c in contents
        ).lower()

        # 간단한 키워드 추출
        words = re.findall(r'\b[a-z]{4,}\b', all_text)
        word_counts = defaultdict(int)
        for word in words:
            word_counts[word] += 1

        top_keywords = sorted(
            word_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return {
            "total_contents": len(contents),
            "category_distribution": dict(category_counts),
            "platform_distribution": dict(platform_counts),
            "average_velocity": round(avg_velocity, 2),
            "top_keywords": [kw for kw, _ in top_keywords],
        }

    def create_digest(
        self,
        contents: list[ViralContent],
        top_n: int = 20
    ) -> ViralDigest:
        """바이럴 다이제스트 생성"""
        # 크로스 플랫폼 감지
        cross_platform = self.detect_cross_platform(contents)

        # 카테고리별 분류
        by_category = self.categorize_content(contents)

        # 플랫폼별 분류
        by_platform = defaultdict(list)
        for content in contents:
            by_platform[content.source].append(content)

        for platform in by_platform:
            by_platform[platform].sort(key=lambda x: x.viral_score, reverse=True)

        # 상위 바이럴 콘텐츠
        top_viral = self.rank_viral_content(contents, top_n)

        return ViralDigest(
            date=datetime.now(timezone.utc),
            top_viral=top_viral,
            by_category=by_category,
            by_platform=dict(by_platform),
            cross_platform_hits=cross_platform,
            total_collected=len(contents)
        )

    def is_new_viral(self, content: ViralContent, threshold: float = 50.0) -> bool:
        """새로운 바이럴 콘텐츠인지 확인"""
        url_key = self._normalize_url(content.url)

        # 이전 기록 확인
        if url_key in self.history.get("last_scores", {}):
            prev_score = self.history["last_scores"][url_key]
            # 점수가 2배 이상 증가했는지
            if content.score > prev_score * 2:
                return True
            # 이미 처리된 바이럴
            return False

        # 새로운 콘텐츠이고 velocity가 임계값 이상
        return content.velocity >= threshold

    def update_history(self, contents: list[ViralContent]):
        """기록 업데이트"""
        for content in contents:
            url_key = self._normalize_url(content.url)
            self.history["last_scores"][url_key] = content.score
            self.history["urls"][url_key] = {
                "title": content.title,
                "source": content.source,
                "last_seen": datetime.now(timezone.utc).isoformat()
            }

        # 오래된 기록 정리 (30일 이상)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.history["urls"] = {
            k: v for k, v in self.history["urls"].items()
            if v.get("last_seen", "") > cutoff
        }

        self._save_history()


if __name__ == "__main__":
    detector = ViralDetector()

    # 테스트 데이터
    test_contents = [
        ViralContent(
            id="1",
            title="GPT-5 Released",
            url="https://openai.com/gpt5",
            source="hn",
            category="ai",
            score=500,
            velocity=100.0,
            created_at=datetime.now(timezone.utc) - timedelta(hours=5),
            description="OpenAI releases GPT-5"
        ),
        ViralContent(
            id="2",
            title="GPT-5 Released",
            url="https://openai.com/gpt5",
            source="reddit",
            category="ai",
            score=1000,
            velocity=150.0,
            created_at=datetime.now(timezone.utc) - timedelta(hours=4),
            description="OpenAI releases GPT-5"
        ),
    ]

    # 크로스 플랫폼 감지 테스트
    cross = detector.detect_cross_platform(test_contents)
    print(f"Cross-platform hits: {len(cross)}")
    for c in cross:
        print(f"  {c.title} - Found on: {c.platforms_found}")
