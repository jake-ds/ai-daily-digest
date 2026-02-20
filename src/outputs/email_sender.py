"""이메일 발송 모듈 - 일일 요약 이메일"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class DigestItem:
    """다이제스트 항목"""
    title: str
    url: Optional[str]
    source_type: str
    summary: str
    tags: list[str]
    relevance_score: float = 0.0


class EmailSender:
    """SMTP를 통한 이메일 발송"""

    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        recipient: Optional[str] = None
    ):
        self.smtp_server = smtp_server or os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", smtp_port))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.recipient = recipient or os.getenv("MY_EMAIL")

        if not all([self.smtp_user, self.smtp_password]):
            raise ValueError("SMTP 설정이 필요합니다. (SMTP_USER, SMTP_PASSWORD)")

    def _generate_html(self, items: list[DigestItem], date: datetime) -> str:
        """HTML 형식 다이제스트 생성"""
        date_str = date.strftime("%Y년 %m월 %d일")

        # CSS 스타일
        styles = """
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }
            h1 {
                color: #2563eb;
                border-bottom: 2px solid #e5e7eb;
                padding-bottom: 10px;
            }
            h2 {
                color: #1f2937;
                margin-top: 30px;
            }
            .item {
                background: #f9fafb;
                border-left: 4px solid #3b82f6;
                padding: 15px;
                margin: 15px 0;
                border-radius: 0 8px 8px 0;
            }
            .item-title {
                font-weight: 600;
                font-size: 16px;
                color: #1f2937;
            }
            .item-title a {
                color: #2563eb;
                text-decoration: none;
            }
            .item-title a:hover {
                text-decoration: underline;
            }
            .item-meta {
                font-size: 12px;
                color: #6b7280;
                margin: 5px 0;
            }
            .item-summary {
                font-size: 14px;
                color: #4b5563;
                margin-top: 8px;
            }
            .tags {
                margin-top: 8px;
            }
            .tag {
                display: inline-block;
                background: #dbeafe;
                color: #1e40af;
                font-size: 11px;
                padding: 2px 8px;
                border-radius: 12px;
                margin-right: 5px;
            }
            .high-relevance {
                border-left-color: #10b981;
            }
            .stats {
                background: #f3f4f6;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
            }
            .footer {
                font-size: 12px;
                color: #9ca3af;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #e5e7eb;
            }
        </style>
        """

        # 통계
        by_type = {}
        high_relevance = 0
        for item in items:
            by_type[item.source_type] = by_type.get(item.source_type, 0) + 1
            if item.relevance_score >= 0.7:
                high_relevance += 1

        stats_html = f"""
        <div class="stats">
            <strong>오늘의 통계</strong><br>
            총 {len(items)}개 콘텐츠 수집 | 높은 관련도: {high_relevance}개<br>
            {' | '.join([f'{t}: {c}개' for t, c in by_type.items()])}
        </div>
        """

        # 아이템 목록
        items_html = ""

        # 높은 관련도 우선 정렬
        sorted_items = sorted(items, key=lambda x: x.relevance_score, reverse=True)

        for item in sorted_items:
            relevance_class = "high-relevance" if item.relevance_score >= 0.7 else ""

            if item.url:
                title_html = f'<a href="{item.url}">{item.title}</a>'
            else:
                title_html = item.title

            tags_html = ""
            if item.tags:
                tags_html = '<div class="tags">' + ''.join(
                    [f'<span class="tag">{tag}</span>' for tag in item.tags[:5]]
                ) + '</div>'

            items_html += f"""
            <div class="item {relevance_class}">
                <div class="item-title">{title_html}</div>
                <div class="item-meta">{item.source_type} | 관련도: {int(item.relevance_score * 100)}%</div>
                <div class="item-summary">{item.summary}</div>
                {tags_html}
            </div>
            """

        # 최종 HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            {styles}
        </head>
        <body>
            <h1>AI Daily Digest</h1>
            <p>{date_str} 다이제스트입니다.</p>

            {stats_html}

            <h2>오늘의 콘텐츠</h2>
            {items_html}

            <div class="footer">
                이 이메일은 AI Daily Digest 시스템에서 자동으로 발송되었습니다.<br>
                Obsidian 볼트에서 전체 내용을 확인할 수 있습니다.
            </div>
        </body>
        </html>
        """

        return html

    def _generate_text(self, items: list[DigestItem], date: datetime) -> str:
        """텍스트 형식 다이제스트 생성"""
        date_str = date.strftime("%Y년 %m월 %d일")

        lines = [
            f"AI Daily Digest - {date_str}",
            "=" * 50,
            "",
            f"총 {len(items)}개 콘텐츠 수집",
            "",
        ]

        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item.title}")
            lines.append(f"   유형: {item.source_type} | 관련도: {int(item.relevance_score * 100)}%")
            if item.url:
                lines.append(f"   URL: {item.url}")
            lines.append(f"   {item.summary}")
            if item.tags:
                lines.append(f"   태그: {', '.join(item.tags[:5])}")
            lines.append("")

        lines.append("-" * 50)
        lines.append("AI Daily Digest 시스템에서 자동 발송")

        return "\n".join(lines)

    def send_digest(
        self,
        items: list[DigestItem],
        date: Optional[datetime] = None,
        recipient: Optional[str] = None
    ) -> bool:
        """다이제스트 이메일 발송"""
        if date is None:
            date = datetime.now()

        if recipient is None:
            recipient = self.recipient

        if not recipient:
            print("[Email] 수신자 이메일이 설정되지 않았습니다.")
            return False

        date_str = date.strftime("%Y-%m-%d")

        # 이메일 메시지 생성
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[AI Digest] {date_str} 일일 요약 ({len(items)}개 콘텐츠)"
        msg["From"] = self.smtp_user
        msg["To"] = recipient

        # 텍스트 및 HTML 버전
        text_content = self._generate_text(items, date)
        html_content = self._generate_html(items, date)

        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, recipient, msg.as_string())

            print(f"[Email] 다이제스트 발송 완료: {recipient}")
            return True

        except Exception as e:
            print(f"[Email] 발송 실패: {e}")
            return False

    def send_notification(
        self,
        subject: str,
        content: str,
        recipient: Optional[str] = None
    ) -> bool:
        """간단한 알림 이메일 발송"""
        if recipient is None:
            recipient = self.recipient

        if not recipient:
            return False

        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = recipient

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, recipient, msg.as_string())

            return True

        except Exception as e:
            print(f"[Email] 알림 발송 실패: {e}")
            return False


if __name__ == "__main__":
    # 테스트
    try:
        sender = EmailSender()

        test_items = [
            DigestItem(
                title="OpenAI GPT-5 발표",
                url="https://example.com/gpt5",
                source_type="article",
                summary="OpenAI가 새로운 GPT-5 모델을 발표했습니다. 멀티모달 기능이 크게 향상되었습니다.",
                tags=["AI", "OpenAI", "GPT"],
                relevance_score=0.85
            ),
            DigestItem(
                title="Claude 3.5 Sonnet 업데이트",
                url="https://example.com/claude",
                source_type="article",
                summary="Anthropic이 Claude 3.5 Sonnet의 새로운 버전을 공개했습니다.",
                tags=["AI", "Anthropic", "Claude"],
                relevance_score=0.90
            ),
        ]

        print("테스트 이메일 발송 중...")
        # sender.send_digest(test_items)  # 실제 발송 시 주석 해제

    except ValueError as e:
        print(f"설정 오류: {e}")
