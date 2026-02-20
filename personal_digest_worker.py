#!/usr/bin/env python3
"""
Personal AI Digest Worker
- 매시간: Gmail 수집 + 바이럴 수집 → 처리 → Obsidian 저장
- 매일 5시: 일일 요약 이메일 발송
"""

import os
import sys
import argparse
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import schedule
import anthropic
from dotenv import load_dotenv

load_dotenv()

# 모듈 임포트
from src.collectors.gmail_collector import GmailCollector, EmailContent
from src.collectors.youtube_transcript import YouTubeTranscriptExtractor
from src.collectors.viral_aggregator import ViralAggregator
from src.processors.content_parser import ContentParser, ContentType, ParsedContent
from src.processors.image_analyzer import ImageAnalyzer
from src.processors.personalization import ObsidianPersonalizer, PersonalizedAnalysis
from src.processors.viral_detector import ViralContent, ViralDigest
from src.outputs.obsidian_output import ObsidianOutput, DigestNote
from src.outputs.email_sender import EmailSender, DigestItem
from src.outputs.notion_output import NotionOutput, NotionArticlesDB


class PersonalDigestWorker:
    """개인 다이제스트 워커"""

    def __init__(self):
        # 필수 설정 확인
        self.vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
        if not self.vault_path:
            raise ValueError("OBSIDIAN_VAULT_PATH 환경변수를 설정하세요.")

        # 컴포넌트 초기화
        self.gmail: Optional[GmailCollector] = None
        self.content_parser = ContentParser()
        self.youtube = YouTubeTranscriptExtractor()
        self.image_analyzer: Optional[ImageAnalyzer] = None
        self.personalizer: Optional[ObsidianPersonalizer] = None
        self.obsidian_output = ObsidianOutput(self.vault_path)
        self.email_sender: Optional[EmailSender] = None
        self.viral_aggregator: Optional[ViralAggregator] = None
        self.notion_output: Optional[NotionOutput] = None
        self.notion_articles: Optional[NotionArticlesDB] = None

        # Claude 클라이언트
        api_key = os.getenv("ANTHROPIC_API_KEY")
        self.claude = anthropic.Anthropic(api_key=api_key) if api_key else None

        # 오늘 처리된 아이템 (일일 요약용)
        self.today_items: list[DigestItem] = []
        self.today_notes: list[DigestNote] = []
        self.today_viral: list[ViralContent] = []
        self.today_viral_digest: Optional[ViralDigest] = None
        self.last_daily_reset = datetime.now().date()

        # 컴포넌트 초기화 시도
        self._init_components()

    def _init_components(self):
        """컴포넌트 초기화 (실패해도 계속 진행)"""
        # Gmail
        try:
            self.gmail = GmailCollector()
            print("[Worker] Gmail 연결 완료")
        except Exception as e:
            print(f"[Worker] Gmail 연결 실패 (나중에 재시도): {e}")

        # Image Analyzer
        try:
            self.image_analyzer = ImageAnalyzer()
            print("[Worker] 이미지 분석기 준비 완료")
        except Exception as e:
            print(f"[Worker] 이미지 분석기 초기화 실패: {e}")

        # Personalizer
        try:
            self.personalizer = ObsidianPersonalizer(self.vault_path)
            print("[Worker] Obsidian 개인화 모듈 준비 완료")
        except Exception as e:
            print(f"[Worker] 개인화 모듈 초기화 실패: {e}")

        # Email Sender
        try:
            self.email_sender = EmailSender()
            print("[Worker] 이메일 발송 모듈 준비 완료")
        except Exception as e:
            print(f"[Worker] 이메일 발송 모듈 초기화 실패: {e}")

        # Viral Aggregator
        try:
            self.viral_aggregator = ViralAggregator()
            print("[Worker] 바이럴 수집기 준비 완료")
        except Exception as e:
            print(f"[Worker] 바이럴 수집기 초기화 실패: {e}")

        # Notion Output
        try:
            self.notion_output = NotionOutput()
            if self.notion_output.is_available():
                print("[Worker] Notion 다이제스트 DB 준비 완료")
            else:
                print("[Worker] Notion 다이제스트 DB 미설정 (선택적)")
                self.notion_output = None
        except Exception as e:
            print(f"[Worker] Notion 다이제스트 초기화 실패: {e}")

        # Notion Articles DB
        try:
            self.notion_articles = NotionArticlesDB()
            if self.notion_articles.is_available():
                print("[Worker] Notion Articles DB 준비 완료")
            else:
                print("[Worker] Notion Articles DB 미설정 (선택적)")
                self.notion_articles = None
        except Exception as e:
            print(f"[Worker] Notion Articles 초기화 실패: {e}")

    def _reset_daily_if_needed(self):
        """날짜가 바뀌면 일일 데이터 리셋"""
        today = datetime.now().date()
        if today != self.last_daily_reset:
            self.today_items = []
            self.today_notes = []
            self.today_viral = []
            self.today_viral_digest = None
            self.last_daily_reset = today
            print(f"[Worker] 새로운 날 시작: {today}")

    def _summarize_content(self, title: str, content: str) -> str:
        """콘텐츠 요약 (Claude 사용)"""
        if not self.claude or not content:
            return ""

        try:
            prompt = f"""다음 콘텐츠를 2-3문장으로 핵심만 요약해주세요.

제목: {title}
내용:
{content[:5000]}

요약:"""

            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        except Exception as e:
            print(f"[Worker] 요약 실패: {e}")
            return ""

    def process_youtube(self, parsed: ParsedContent) -> tuple[str, str]:
        """YouTube 콘텐츠 처리 → (content, summary)"""
        video_id = parsed.metadata.get("video_id")
        if not video_id:
            return "", ""

        video = self.youtube.get_video_info(video_id)
        if not video or not video.transcript:
            return "", ""

        transcript = video.transcript

        # 요약 생성
        summary = self._summarize_content(
            f"YouTube Video ({video_id})",
            transcript
        )

        # 포맷팅
        content = f"""## 트랜스크립트

{transcript[:10000]}
"""
        if len(transcript) > 10000:
            content += "\n\n(트랜스크립트가 너무 길어 일부만 표시합니다)"

        return content, summary

    def process_image(self, url: str) -> tuple[str, str]:
        """이미지 콘텐츠 처리 → (content, summary)"""
        if not self.image_analyzer:
            return "", ""

        try:
            analysis = self.image_analyzer.analyze_image(url)

            content = f"""## 이미지 분석

**설명**: {analysis.description}

**추출된 텍스트**: {analysis.text_content or '없음'}

**태그**: {', '.join(analysis.tags) if analysis.tags else '없음'}
"""
            summary = analysis.summary or analysis.description[:200]
            return content, summary

        except Exception as e:
            print(f"[Worker] 이미지 분석 실패: {e}")
            return "", ""

    def process_article(self, url: str) -> tuple[str, str]:
        """웹 아티클 처리 → (content, summary)"""
        # 기본적으로 URL만 저장
        content = f"URL: {url}"
        summary = "웹 아티클 링크가 저장되었습니다."
        return content, summary

    def process_email(self, email: EmailContent) -> list[DigestNote]:
        """이메일 처리 → 노트 목록 생성"""
        notes = []

        # 이메일 본문에서 콘텐츠 추출
        parsed_contents = self.content_parser.parse_email_body(
            email.body_text,
            email.body_html
        )

        print(f"  [Email] '{email.subject}' - {len(parsed_contents)}개 URL 발견")

        # 공유 이메일인 경우 (iPhone 단축어 등)
        is_shared = "[Shared]" in email.subject or "공유" in email.subject

        for parsed in parsed_contents:
            try:
                content = ""
                summary = ""
                source_type = parsed.content_type.value

                # 콘텐츠 타입별 처리
                if parsed.content_type == ContentType.YOUTUBE:
                    content, summary = self.process_youtube(parsed)
                    title = f"YouTube: {parsed.url}"

                elif parsed.content_type == ContentType.IMAGE:
                    content, summary = self.process_image(parsed.url)
                    title = f"Image: {parsed.url.split('/')[-1]}"

                else:
                    content, summary = self.process_article(parsed.url)
                    title = email.subject if is_shared else parsed.url

                # 개인화 분석
                analysis: Optional[PersonalizedAnalysis] = None
                if self.personalizer and (content or summary):
                    analysis = self.personalizer.analyze_content(
                        title,
                        f"{summary}\n{content[:2000]}",
                        source_type
                    )

                # 노트 생성
                note = DigestNote(
                    title=title[:100],
                    content=content or f"URL: {parsed.url}",
                    source_url=parsed.url,
                    source_type=source_type,
                    tags=analysis.suggested_tags if analysis else [],
                    summary=summary,
                    personalized_note=analysis.personalized_summary if analysis else None,
                    related_interests=analysis.related_interests if analysis else []
                )
                notes.append(note)

                # 일일 요약용 아이템
                self.today_items.append(DigestItem(
                    title=note.title,
                    url=parsed.url,
                    source_type=source_type,
                    summary=summary or "요약 없음",
                    tags=note.tags,
                    relevance_score=analysis.relevance_score if analysis else 0.5
                ))

            except Exception as e:
                print(f"  [Email] 콘텐츠 처리 실패 ({parsed.url}): {e}")
                continue

        return notes

    def collect_and_process(self, hours: int = 24):
        """Gmail 수집 및 처리"""
        self._reset_daily_if_needed()

        if not self.gmail:
            try:
                self.gmail = GmailCollector()
            except Exception as e:
                print(f"[Worker] Gmail 연결 실패: {e}")
                return

        print(f"\n{'='*50}")
        print(f"[Worker] Gmail 수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}")

        # 이메일 수집
        emails = self.gmail.fetch_unread_emails(hours=hours)

        if not emails:
            print("[Worker] 새 이메일이 없습니다.")
            return

        processed_count = 0

        for email in emails:
            try:
                # 이메일 처리
                notes = self.process_email(email)

                # Obsidian에 저장
                for note in notes:
                    saved_path = self.obsidian_output.save_note(note)
                    self.today_notes.append(note)
                    processed_count += 1

                # 이메일 읽음 표시
                self.gmail.mark_as_read(email.message_id)

            except Exception as e:
                print(f"[Worker] 이메일 처리 실패 ({email.subject}): {e}")
                continue

        print(f"\n[Worker] 처리 완료: {processed_count}개 노트 저장")

    def collect_viral(self):
        """글로벌 바이럴 콘텐츠 수집"""
        self._reset_daily_if_needed()

        if not self.viral_aggregator:
            print("[Worker] 바이럴 수집기가 준비되지 않았습니다.")
            return

        print(f"\n{'='*50}")
        print(f"[Worker] 바이럴 수집 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}")

        try:
            # 바이럴 다이제스트 생성
            digest = self.viral_aggregator.create_digest(
                top_n=30,
                include_twitter=False  # Twitter는 API 비용으로 인해 기본 비활성화
            )

            print(f"[Viral] 총 {digest.total_collected}개 수집")
            print(f"[Viral] 크로스 플랫폼: {len(digest.cross_platform_hits)}개")

            # 상위 바이럴 콘텐츠를 노트로 저장
            saved_count = 0

            for viral in digest.top_viral[:20]:
                try:
                    # 개인화 분석
                    analysis = None
                    if self.personalizer:
                        analysis = self.personalizer.analyze_content(
                            viral.title,
                            viral.description or "",
                            viral.category
                        )

                    # AI 요약 생성
                    summary = ""
                    if self.claude:
                        summary = self._summarize_viral(viral)

                    # 노트 생성
                    note = DigestNote(
                        title=f"[{viral.source.upper()}] {viral.title[:80]}",
                        content=self._format_viral_content(viral),
                        source_url=viral.url,
                        source_type=f"viral-{viral.source}",
                        tags=[viral.category, viral.source, "viral"] + viral.relevance_tags[:3],
                        summary=summary or viral.description,
                        personalized_note=analysis.personalized_summary if analysis else None,
                        related_interests=analysis.related_interests if analysis else []
                    )

                    # Obsidian에 저장
                    self.obsidian_output.save_note(note)
                    self.today_notes.append(note)
                    self.today_viral.append(viral)
                    saved_count += 1

                    # 일일 요약용 아이템 추가
                    self.today_items.append(DigestItem(
                        title=f"[{viral.source}] {viral.title[:60]}",
                        url=viral.url,
                        source_type=f"viral-{viral.category}",
                        summary=summary or viral.description or "바이럴 콘텐츠",
                        tags=[viral.category, viral.source],
                        relevance_score=analysis.relevance_score if analysis else viral.viral_score / 20
                    ))

                except Exception as e:
                    print(f"[Viral] 저장 실패: {e}")
                    continue

            # 크로스 플랫폼 바이럴 별도 표시
            for viral in digest.cross_platform_hits[:5]:
                if viral not in digest.top_viral[:20]:
                    try:
                        note = DigestNote(
                            title=f"[CROSS-PLATFORM] {viral.title[:70]}",
                            content=self._format_viral_content(viral, is_cross_platform=True),
                            source_url=viral.url,
                            source_type="viral-cross-platform",
                            tags=["viral", "cross-platform", viral.category] + viral.platforms_found,
                            summary=f"여러 플랫폼에서 동시 바이럴: {', '.join(viral.platforms_found)}"
                        )
                        self.obsidian_output.save_note(note)
                        saved_count += 1
                    except Exception:
                        continue

            print(f"[Viral] {saved_count}개 바이럴 노트 저장 완료 (Obsidian)")

            # 바이럴 다이제스트 저장 (일일 통합 저장에서 사용)
            self.today_viral_digest = digest

        except Exception as e:
            print(f"[Worker] 바이럴 수집 실패: {e}")

    def _summarize_viral(self, viral: ViralContent) -> str:
        """바이럴 콘텐츠 요약"""
        if not self.claude:
            return ""

        try:
            prompt = f"""다음 바이럴 콘텐츠를 한국어로 2-3문장으로 요약해주세요.
왜 글로벌에서 주목받고 있는지 설명해주세요.

제목: {viral.title}
출처: {viral.source}
카테고리: {viral.category}
점수: {viral.score}
설명: {viral.description or 'N/A'}

요약:"""

            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        except Exception:
            return ""

    def _format_viral_content(
        self,
        viral: ViralContent,
        is_cross_platform: bool = False
    ) -> str:
        """바이럴 콘텐츠 마크다운 포맷"""
        lines = []

        # 메타 정보
        lines.append(f"> **출처**: {viral.source.upper()}")
        lines.append(f"> **카테고리**: {viral.category}")
        lines.append(f"> **점수**: {viral.score:,} | **속도**: {viral.velocity:.1f}/hr")
        lines.append(f"> **바이럴 점수**: {viral.viral_score:.2f}")

        if is_cross_platform and viral.platforms_found:
            lines.append(f"> **발견 플랫폼**: {', '.join(viral.platforms_found)}")

        lines.append("")

        # 설명
        if viral.description:
            lines.append("## 요약")
            lines.append(viral.description)
            lines.append("")

        # AI 요약이 있으면 추가
        if viral.ai_summary:
            lines.append("## AI 분석")
            lines.append(viral.ai_summary)
            lines.append("")

        # 원본 링크
        lines.append("## 원본")
        lines.append(f"[{viral.title}]({viral.url})")

        return "\n".join(lines)

    def send_daily_digest(self):
        """일일 요약 이메일 발송 및 Notion 바이럴 페이지 생성"""
        print(f"\n{'='*50}")
        print(f"[Worker] 일일 다이제스트 생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*50}")

        # 통계 출력
        viral_count = self.today_viral_digest.total_collected if self.today_viral_digest else 0
        print(f"[Worker] 바이럴: {viral_count}개")

        # Obsidian에 일일 다이제스트 저장
        if self.today_notes:
            self.obsidian_output.save_daily_digest(self.today_notes)

        # Notion 바이럴 다이제스트 페이지 생성
        if self.notion_output and self.today_viral_digest:
            try:
                self.notion_output.create_viral_digest_page(
                    viral_digest=self.today_viral_digest,
                    top_n=15
                )
            except Exception as e:
                print(f"[Notion] 바이럴 다이제스트 생성 실패: {e}")

        # 이메일 발송
        if self.email_sender and self.today_items:
            self.email_sender.send_digest(self.today_items)
            print(f"[Worker] 이메일 발송 완료 ({len(self.today_items)}개 항목)")
        elif not self.today_items:
            print("[Worker] 오늘 수집된 콘텐츠가 없어 이메일 발송 생략")

        print(f"[Worker] 일일 다이제스트 완료")

    def run_once(self, hours: int = 24, include_viral: bool = True):
        """한 번만 실행 (Gmail + 바이럴)"""
        self.collect_and_process(hours)
        if include_viral:
            self.collect_viral()
        print("\n[Worker] 단일 실행 완료")

    def create_notion_digest(self):
        """Notion 바이럴 다이제스트 즉시 생성 (수집 없이)"""
        if not self.notion_output:
            print("[Worker] Notion이 설정되지 않았습니다.")
            return

        if not self.today_viral_digest:
            print("[Worker] 바이럴 데이터가 없습니다. 먼저 --viral-only를 실행하세요.")
            return

        self.notion_output.create_viral_digest_page(
            viral_digest=self.today_viral_digest,
            top_n=15
        )

    def run_scheduler(self):
        """스케줄러 실행"""
        print("\n[Worker] 스케줄러 시작")
        print("- 매시간: Gmail 수집 및 처리")
        print("- 매 3시간: 글로벌 바이럴 수집")
        print("- 매일 05:00: 일일 요약 이메일 발송")
        print("(RSS 뉴스는 main.py를 별도로 실행하세요)")
        print("-" * 50)

        # 스케줄 설정
        schedule.every().hour.do(self.collect_and_process, hours=2)
        schedule.every(3).hours.do(self.collect_viral)
        schedule.every().day.at("05:00").do(self.send_daily_digest)

        # 시작 시 즉시 한 번 실행
        self.collect_and_process(hours=24)
        self.collect_viral()

        # 스케줄 루프
        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Personal AI Digest Worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="한 번만 실행 후 종료"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=48,
        help="수집할 기간 (시간, 기본값: 48)"
    )
    parser.add_argument(
        "--send-digest",
        action="store_true",
        help="일일 다이제스트 즉시 발송"
    )
    parser.add_argument(
        "--viral-only",
        action="store_true",
        help="바이럴 콘텐츠만 수집"
    )
    parser.add_argument(
        "--no-viral",
        action="store_true",
        help="바이럴 수집 제외"
    )
    parser.add_argument(
        "--notion",
        action="store_true",
        help="Notion 바이럴 다이제스트 생성"
    )

    args = parser.parse_args()

    try:
        worker = PersonalDigestWorker()

        if args.viral_only:
            worker.collect_viral()
            if args.notion:
                worker.create_notion_digest()
        elif args.send_digest:
            if not args.no_viral:
                worker.collect_viral()
            worker.send_daily_digest()
        elif args.once:
            worker.run_once(
                hours=args.hours,
                include_viral=not args.no_viral
            )
        else:
            worker.run_scheduler()

    except KeyboardInterrupt:
        print("\n[Worker] 종료됨")
        sys.exit(0)
    except Exception as e:
        print(f"[Worker] 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
