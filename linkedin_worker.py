#!/usr/bin/env python3
"""LinkedIn 초안 생성 워커

Notion에서 'Requested' 상태인 기사를 찾아 LinkedIn 초안을 생성합니다.

사용법:
    python linkedin_worker.py          # 한 번 실행
    python linkedin_worker.py --watch  # 5분마다 체크
"""

import os
import sys
import time
import argparse
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# .env 파일 로드
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from src.outputs.notion_output import NotionArticlesDB
from src.processors.linkedin_generator import LinkedInGenerator


def poll_and_generate(verbose: bool = True) -> int:
    """Notion에서 'Requested' 상태인 기사를 찾아 초안 생성

    Returns:
        처리된 기사 수
    """
    # 초기화
    notion_db = NotionArticlesDB()
    generator = LinkedInGenerator()

    if not notion_db.is_available():
        print("오류: Notion Articles DB가 설정되지 않았습니다.")
        print("NOTION_API_KEY와 NOTION_ARTICLES_DATABASE_ID 환경변수를 확인하세요.")
        return 0

    if not generator.is_available():
        print("오류: Anthropic API 키가 설정되지 않았습니다.")
        print("ANTHROPIC_API_KEY 환경변수를 확인하세요.")
        return 0

    # 1. LinkedIn Status = "Requested"인 기사 쿼리
    if verbose:
        print("Notion에서 요청된 기사 조회 중...")

    pages = notion_db.query_requested_articles()

    if not pages:
        if verbose:
            print("처리할 기사가 없습니다.")
        return 0

    if verbose:
        print(f"처리 대기 중인 기사: {len(pages)}개\n")

    # 2. 각 기사에 대해 초안 생성
    processed = 0

    for i, page in enumerate(pages, 1):
        article = notion_db.extract_article_data(page)

        if verbose:
            print(f"[{i}/{len(pages)}] {article['title'][:50]}...")
            print(f"  카테고리: {article['category']}, 출처: {article['source']}")

        # 시나리오 판별 및 초안 생성
        draft, scenario = generator.generate_draft(article)

        if verbose:
            print(f"  시나리오: {scenario}")
            print(f"  초안 길이: {len(draft)}자")

        # 3. Notion 페이지 업데이트
        success = notion_db.update_linkedin_draft(
            page_id=article["page_id"],
            draft=draft,
            scenario=scenario
        )

        if success:
            processed += 1
            if verbose:
                print(f"  완료!\n")
        else:
            if verbose:
                print(f"  업데이트 실패\n")

    if verbose:
        print(f"\n총 {processed}/{len(pages)}개 기사 처리 완료")

    return processed


def watch_mode(interval: int = 300):
    """주기적으로 Notion을 체크하고 초안 생성

    Args:
        interval: 체크 간격 (초), 기본 5분
    """
    print(f"Watch 모드 시작 (체크 간격: {interval}초)")
    print("종료하려면 Ctrl+C를 누르세요.\n")

    try:
        while True:
            processed = poll_and_generate(verbose=True)

            if processed > 0:
                print(f"\n{processed}개 처리됨. 다음 체크까지 대기 중...")
            else:
                print(f"대기 중... (다음 체크: {interval}초 후)")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nWatch 모드 종료")


def show_status():
    """현재 상태 표시"""
    notion_db = NotionArticlesDB()

    if not notion_db.is_available():
        print("Notion Articles DB가 설정되지 않았습니다.")
        return

    # 대기 중인 기사 조회
    pages = notion_db.query_requested_articles()

    print(f"\n현재 대기 중인 기사: {len(pages)}개")

    if pages:
        print("\n대기 목록:")
        for i, page in enumerate(pages, 1):
            article = notion_db.extract_article_data(page)
            print(f"  {i}. {article['title'][:60]}...")
            print(f"     카테고리: {article['category']}, 출처: {article['source']}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn 초안 생성 워커",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python linkedin_worker.py              # 한 번 실행
  python linkedin_worker.py --watch      # 5분마다 자동 체크
  python linkedin_worker.py --watch -i 60  # 1분마다 자동 체크
  python linkedin_worker.py --status     # 대기 중인 기사 목록
"""
    )

    parser.add_argument(
        "--watch", "-w",
        action="store_true",
        help="주기적으로 체크하는 watch 모드"
    )
    parser.add_argument(
        "--interval", "-i",
        type=int,
        default=300,
        help="watch 모드 체크 간격 (초), 기본 300초(5분)"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="현재 대기 중인 기사 목록 표시"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="최소한의 출력만"
    )

    args = parser.parse_args()

    print("=" * 50)
    print("LinkedIn 초안 생성 워커")
    print("=" * 50 + "\n")

    if args.status:
        show_status()
    elif args.watch:
        watch_mode(interval=args.interval)
    else:
        poll_and_generate(verbose=not args.quiet)


if __name__ == "__main__":
    main()
