#!/usr/bin/env python3
"""AI Daily Digest - 메인 실행 파일"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# .env 파일 로드
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.collectors import RSSCollector, HackerNewsCollector, ArxivEnricher, YouTubeCollector
from src.processors import Deduplicator, Scorer, Summarizer
from src.outputs import (
    MarkdownOutput,
    NotionOutput,
    NotionArticlesDB,
    setup_notion_database,
    setup_articles_database
)


def main(
    hours: int = 48,
    top_n: int = 20,
    skip_summary: bool = False,
    clear_history: bool = False,
    notion: bool = False,
    notion_only: bool = False,
    articles_db: bool = False
):
    """메인 실행 함수

    Args:
        hours: 수집할 기간 (시간)
        top_n: 상위 N개 기사 처리
        skip_summary: LLM 요약 건너뛰기
        clear_history: 히스토리 초기화
        notion: 노션에도 저장
        notion_only: 노션에만 저장 (마크다운 건너뛰기)
        articles_db: 개별 기사 페이지도 생성 (LinkedIn 선택용)
    """
    print("=" * 50)
    print("AI Daily Digest 시작")
    print("=" * 50 + "\n")

    # 작업 디렉토리 설정
    os.chdir(Path(__file__).parent)

    # 1. 수집
    print("[1/5] 기사 수집 중...\n")

    rss_collector = RSSCollector()
    hn_collector = HackerNewsCollector()

    articles = []
    articles.extend(rss_collector.collect_all(hours=hours))
    articles.extend(hn_collector.collect(limit=30))

    # YouTube 수집
    if os.getenv("YOUTUBE_API_KEY"):
        yt_collector = YouTubeCollector()
        articles.extend(yt_collector.collect(hours=hours))
    else:
        print("YOUTUBE_API_KEY 없음, YouTube 수집 건너뜀")

    if not articles:
        print("수집된 기사가 없습니다.")
        return

    # 2. 중복 제거
    print("\n[2/5] 중복 제거 중...\n")

    dedup = Deduplicator()
    if clear_history:
        dedup.clear_history()
    articles = dedup.deduplicate(articles)

    # 3. 점수 부여 및 선택 (research만 top 3 제한, 나머지는 전부)
    print("\n[3/5] 점수 부여 및 선택 중...\n")

    scorer = Scorer()
    articles = scorer.get_all_articles_with_research_limit(articles, research_limit=3)

    # 4. arXiv 논문 기관 정보 보강
    print("\n[4/5] arXiv 기관 정보 조회 중...\n")

    arxiv_enricher = ArxivEnricher()
    research_count = len([a for a in articles if a.category == "research"])
    articles = arxiv_enricher.enrich_articles(articles, limit=research_count)

    # 5. 요약
    print("\n[5/5] 요약 생성 중...\n")

    summarizer = Summarizer()

    if not skip_summary and os.getenv("ANTHROPIC_API_KEY"):
        articles = summarizer.summarize_all(articles, limit=len(articles))
    else:
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY가 설정되지 않아 요약을 건너뜁니다.")

    # 출력
    print("\n출력 생성 중...\n")

    results = {}

    # 마크다운 출력
    if not notion_only:
        md_output = MarkdownOutput()
        filepath = md_output.save(articles)
        results["markdown"] = filepath

    # 노션 출력
    if notion or notion_only:
        notion_output = NotionOutput()

        if notion_output.is_available():
            # 오늘 이미 생성됐는지 확인
            if notion_output.check_today_exists():
                print("오늘 다이제스트가 이미 노션에 존재합니다.")
            else:
                page_url = notion_output.create_page(articles)
                if page_url:
                    results["notion"] = page_url
        else:
            print("\n노션 API가 설정되지 않았습니다.")
            print("설정 방법을 보려면: python main.py --notion-setup\n")

    # 개별 기사 DB 출력 (LinkedIn 선택용)
    if articles_db:
        articles_output = NotionArticlesDB()

        if articles_output.is_available():
            print("\n개별 기사 페이지 생성 중...")
            page_ids = articles_output.create_article_pages(articles)
            if page_ids:
                results["articles_db"] = f"{len(page_ids)}개 기사 페이지 생성"
        else:
            print("\n노션 Articles DB가 설정되지 않았습니다.")
            print("설정 방법을 보려면: python main.py --articles-setup\n")

    print("\n" + "=" * 50)
    print("완료!")
    if "markdown" in results:
        print(f"마크다운: {results['markdown']}")
    if "notion" in results:
        print(f"노션: {results['notion']}")
    if "articles_db" in results:
        print(f"Articles DB: {results['articles_db']}")
    print("=" * 50)

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Daily Digest")
    parser.add_argument("--hours", type=int, default=48, help="수집 기간 (시간)")
    parser.add_argument("--top", type=int, default=20, help="상위 N개 기사")
    parser.add_argument("--skip-summary", action="store_true", help="요약 건너뛰기")
    parser.add_argument("--clear-history", action="store_true", help="히스토리 초기화")
    parser.add_argument("--notion", action="store_true", help="노션에도 저장")
    parser.add_argument("--notion-only", action="store_true", help="노션에만 저장")
    parser.add_argument("--notion-setup", action="store_true", help="노션 설정 가이드 출력")
    parser.add_argument("--articles-db", action="store_true", help="개별 기사 페이지도 생성 (LinkedIn 선택용)")
    parser.add_argument("--articles-setup", action="store_true", help="Articles DB 설정 가이드 출력")

    args = parser.parse_args()

    # 설정 가이드
    if args.notion_setup:
        setup_notion_database()
    elif args.articles_setup:
        setup_articles_database()
    else:
        main(
            hours=args.hours,
            top_n=args.top,
            skip_summary=args.skip_summary,
            clear_history=args.clear_history,
            notion=args.notion,
            notion_only=args.notion_only,
            articles_db=args.articles_db
        )
