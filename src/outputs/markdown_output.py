"""마크다운 출력 모듈"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from collections import defaultdict

if TYPE_CHECKING:
    from ..collectors.rss_collector import Article


class MarkdownOutput:
    """다이제스트를 마크다운으로 출력"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _format_article(self, article: "Article", with_summary: bool = True) -> str:
        """기사를 마크다운 형식으로 포맷"""
        lines = [f"- [{article.title}]({article.url})"]

        # 연구 논문의 경우 저자 표시
        if article.category == "research" and article.authors:
            lines.append(f"  - *{article.authors}*")

        # 요약 표시
        summary = article.ai_summary or article.summary or ""
        if summary and with_summary:
            # HTML 태그 제거 및 정리
            clean_summary = summary.replace("\n", " ").strip()
            if clean_summary.startswith("<"):
                # HTML이 포함된 경우 건너뛰기
                clean_summary = ""
            if clean_summary:
                lines.append(f"  > {clean_summary[:200]}")

        return "\n".join(lines)

    def _group_by_category(self, articles: list["Article"]) -> dict:
        """카테고리별로 기사 그룹화"""
        groups = defaultdict(list)
        for article in articles:
            groups[article.category].append(article)
        return groups

    def _is_media_content(self, article: "Article") -> bool:
        """YouTube, 팟캐스트, 뉴스레터 콘텐츠인지 확인"""
        source_lower = article.source.lower()
        category = article.category.lower()
        return (
            source_lower.startswith("youtube") or
            category in ("podcast", "newsletter") or
            "podcast" in source_lower
        )

    def _separate_media_articles(
        self, articles: list["Article"]
    ) -> tuple[list["Article"], list["Article"]]:
        """미디어 콘텐츠와 일반 기사 분리"""
        media = []
        regular = []
        for article in articles:
            if self._is_media_content(article):
                media.append(article)
            else:
                regular.append(article)
        return media, regular

    def generate(self, articles: list["Article"], top_n: int = 3) -> str:
        """전체 다이제스트 마크다운 생성"""
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [f"# AI Daily Digest - {today}\n"]

        # 미디어 콘텐츠 분리
        media_articles, regular_articles = self._separate_media_articles(articles)

        # 오늘의 하이라이트 (미디어 제외한 기사에서)
        lines.append("## 오늘의 하이라이트\n")
        for article in regular_articles[:top_n]:
            lines.append(self._format_article(article))
        lines.append("")

        # 카테고리별 정리 (미디어 제외)
        grouped = self._group_by_category(regular_articles[top_n:])

        category_names = {
            "bigtech": "빅테크 동향",
            "vc": "VC/투자 동향",
            "research": "AI 연구",
            "news": "AI 뉴스",
            "community": "커뮤니티",
            "korean": "국내 동향"
        }

        for category, name in category_names.items():
            category_articles = grouped.get(category, [])
            if category_articles:
                lines.append(f"## {name}\n")
                for article in category_articles[:10]:
                    lines.append(self._format_article(article, with_summary=True))
                lines.append("")

        # 영상 & 팟캐스트 & 뉴스레터 섹션
        if media_articles:
            lines.append("## 영상 & 팟캐스트 & 뉴스레터\n")
            for article in media_articles:
                # 출처 표시
                source_tag = f"[{article.source}]" if not article.source.startswith("YouTube") else ""
                lines.append(self._format_article(article, with_summary=True))
            lines.append("")

        return "\n".join(lines)

    def save(self, articles: list["Article"], filename: str = "") -> str:
        """마크다운 파일 저장"""
        if not filename:
            today = datetime.now().strftime("%Y-%m-%d")
            filename = f"digest_{today}.md"

        content = self.generate(articles)
        filepath = self.output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"다이제스트 저장: {filepath}")
        return str(filepath)
