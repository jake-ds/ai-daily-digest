"""Digest service wrapping the existing collection logic."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, List

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.orm import Session

from src.collectors.rss_collector import RSSCollector, Article as RSSArticle
from src.collectors.hn_collector import HackerNewsCollector
from src.collectors.viral_aggregator import ViralAggregator
from src.processors.dedup import Deduplicator
from src.processors.scorer import Scorer
from src.processors.summarizer import Summarizer
from src.collectors.arxiv_enricher import ArxivEnricher
from src.outputs.notion_output import NotionOutput

from web.models import Article, Collection
from web.config import DEFAULT_COLLECTION_HOURS, DEFAULT_HN_LIMIT, DEFAULT_ARTICLE_LIMIT


CollectionType = Literal["news", "viral", "all"]


class DigestService:
    """Service for running digest collections and storing results."""

    def __init__(self, db: Session):
        self.db = db
        self.rss_collector = RSSCollector()
        self.hn_collector = HackerNewsCollector()
        self.viral_aggregator = ViralAggregator()
        self.deduplicator = Deduplicator()
        self.scorer = Scorer()
        self.summarizer = Summarizer()
        self.arxiv_enricher = ArxivEnricher()
        self.notion_output = NotionOutput()

    def _update_progress(self, collection_id: int, stage: str, detail: str = None):
        """Update collection progress stage."""
        collection = self.db.query(Collection).filter(Collection.id == collection_id).first()
        if collection:
            collection.progress_stage = stage
            collection.progress_detail = detail
            self.db.commit()
            print(f"[Progress] {stage}: {detail or ''}")

    def run_collection(
        self,
        collection_type: CollectionType = "all",
        hours: int = DEFAULT_COLLECTION_HOURS,
        limit: int = DEFAULT_ARTICLE_LIMIT,
        skip_notion: bool = False,
    ) -> Collection:
        """
        Run a collection based on type.

        Args:
            collection_type: Type of collection (news, viral, all)
            hours: How many hours back to collect
            limit: Maximum articles to process
            skip_notion: Skip Notion sync

        Returns:
            Collection record with results
        """
        # Create collection record
        collection = Collection(
            name=f"{collection_type.title()} Digest {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            type=collection_type,
            status="running",
            progress_stage="starting",
            progress_detail="컬렉션 초기화 중...",
        )
        self.db.add(collection)
        self.db.commit()
        self.db.refresh(collection)

        try:
            articles = []

            # Collect based on type
            if collection_type in ("news", "all"):
                articles.extend(self._collect_news(hours, collection.id))

            if collection_type in ("viral", "all"):
                articles.extend(self._collect_viral(collection.id))

            # Process articles
            articles = self._process_articles(articles, limit, collection.id)

            # Store in database
            self._update_progress(collection.id, "storing", "데이터베이스에 저장 중...")
            stored_count = self._store_articles(articles, collection.id)
            self._update_progress(collection.id, "storing", f"{stored_count}개 기사 저장 완료")

            # AI evaluation for stored articles
            try:
                self._update_progress(collection.id, "evaluating", "AI 평가 중...")
                from web.services.evaluation_service import EvaluationService
                eval_service = EvaluationService(self.db)
                eval_result = eval_service.batch_evaluate(limit=stored_count)
                self._update_progress(
                    collection.id, "evaluating",
                    f"{eval_result['processed']}개 기사 AI 평가 완료"
                )
            except Exception as e:
                self._update_progress(collection.id, "evaluating", f"AI 평가 오류: {str(e)[:50]}")
                print(f"AI evaluation error: {e}")

            # Sync to Notion if enabled
            notion_url = None
            if not skip_notion and articles:
                try:
                    self._update_progress(collection.id, "syncing_notion", "Notion 페이지 생성 중...")
                    notion_url = self.notion_output.create_page(articles)
                    self._update_progress(collection.id, "syncing_notion", "Notion 동기화 완료")
                except Exception as e:
                    self._update_progress(collection.id, "syncing_notion", f"Notion 동기화 실패: {str(e)[:50]}")
                    print(f"Notion sync failed: {e}")

            # Update collection record
            collection = self.db.query(Collection).filter(Collection.id == collection.id).first()
            collection.status = "completed"
            collection.article_count = stored_count
            collection.notion_page_url = notion_url
            collection.completed_at = datetime.utcnow()
            collection.progress_stage = "completed"
            collection.progress_detail = f"총 {stored_count}개 기사 수집 완료"
            self.db.commit()
            self.db.refresh(collection)

            return collection

        except Exception as e:
            collection = self.db.query(Collection).filter(Collection.id == collection.id).first()
            collection.status = "failed"
            collection.error_message = str(e)
            collection.completed_at = datetime.utcnow()
            collection.progress_stage = "failed"
            collection.progress_detail = str(e)[:100]
            self.db.commit()
            raise

    def _collect_news(self, hours: int, collection_id: int) -> list:
        """Collect news from RSS feeds and HN."""
        articles = []

        # RSS feeds
        self._update_progress(collection_id, "collecting_rss", "RSS 피드 수집 시작...")
        try:
            rss_articles = self.rss_collector.collect_all(hours=hours)
            articles.extend(rss_articles)
            self._update_progress(collection_id, "collecting_rss", f"{len(rss_articles)}개 RSS 기사 수집")
        except Exception as e:
            self._update_progress(collection_id, "collecting_rss", f"RSS 오류: {str(e)[:50]}")
            print(f"RSS collection error: {e}")

        # Hacker News
        self._update_progress(collection_id, "collecting_hn", "Hacker News 수집 중...")
        try:
            hn_articles = self.hn_collector.collect(limit=DEFAULT_HN_LIMIT)
            articles.extend(hn_articles)
            self._update_progress(collection_id, "collecting_hn", f"{len(hn_articles)}개 HN 기사 수집")
        except Exception as e:
            self._update_progress(collection_id, "collecting_hn", f"HN 오류: {str(e)[:50]}")
            print(f"HN collection error: {e}")

        return articles

    def _collect_viral(self, collection_id: int) -> list:
        """Collect viral content from various sources."""
        articles = []

        self._update_progress(collection_id, "collecting_viral", "바이럴 콘텐츠 수집 중...")
        try:
            viral_content = self.viral_aggregator.collect_all()
            # Convert viral content to article-like format
            for item in viral_content:
                article = RSSArticle(
                    title=item.title,
                    url=item.url,
                    source=item.source,
                    category="viral",
                    published=item.created_at,
                    summary=item.description or "",
                    score=item.score or 0,
                )
                articles.append(article)
            self._update_progress(collection_id, "collecting_viral", f"{len(viral_content)}개 바이럴 콘텐츠 수집")
        except Exception as e:
            self._update_progress(collection_id, "collecting_viral", f"바이럴 오류: {str(e)[:50]}")
            print(f"Viral collection error: {e}")

        return articles

    def _process_articles(self, articles: list, limit: int, collection_id: int) -> list:
        """Process articles through dedup, scoring, enrichment, and summarization."""
        if not articles:
            return []

        # Deduplication
        self._update_progress(collection_id, "deduplicating", f"{len(articles)}개 기사 중복 제거 중...")
        articles = self.deduplicator.deduplicate(articles)
        self._update_progress(collection_id, "deduplicating", f"중복 제거 후 {len(articles)}개")

        # Scoring and selection
        self._update_progress(collection_id, "scoring", "기사 점수 계산 중...")
        articles = self.scorer.get_all_articles_with_research_limit(articles, research_limit=5)
        self._update_progress(collection_id, "scoring", f"상위 {len(articles)}개 선별 완료")

        # Limit
        articles = articles[:limit]

        # Enrich arXiv papers
        self._update_progress(collection_id, "enriching", "arXiv 논문 정보 보강 중...")
        try:
            articles = self.arxiv_enricher.enrich_articles(articles)
            self._update_progress(collection_id, "enriching", "논문 정보 보강 완료")
        except Exception as e:
            self._update_progress(collection_id, "enriching", f"보강 오류: {str(e)[:50]}")
            print(f"Enrichment error: {e}")

        # Summarize (top articles only for speed)
        summarize_count = min(20, len(articles))
        self._update_progress(collection_id, "summarizing", f"AI 요약 생성 중 (0/{summarize_count})...")
        try:
            # Use a callback to update progress during summarization
            articles = self.summarizer.summarize_all(articles, limit=summarize_count)
            self._update_progress(collection_id, "summarizing", f"{summarize_count}개 기사 요약 완료")
        except Exception as e:
            self._update_progress(collection_id, "summarizing", f"요약 오류: {str(e)[:50]}")
            print(f"Summarization error: {e}")

        return articles

    def _store_articles(self, articles: list, collection_id: int) -> int:
        """Store articles in database, avoiding duplicates."""
        stored = 0

        for rss_article in articles:
            # Check if URL already exists
            existing = self.db.query(Article).filter(Article.url == rss_article.url).first()
            if existing:
                continue

            # Create new article
            article = Article(
                title=rss_article.title,
                url=rss_article.url,
                source=rss_article.source,
                category=rss_article.category,
                summary=rss_article.summary,
                ai_summary=getattr(rss_article, "ai_summary", None),
                score=rss_article.score,
                viral_score=getattr(rss_article, "viral_score", None),
                published_at=rss_article.published if rss_article.published else None,
                collection_id=collection_id,
            )
            self.db.add(article)
            stored += 1

        self.db.commit()
        return stored

    def get_collection_status(self, collection_id: int) -> Optional[Collection]:
        """Get collection status by ID."""
        return self.db.query(Collection).filter(Collection.id == collection_id).first()

    def get_recent_collections(self, limit: int = 10) -> List[Collection]:
        """Get recent collections."""
        return (
            self.db.query(Collection)
            .order_by(Collection.collected_at.desc())
            .limit(limit)
            .all()
        )

    def get_today_stats(self) -> dict:
        """Get statistics for today's collections."""
        today = datetime.utcnow().date()

        total_articles = (
            self.db.query(Article)
            .filter(Article.collected_at >= datetime(today.year, today.month, today.day))
            .count()
        )

        viral_articles = (
            self.db.query(Article)
            .filter(
                Article.collected_at >= datetime(today.year, today.month, today.day),
                Article.category == "viral",
            )
            .count()
        )

        drafts_generated = (
            self.db.query(Article)
            .filter(
                Article.collected_at >= datetime(today.year, today.month, today.day),
                Article.linkedin_status != "none",
            )
            .count()
        )

        return {
            "total_articles": total_articles,
            "viral_articles": viral_articles,
            "drafts_generated": drafts_generated,
        }
