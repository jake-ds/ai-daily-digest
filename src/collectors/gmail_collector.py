"""Gmail API 수집기 - 뉴스레터 및 공유 콘텐츠 수집"""

import os
import base64
import re
from pathlib import Path
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


@dataclass
class EmailContent:
    """수집된 이메일 데이터"""
    message_id: str
    subject: str
    sender: str
    date: datetime
    body_text: str
    body_html: str
    urls: list[str] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)


class GmailCollector:
    """Gmail API를 통해 이메일 수집"""

    def __init__(
        self,
        credentials_path: str = "data/gmail_credentials.json",
        token_path: str = "data/gmail_token.json"
    ):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.service = self._authenticate()

    def _authenticate(self):
        """OAuth2 인증 및 Gmail 서비스 생성"""
        creds = None

        # 기존 토큰 로드
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        # 토큰이 없거나 만료된 경우
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials 파일이 없습니다: {self.credentials_path}\n"
                        "Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 생성하고 "
                        "credentials.json을 다운로드하세요."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            # 토큰 저장
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    def _parse_email_date(self, headers: list[dict]) -> Optional[datetime]:
        """이메일 헤더에서 날짜 파싱"""
        for header in headers:
            if header["name"].lower() == "date":
                try:
                    return parsedate_to_datetime(header["value"])
                except Exception:
                    pass
        return None

    def _get_header_value(self, headers: list[dict], name: str) -> str:
        """헤더에서 특정 값 추출"""
        for header in headers:
            if header["name"].lower() == name.lower():
                return header["value"]
        return ""

    def _decode_body(self, data: str) -> str:
        """Base64URL 디코딩"""
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _extract_body(self, payload: dict) -> tuple[str, str]:
        """이메일 본문 추출 (text, html)"""
        text_body = ""
        html_body = ""

        def process_part(part: dict):
            nonlocal text_body, html_body
            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            data = body.get("data", "")

            if mime_type == "text/plain" and not text_body:
                text_body = self._decode_body(data)
            elif mime_type == "text/html" and not html_body:
                html_body = self._decode_body(data)

            # 중첩된 파트 처리
            for sub_part in part.get("parts", []):
                process_part(sub_part)

        process_part(payload)
        return text_body, html_body

    def _extract_urls(self, text: str, html: str) -> list[str]:
        """본문에서 URL 추출"""
        urls = set()

        # URL 패턴
        url_pattern = r'https?://[^\s<>"\')\]}>]+'

        for content in [text, html]:
            if content:
                found = re.findall(url_pattern, content)
                urls.update(found)

        # 정리: 트래킹 파라미터 제거, 중복 제거
        cleaned_urls = []
        for url in urls:
            # 끝에 있는 불필요한 문자 제거
            url = url.rstrip(".,;:!?")
            if url and len(url) > 10:
                cleaned_urls.append(url)

        return list(set(cleaned_urls))

    def _extract_attachments(self, payload: dict, message_id: str) -> list[dict]:
        """첨부파일 정보 추출"""
        attachments = []

        def process_part(part: dict):
            filename = part.get("filename", "")
            body = part.get("body", {})
            attachment_id = body.get("attachmentId")
            mime_type = part.get("mimeType", "")

            if filename and attachment_id:
                attachments.append({
                    "filename": filename,
                    "mime_type": mime_type,
                    "attachment_id": attachment_id,
                    "size": body.get("size", 0)
                })

            for sub_part in part.get("parts", []):
                process_part(sub_part)

        process_part(payload)
        return attachments

    def get_attachment_data(self, message_id: str, attachment_id: str) -> bytes:
        """첨부파일 데이터 다운로드"""
        attachment = self.service.users().messages().attachments().get(
            userId="me",
            messageId=message_id,
            id=attachment_id
        ).execute()

        data = attachment.get("data", "")
        return base64.urlsafe_b64decode(data)

    def fetch_unread_emails(self, hours: int = 24, max_results: int = 50) -> list[EmailContent]:
        """읽지 않은 이메일 조회"""
        emails = []

        # 시간 기준 쿼리
        after_date = datetime.now(timezone.utc) - timedelta(hours=hours)
        after_timestamp = int(after_date.timestamp())
        query = f"is:unread after:{after_timestamp}"

        try:
            results = self.service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            print(f"[Gmail] {len(messages)}개의 읽지 않은 이메일 발견")

            for msg in messages:
                email = self._fetch_email_detail(msg["id"])
                if email:
                    emails.append(email)

        except Exception as e:
            print(f"[Gmail] 이메일 조회 실패: {e}")

        return emails

    def _fetch_email_detail(self, message_id: str) -> Optional[EmailContent]:
        """개별 이메일 상세 조회"""
        try:
            msg = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()

            payload = msg.get("payload", {})
            headers = payload.get("headers", [])

            subject = self._get_header_value(headers, "Subject")
            sender = self._get_header_value(headers, "From")
            date = self._parse_email_date(headers)

            text_body, html_body = self._extract_body(payload)
            urls = self._extract_urls(text_body, html_body)
            attachments = self._extract_attachments(payload, message_id)

            return EmailContent(
                message_id=message_id,
                subject=subject,
                sender=sender,
                date=date or datetime.now(timezone.utc),
                body_text=text_body,
                body_html=html_body,
                urls=urls,
                attachments=attachments,
                labels=msg.get("labelIds", [])
            )

        except Exception as e:
            print(f"[Gmail] 이메일 상세 조회 실패 ({message_id}): {e}")
            return None

    def mark_as_read(self, message_id: str) -> bool:
        """이메일을 읽음으로 표시"""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]}
            ).execute()
            return True
        except Exception as e:
            print(f"[Gmail] 읽음 표시 실패 ({message_id}): {e}")
            return False

    def add_label(self, message_id: str, label_id: str) -> bool:
        """이메일에 라벨 추가"""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]}
            ).execute()
            return True
        except Exception as e:
            print(f"[Gmail] 라벨 추가 실패 ({message_id}): {e}")
            return False


if __name__ == "__main__":
    collector = GmailCollector()
    emails = collector.fetch_unread_emails(hours=24)

    for email in emails:
        print(f"\n제목: {email.subject}")
        print(f"발신자: {email.sender}")
        print(f"URL 수: {len(email.urls)}")
        print(f"첨부파일 수: {len(email.attachments)}")
