"""콘텐츠 파서 - 이메일에서 콘텐츠 추출 및 분류"""

import re
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from urllib.parse import urlparse, parse_qs


class ContentType(Enum):
    """콘텐츠 타입"""
    YOUTUBE = "youtube"
    ARTICLE = "article"
    IMAGE = "image"
    PDF = "pdf"
    TWITTER = "twitter"
    GITHUB = "github"
    UNKNOWN = "unknown"


@dataclass
class ParsedContent:
    """파싱된 콘텐츠"""
    url: str
    content_type: ContentType
    title: Optional[str] = None
    description: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class ContentParser:
    """이메일 콘텐츠 파싱 및 분류"""

    # 이미지 확장자
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}

    # PDF 확장자
    PDF_EXTENSION = ".pdf"

    # YouTube URL 패턴
    YOUTUBE_PATTERNS = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]

    # Twitter/X URL 패턴
    TWITTER_PATTERNS = [
        r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/\w+/status/(\d+)",
    ]

    # GitHub URL 패턴
    GITHUB_PATTERNS = [
        r"(?:https?://)?(?:www\.)?github\.com/([^/]+/[^/]+)",
    ]

    def classify_url(self, url: str) -> ContentType:
        """URL 타입 분류"""
        url_lower = url.lower()
        parsed = urlparse(url)
        path = parsed.path.lower()

        # YouTube 체크
        for pattern in self.YOUTUBE_PATTERNS:
            if re.search(pattern, url):
                return ContentType.YOUTUBE

        # Twitter/X 체크
        for pattern in self.TWITTER_PATTERNS:
            if re.search(pattern, url):
                return ContentType.TWITTER

        # GitHub 체크
        for pattern in self.GITHUB_PATTERNS:
            if re.search(pattern, url):
                return ContentType.GITHUB

        # 이미지 체크
        for ext in self.IMAGE_EXTENSIONS:
            if path.endswith(ext):
                return ContentType.IMAGE

        # PDF 체크
        if path.endswith(self.PDF_EXTENSION):
            return ContentType.PDF

        # 나머지는 아티클로 분류
        return ContentType.ARTICLE

    def extract_youtube_id(self, url: str) -> Optional[str]:
        """YouTube 비디오 ID 추출"""
        for pattern in self.YOUTUBE_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # URL 파라미터에서 추출 시도
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "v" in params:
            return params["v"][0]

        return None

    def extract_twitter_id(self, url: str) -> Optional[str]:
        """Twitter 트윗 ID 추출"""
        for pattern in self.TWITTER_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def extract_github_repo(self, url: str) -> Optional[str]:
        """GitHub 저장소 경로 추출"""
        for pattern in self.GITHUB_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def parse_url(self, url: str) -> ParsedContent:
        """URL 파싱 및 메타데이터 추출"""
        content_type = self.classify_url(url)
        metadata = {}

        if content_type == ContentType.YOUTUBE:
            video_id = self.extract_youtube_id(url)
            if video_id:
                metadata["video_id"] = video_id
                metadata["thumbnail"] = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        elif content_type == ContentType.TWITTER:
            tweet_id = self.extract_twitter_id(url)
            if tweet_id:
                metadata["tweet_id"] = tweet_id

        elif content_type == ContentType.GITHUB:
            repo = self.extract_github_repo(url)
            if repo:
                metadata["repo"] = repo

        return ParsedContent(
            url=url,
            content_type=content_type,
            metadata=metadata
        )

    def parse_email_body(self, text: str, html: str) -> list[ParsedContent]:
        """이메일 본문에서 모든 콘텐츠 추출"""
        contents = []
        seen_urls = set()

        # URL 추출 패턴
        url_pattern = r'https?://[^\s<>"\')\]}>]+'

        for body in [text, html]:
            if not body:
                continue

            urls = re.findall(url_pattern, body)
            for url in urls:
                # 정리
                url = url.rstrip(".,;:!?")

                # 중복 제거
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # 트래킹 URL 필터링
                if self._is_tracking_url(url):
                    continue

                # 너무 짧은 URL 필터링
                if len(url) < 15:
                    continue

                content = self.parse_url(url)
                contents.append(content)

        return contents

    def _is_tracking_url(self, url: str) -> bool:
        """트래킹/분석 URL 필터링"""
        tracking_domains = [
            "doubleclick.net",
            "google-analytics.com",
            "googleadservices.com",
            "facebook.com/tr",
            "analytics.",
            "tracker.",
            "click.",
            "track.",
            "open.substack.com",
            "email.mg.",
            "list-manage.com",
            "mailchimp.com",
        ]

        url_lower = url.lower()
        return any(domain in url_lower for domain in tracking_domains)

    def filter_by_type(
        self,
        contents: list[ParsedContent],
        content_types: list[ContentType]
    ) -> list[ParsedContent]:
        """특정 타입의 콘텐츠만 필터링"""
        return [c for c in contents if c.content_type in content_types]

    def get_youtube_contents(self, contents: list[ParsedContent]) -> list[ParsedContent]:
        """YouTube 콘텐츠만 추출"""
        return self.filter_by_type(contents, [ContentType.YOUTUBE])

    def get_article_contents(self, contents: list[ParsedContent]) -> list[ParsedContent]:
        """아티클 콘텐츠만 추출"""
        return self.filter_by_type(contents, [ContentType.ARTICLE])

    def get_image_contents(self, contents: list[ParsedContent]) -> list[ParsedContent]:
        """이미지 콘텐츠만 추출"""
        return self.filter_by_type(contents, [ContentType.IMAGE])


if __name__ == "__main__":
    parser = ContentParser()

    # 테스트 URL들
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://twitter.com/user/status/1234567890",
        "https://github.com/anthropics/claude-code",
        "https://example.com/article/test",
        "https://example.com/image.jpg",
    ]

    for url in test_urls:
        content = parser.parse_url(url)
        print(f"{url}")
        print(f"  타입: {content.content_type.value}")
        print(f"  메타: {content.metadata}")
        print()
