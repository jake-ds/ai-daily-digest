"""노션 API 출력 모듈"""

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Union
from collections import defaultdict

try:
    from notion_client import Client
except ImportError:
    Client = None

if TYPE_CHECKING:
    from ..collectors.rss_collector import Article
    from ..processors.viral_detector import ViralContent, ViralDigest


class NotionArticlesDB:
    """개별 기사를 저장하는 Notion 데이터베이스 (LinkedIn 선택용)"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        database_id: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        self.database_id = database_id or os.getenv("NOTION_ARTICLES_DATABASE_ID")
        self.client = None

        if Client and self.api_key:
            self.client = Client(auth=self.api_key)

    def is_available(self) -> bool:
        """Notion API 사용 가능 여부"""
        return self.client is not None and self.database_id is not None

    def create_article_pages(self, articles: list["Article"]) -> list[str]:
        """각 기사를 개별 페이지로 생성

        Args:
            articles: 저장할 기사 목록

        Returns:
            생성된 페이지 ID 목록
        """
        if not self.is_available():
            print("노션 Articles DB가 설정되지 않았습니다.")
            print("NOTION_ARTICLES_DATABASE_ID 환경변수를 설정하세요.")
            return []

        page_ids = []
        today = datetime.now().strftime("%Y-%m-%d")

        for article in articles:
            try:
                # 요약 텍스트 준비 (2000자 제한)
                summary_text = article.ai_summary or article.summary or ""
                if summary_text:
                    summary_text = summary_text[:2000]

                properties = {
                    "Title": {
                        "title": [{"text": {"content": article.title[:100]}}]
                    },
                    "URL": {"url": article.url},
                    "Source": {"select": {"name": article.source[:100]}},
                    "Category": {"select": {"name": article.category}},
                    "Date": {"date": {"start": today}},
                    "Summary": {
                        "rich_text": [{"text": {"content": summary_text}}]
                    },
                    "Score": {"number": article.score},
                    "LinkedIn Status": {"select": {"name": "None"}},
                }

                response = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties
                )
                page_ids.append(response["id"])

            except Exception as e:
                print(f"  페이지 생성 실패 [{article.title[:30]}...]: {e}")

        print(f"개별 기사 페이지 {len(page_ids)}개 생성 완료")
        return page_ids

    def query_requested_articles(self) -> list[dict]:
        """LinkedIn Status가 'Requested'인 기사 조회

        Returns:
            Notion 페이지 목록
        """
        if not self.is_available():
            return []

        try:
            response = self.client.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "LinkedIn Status",
                    "select": {"equals": "Requested"}
                }
            )
            return response.get("results", [])
        except Exception as e:
            print(f"기사 조회 실패: {e}")
            return []

    def update_linkedin_draft(
        self,
        page_id: str,
        draft: str,
        scenario: str
    ) -> bool:
        """LinkedIn 초안 업데이트

        Args:
            page_id: Notion 페이지 ID
            draft: 생성된 LinkedIn 초안
            scenario: 시나리오 유형 (A-E)

        Returns:
            성공 여부
        """
        if not self.client:
            return False

        try:
            # 초안 텍스트 제한 (Notion rich_text 2000자 제한)
            draft_text = draft[:2000] if len(draft) > 2000 else draft

            self.client.pages.update(
                page_id=page_id,
                properties={
                    "LinkedIn Status": {"select": {"name": "Generated"}},
                    "LinkedIn Draft": {
                        "rich_text": [{"text": {"content": draft_text}}]
                    },
                    "Scenario": {"select": {"name": scenario}}
                }
            )
            return True
        except Exception as e:
            print(f"LinkedIn 초안 업데이트 실패: {e}")
            return False

    def extract_article_data(self, page: dict) -> dict:
        """Notion 페이지에서 기사 데이터 추출

        Args:
            page: Notion 페이지 객체

        Returns:
            기사 데이터 딕셔너리
        """
        props = page.get("properties", {})

        # Title 추출
        title_prop = props.get("Title", {}).get("title", [])
        title = title_prop[0]["text"]["content"] if title_prop else ""

        # URL 추출
        url = props.get("URL", {}).get("url", "")

        # Source 추출
        source_prop = props.get("Source", {}).get("select")
        source = source_prop["name"] if source_prop else ""

        # Category 추출
        category_prop = props.get("Category", {}).get("select")
        category = category_prop["name"] if category_prop else ""

        # Summary 추출
        summary_prop = props.get("Summary", {}).get("rich_text", [])
        summary = summary_prop[0]["text"]["content"] if summary_prop else ""

        # Score 추출
        score = props.get("Score", {}).get("number", 0)

        return {
            "page_id": page["id"],
            "title": title,
            "url": url,
            "source": source,
            "category": category,
            "summary": summary,
            "score": score
        }

    def create_viral_pages(self, viral_contents: list["ViralContent"]) -> list[str]:
        """바이럴 콘텐츠를 개별 페이지로 생성

        Args:
            viral_contents: 저장할 바이럴 콘텐츠 목록

        Returns:
            생성된 페이지 ID 목록
        """
        if not self.is_available():
            print("[Notion] Articles DB가 설정되지 않았습니다.")
            return []

        page_ids = []
        today = datetime.now().strftime("%Y-%m-%d")

        for viral in viral_contents:
            try:
                # 요약 텍스트 준비 (2000자 제한)
                summary_text = viral.ai_summary or viral.description or ""
                if summary_text:
                    summary_text = summary_text[:2000]

                # 플랫폼 표시
                source_name = f"Viral-{viral.source.upper()}"
                if viral.platforms_found:
                    source_name = f"Viral-CrossPlatform ({', '.join(viral.platforms_found)})"

                properties = {
                    "Title": {
                        "title": [{"text": {"content": viral.title[:100]}}]
                    },
                    "URL": {"url": viral.url},
                    "Source": {"select": {"name": source_name[:100]}},
                    "Category": {"select": {"name": viral.category}},
                    "Date": {"date": {"start": today}},
                    "Summary": {
                        "rich_text": [{"text": {"content": summary_text}}]
                    },
                    "Score": {"number": viral.score},
                    "LinkedIn Status": {"select": {"name": "None"}},
                }

                response = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties
                )
                page_ids.append(response["id"])

            except Exception as e:
                print(f"  [Notion] 바이럴 페이지 생성 실패 [{viral.title[:30]}...]: {e}")

        print(f"[Notion] 바이럴 페이지 {len(page_ids)}개 생성 완료")
        return page_ids


class NotionOutput:
    """노션 데이터베이스에 다이제스트 저장"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        database_id: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID")
        self.client = None

        if Client and self.api_key:
            self.client = Client(auth=self.api_key)

    def is_available(self) -> bool:
        """노션 API 사용 가능 여부"""
        return self.client is not None and self.database_id is not None

    def _create_text_block(self, text: str, bold: bool = False) -> dict:
        """텍스트 블록 생성"""
        # Notion API 제한: 2000자
        if len(text) > 2000:
            text = text[:1997] + "..."
        return {
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": text},
                    "annotations": {"bold": bold}
                }]
            }
        }

    def _create_heading_block(self, text: str, level: int = 2) -> dict:
        """헤딩 블록 생성"""
        heading_type = f"heading_{level}"
        return {
            "type": heading_type,
            heading_type: {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": text}
                }]
            }
        }

    def _create_bookmark_block(self, url: str, caption: str = "") -> dict:
        """북마크 블록 생성"""
        block = {
            "type": "bookmark",
            "bookmark": {"url": url}
        }
        if caption:
            block["bookmark"]["caption"] = [{
                "type": "text",
                "text": {"content": caption[:100]}
            }]
        return block

    def _create_bulleted_item(self, text: str, url: Optional[str] = None) -> dict:
        """불릿 리스트 아이템 생성"""
        if url:
            rich_text = [{
                "type": "text",
                "text": {"content": text, "link": {"url": url}}
            }]
        else:
            rich_text = [{
                "type": "text",
                "text": {"content": text}
            }]

        return {
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich_text}
        }

    def _create_callout_block(self, text: str, emoji: str = "💡") -> dict:
        """콜아웃 블록 생성"""
        return {
            "type": "callout",
            "callout": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": text}
                }],
                "icon": {"type": "emoji", "emoji": emoji}
            }
        }

    def _create_divider_block(self) -> dict:
        """구분선 블록"""
        return {"type": "divider", "divider": {}}

    def _group_by_category(self, articles: list["Article"]) -> dict:
        """카테고리별 그룹화"""
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

    def _build_page_content(self, articles: list["Article"], top_n: int = 3) -> list[dict]:
        """페이지 콘텐츠 블록 생성"""
        blocks = []

        # 미디어 콘텐츠 분리
        media_articles, regular_articles = self._separate_media_articles(articles)

        # 오늘의 하이라이트
        blocks.append(self._create_heading_block("오늘의 하이라이트", 2))

        for article in regular_articles[:top_n]:
            summary = article.ai_summary or article.summary or ""
            blocks.append(self._create_bulleted_item(
                article.title[:80],
                article.url
            ))
            # 연구의 경우 저자 표시 (200자 제한)
            if article.category == "research" and article.authors:
                authors_text = article.authors[:200] + "..." if len(article.authors) > 200 else article.authors
                blocks.append(self._create_text_block(f"  👤 {authors_text}"))
            # 요약 표시
            if summary and not summary.strip().startswith("<"):
                clean_summary = summary.replace("\n", " ").strip()[:150]
                blocks.append(self._create_text_block(f"  → {clean_summary}"))

        blocks.append(self._create_divider_block())

        # 카테고리별 정리 (미디어 제외)
        category_names = {
            "bigtech": ("빅테크 동향", "🏢"),
            "vc": ("VC/투자 동향", "💰"),
            "research": ("AI 연구", "🔬"),
            "news": ("AI 뉴스", "📰"),
            "community": ("커뮤니티", "💬"),
            "korean": ("국내 동향", "🇰🇷")
        }

        grouped = self._group_by_category(regular_articles[top_n:])

        for category, (name, emoji) in category_names.items():
            category_articles = grouped.get(category, [])
            if category_articles:
                blocks.append(self._create_heading_block(f"{emoji} {name}", 2))

                for article in category_articles[:8]:
                    blocks.append(self._create_bulleted_item(
                        article.title[:70],
                        article.url
                    ))
                    # 연구의 경우 저자 표시 (200자 제한)
                    if category == "research" and article.authors:
                        authors_text = article.authors[:200] + "..." if len(article.authors) > 200 else article.authors
                        blocks.append(self._create_text_block(f"  👤 {authors_text}"))
                    # 요약 표시
                    summary = article.ai_summary or article.summary or ""
                    if summary and not summary.strip().startswith("<"):
                        clean_summary = summary.replace("\n", " ").strip()[:150]
                        blocks.append(self._create_text_block(f"  → {clean_summary}"))

        # 영상 & 팟캐스트 & 뉴스레터 섹션
        if media_articles:
            blocks.append(self._create_divider_block())
            blocks.append(self._create_heading_block("🎬 영상 & 팟캐스트 & 뉴스레터", 2))

            for article in media_articles:
                blocks.append(self._create_bulleted_item(
                    article.title[:70],
                    article.url
                ))
                # 출처 표시 (카테고리에 따라 아이콘 변경)
                if article.source.lower().startswith("youtube"):
                    icon = "📺"
                elif article.category == "podcast":
                    icon = "🎙️"
                else:
                    icon = "📧"
                blocks.append(self._create_text_block(f"  {icon} {article.source}"))
                # 요약 표시
                summary = article.ai_summary or article.summary or ""
                if summary and not summary.strip().startswith("<"):
                    clean_summary = summary.replace("\n", " ").strip()[:150]
                    blocks.append(self._create_text_block(f"  → {clean_summary}"))

        return blocks

    def create_page(self, articles: list["Article"], top_n: int = 3) -> Optional[str]:
        """노션 데이터베이스에 새 페이지 생성"""
        if not self.is_available():
            print("노션 API가 설정되지 않았습니다.")
            print("NOTION_API_KEY와 NOTION_DATABASE_ID 환경변수를 설정하세요.")
            return None

        today = datetime.now()
        title = f"AI Daily Digest - {today.strftime('%Y-%m-%d')}"

        # 페이지 프로퍼티
        properties = {
            "Name": {
                "title": [{
                    "text": {"content": title}
                }]
            },
            "Date": {
                "date": {"start": today.strftime("%Y-%m-%d")}
            },
            "Articles": {
                "number": len(articles)
            },
            "Status": {
                "select": {"name": "Published"}
            }
        }

        # 페이지 콘텐츠
        children = self._build_page_content(articles, top_n)

        try:
            # 페이지 생성 (블록은 100개씩 제한)
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children[:100]
            )

            page_id = response["id"]
            page_url = response["url"]

            # 100개 초과 블록 추가
            if len(children) > 100:
                for i in range(100, len(children), 100):
                    self.client.blocks.children.append(
                        block_id=page_id,
                        children=children[i:i+100]
                    )

            print(f"노션 페이지 생성 완료: {page_url}")
            return page_url

        except Exception as e:
            print(f"노션 페이지 생성 실패: {e}")
            return None

    def check_today_exists(self) -> bool:
        """오늘 다이제스트가 이미 있는지 확인"""
        if not self.is_available():
            return False

        today = datetime.now().strftime("%Y-%m-%d")

        try:
            response = self.client.databases.query(
                database_id=self.database_id,
                filter={
                    "property": "Date",
                    "date": {"equals": today}
                }
            )
            return len(response.get("results", [])) > 0
        except Exception:
            return False

    def create_viral_digest_page(
        self,
        viral_digest: "ViralDigest",
        top_n: int = 20
    ) -> Optional[str]:
        """바이럴 다이제스트 페이지 생성

        Args:
            viral_digest: 바이럴 다이제스트 객체
            top_n: 표시할 상위 콘텐츠 수

        Returns:
            생성된 페이지 URL
        """
        if not self.is_available():
            print("[Notion] API가 설정되지 않았습니다.")
            return None

        today = datetime.now()
        title = f"Viral Digest - {today.strftime('%Y-%m-%d')}"

        # 페이지 프로퍼티
        properties = {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Date": {
                "date": {"start": today.strftime("%Y-%m-%d")}
            },
            "Articles": {
                "number": viral_digest.total_collected
            },
            "Status": {
                "select": {"name": "Published"}
            }
        }

        # 페이지 콘텐츠 생성
        children = self._build_viral_content(viral_digest, top_n)

        try:
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children[:100]
            )

            page_id = response["id"]
            page_url = response["url"]

            # 100개 초과 블록 추가
            if len(children) > 100:
                for i in range(100, len(children), 100):
                    self.client.blocks.children.append(
                        block_id=page_id,
                        children=children[i:i+100]
                    )

            print(f"[Notion] 바이럴 다이제스트 생성 완료: {page_url}")
            return page_url

        except Exception as e:
            print(f"[Notion] 바이럴 다이제스트 생성 실패: {e}")
            return None

    def _build_viral_content(
        self,
        viral_digest: "ViralDigest",
        top_n: int = 20
    ) -> list[dict]:
        """바이럴 다이제스트 콘텐츠 블록 생성"""
        blocks = []

        # 통계 콜아웃
        stats_text = f"총 {viral_digest.total_collected}개 수집 | 크로스 플랫폼: {len(viral_digest.cross_platform_hits)}개"
        blocks.append(self._create_callout_block(stats_text, "📊"))

        # 크로스 플랫폼 바이럴 (가장 중요)
        if viral_digest.cross_platform_hits:
            blocks.append(self._create_heading_block("🔥 크로스 플랫폼 바이럴", 2))
            blocks.append(self._create_text_block("여러 플랫폼에서 동시에 화제가 된 콘텐츠"))

            for viral in viral_digest.cross_platform_hits[:5]:
                platforms = ", ".join(viral.platforms_found)
                blocks.append(self._create_bulleted_item(
                    f"[{platforms}] {viral.title[:60]}",
                    viral.url
                ))
                if viral.description:
                    blocks.append(self._create_text_block(f"  → {viral.description[:150]}"))

            blocks.append(self._create_divider_block())

        # Top 바이럴
        blocks.append(self._create_heading_block("🚀 Top Viral", 2))

        for i, viral in enumerate(viral_digest.top_viral[:top_n], 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "📌"
            blocks.append(self._create_bulleted_item(
                f"{emoji} [{viral.source.upper()}] {viral.title[:55]}",
                viral.url
            ))
            score_text = f"Score: {viral.score:,} | Velocity: {viral.velocity:.1f}/hr"
            blocks.append(self._create_text_block(f"  {score_text}"))
            if viral.ai_summary:
                blocks.append(self._create_text_block(f"  → {viral.ai_summary[:150]}"))
            elif viral.description:
                blocks.append(self._create_text_block(f"  → {viral.description[:150]}"))

        blocks.append(self._create_divider_block())

        # 카테고리별 정리
        category_emoji = {
            "ai": "🤖",
            "saas": "💼",
            "vc": "💰",
            "tech": "💻"
        }

        for category, contents in viral_digest.by_category.items():
            if contents:
                emoji = category_emoji.get(category, "📁")
                blocks.append(self._create_heading_block(f"{emoji} {category.upper()}", 2))

                for viral in contents[:8]:
                    blocks.append(self._create_bulleted_item(
                        f"[{viral.source}] {viral.title[:55]}",
                        viral.url
                    ))

        return blocks


    def create_combined_digest_page(
        self,
        articles: list["Article"] = None,
        viral_digest: "ViralDigest" = None,
        top_viral: int = 15,
        top_articles: int = 3
    ) -> Optional[str]:
        """바이럴 + 뉴스 통합 다이제스트 페이지 생성

        Args:
            articles: 뉴스 기사 목록
            viral_digest: 바이럴 다이제스트
            top_viral: 표시할 바이럴 콘텐츠 수
            top_articles: 하이라이트로 표시할 기사 수

        Returns:
            생성된 페이지 URL
        """
        if not self.is_available():
            print("[Notion] API가 설정되지 않았습니다.")
            return None

        today = datetime.now()
        title = f"AI Daily Digest - {today.strftime('%Y-%m-%d')}"

        # 통계 계산
        total_articles = len(articles) if articles else 0
        total_viral = viral_digest.total_collected if viral_digest else 0

        # 페이지 프로퍼티
        properties = {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Date": {
                "date": {"start": today.strftime("%Y-%m-%d")}
            },
            "Articles": {
                "number": total_articles + total_viral
            },
            "Status": {
                "select": {"name": "Published"}
            }
        }

        # 페이지 콘텐츠 생성
        children = []

        # 통계 콜아웃
        stats_parts = []
        if viral_digest:
            stats_parts.append(f"바이럴: {total_viral}개")
            if viral_digest.cross_platform_hits:
                stats_parts.append(f"크로스플랫폼: {len(viral_digest.cross_platform_hits)}개")
        if articles:
            stats_parts.append(f"뉴스: {total_articles}개")

        if stats_parts:
            children.append(self._create_callout_block(" | ".join(stats_parts), "📊"))

        # === 글로벌 바이럴 섹션 ===
        if viral_digest and viral_digest.top_viral:
            children.append(self._create_heading_block("🔥 글로벌 바이럴", 1))

            # 크로스 플랫폼
            if viral_digest.cross_platform_hits:
                children.append(self._create_heading_block("🌐 크로스 플랫폼 (다중 채널 화제)", 2))
                for viral in viral_digest.cross_platform_hits[:3]:
                    platforms = ", ".join(viral.platforms_found)
                    children.append(self._create_bulleted_item(
                        f"[{platforms}] {viral.title[:55]}",
                        viral.url
                    ))
                    if viral.ai_summary or viral.description:
                        summary = viral.ai_summary or viral.description
                        children.append(self._create_text_block(f"  → {summary[:120]}"))

            # Top 바이럴
            children.append(self._create_heading_block("🚀 Top Viral", 2))

            for i, viral in enumerate(viral_digest.top_viral[:top_viral], 1):
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else ""
                prefix = f"{emoji} " if emoji else ""
                children.append(self._create_bulleted_item(
                    f"{prefix}[{viral.source.upper()}] {viral.title[:50]}",
                    viral.url
                ))
                score_text = f"Score: {viral.score:,} | Velocity: {viral.velocity:.1f}/hr"
                children.append(self._create_text_block(f"  {score_text}"))
                if viral.ai_summary:
                    children.append(self._create_text_block(f"  → {viral.ai_summary[:100]}"))

            # 카테고리별 요약
            children.append(self._create_heading_block("📁 카테고리별", 2))
            category_emoji = {"ai": "🤖", "saas": "💼", "vc": "💰", "tech": "💻"}

            for category, contents in viral_digest.by_category.items():
                if contents:
                    emoji = category_emoji.get(category, "📁")
                    children.append(self._create_text_block(f"{emoji} {category.upper()}: {len(contents)}개", bold=True))
                    for viral in contents[:3]:
                        children.append(self._create_bulleted_item(
                            f"[{viral.source}] {viral.title[:50]}",
                            viral.url
                        ))

            children.append(self._create_divider_block())

        # === 뉴스 섹션 ===
        if articles:
            children.append(self._create_heading_block("📰 뉴스 & 리서치", 1))

            # 미디어 콘텐츠 분리
            media_articles, regular_articles = self._separate_media_articles(articles)

            # 오늘의 하이라이트
            if regular_articles:
                children.append(self._create_heading_block("⭐ 하이라이트", 2))
                for article in regular_articles[:top_articles]:
                    children.append(self._create_bulleted_item(
                        article.title[:70],
                        article.url
                    ))
                    summary = article.ai_summary or article.summary or ""
                    if summary and not summary.strip().startswith("<"):
                        children.append(self._create_text_block(f"  → {summary[:120]}"))

            # 카테고리별
            grouped = self._group_by_category(regular_articles[top_articles:])
            category_names = {
                "bigtech": ("빅테크", "🏢"),
                "vc": ("VC/투자", "💰"),
                "research": ("연구", "🔬"),
                "news": ("뉴스", "📰"),
                "community": ("커뮤니티", "💬"),
                "korean": ("국내", "🇰🇷")
            }

            for category, (name, emoji) in category_names.items():
                category_articles = grouped.get(category, [])
                if category_articles:
                    children.append(self._create_heading_block(f"{emoji} {name}", 2))
                    for article in category_articles[:5]:
                        children.append(self._create_bulleted_item(
                            article.title[:60],
                            article.url
                        ))

            # 미디어 섹션
            if media_articles:
                children.append(self._create_heading_block("🎬 영상 & 팟캐스트", 2))
                for article in media_articles[:5]:
                    children.append(self._create_bulleted_item(
                        article.title[:60],
                        article.url
                    ))

        try:
            response = self.client.pages.create(
                parent={"database_id": self.database_id},
                properties=properties,
                children=children[:100]
            )

            page_id = response["id"]
            page_url = response["url"]

            # 100개 초과 블록 추가
            if len(children) > 100:
                for i in range(100, len(children), 100):
                    self.client.blocks.children.append(
                        block_id=page_id,
                        children=children[i:i+100]
                    )

            print(f"[Notion] 통합 다이제스트 생성 완료: {page_url}")
            return page_url

        except Exception as e:
            print(f"[Notion] 통합 다이제스트 생성 실패: {e}")
            return None


def setup_notion_database():
    """노션 데이터베이스 설정 가이드 출력"""
    guide = """
╔══════════════════════════════════════════════════════════════╗
║                    노션 API 설정 가이드                        ║
╚══════════════════════════════════════════════════════════════╝

1. 노션 Integration 생성
   → https://www.notion.so/my-integrations
   → "New integration" 클릭
   → 이름 입력 (예: AI Daily Digest)
   → "Internal Integration Token" 복사

2. 데이터베이스 생성
   → 노션에서 새 데이터베이스 생성 (Full page database)
   → 다음 속성 추가:
     • Name (title) - 기본 제목
     • Date (date) - 날짜
     • Articles (number) - 기사 수
     • Status (select) - 상태 (Published, Draft)

3. Integration 연결
   → 데이터베이스 페이지 우측 상단 "..." 클릭
   → "Connections" → 생성한 Integration 선택

4. Database ID 확인
   → 데이터베이스 URL에서 추출
   → https://notion.so/workspace/DATABASE_ID?v=...
   → DATABASE_ID 부분 복사 (32자리 문자열)

5. 환경변수 설정
   export NOTION_API_KEY="secret_xxxxx..."
   export NOTION_DATABASE_ID="xxxxxxxx..."

또는 .env 파일 생성:
   NOTION_API_KEY=secret_xxxxx...
   NOTION_DATABASE_ID=xxxxxxxx...
"""
    print(guide)


def setup_articles_database():
    """AI Articles 데이터베이스 설정 가이드 출력"""
    guide = """
╔══════════════════════════════════════════════════════════════╗
║              AI Articles 데이터베이스 설정 가이드               ║
╚══════════════════════════════════════════════════════════════╝

기존 AI Daily Digest DB 외에, 개별 기사 관리용 DB를 추가로 생성합니다.

1. 새 데이터베이스 생성
   → 노션에서 새 데이터베이스 생성 (Full page database)
   → 이름: "AI Articles" (또는 원하는 이름)

2. 다음 속성 추가:
   • Title (title) - 기사 제목
   • URL (url) - 원문 링크
   • Source (select) - 출처
   • Category (select) - 카테고리 (bigtech, news, research 등)
   • Date (date) - 수집일
   • Summary (rich text) - AI 요약
   • Score (number) - 관심도 점수
   • LinkedIn Status (select) - None / Requested / Generated
   • LinkedIn Draft (rich text) - 생성된 초안
   • Scenario (select) - A / B / C / D / E

3. Integration 연결
   → 데이터베이스 페이지 우측 상단 "..." 클릭
   → "Connections" → 기존 Integration 선택

4. Database ID 확인 및 환경변수 설정
   → URL에서 Database ID 복사

   .env 파일에 추가:
   NOTION_ARTICLES_DATABASE_ID=xxxxxxxx...

5. 사용 흐름
   ① main.py --notion --articles-db  → 기사 개별 페이지 생성
   ② Notion에서 LinkedIn Status를 "Requested"로 변경
   ③ python linkedin_worker.py  → 초안 자동 생성
   ④ Notion에서 생성된 초안 확인 및 수정
"""
    print(guide)


if __name__ == "__main__":
    setup_notion_database()
    setup_articles_database()
