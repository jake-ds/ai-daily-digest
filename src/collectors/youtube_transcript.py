"""YouTube 트랜스크립트 추출기"""

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)


@dataclass
class YouTubeVideo:
    """YouTube 비디오 정보"""
    video_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    transcript: Optional[str] = None
    language: Optional[str] = None
    duration_seconds: int = 0


class YouTubeTranscriptExtractor:
    """YouTube 자막 추출기"""

    # 선호 언어 순서
    PREFERRED_LANGUAGES = ["ko", "en", "ja", "zh-Hans", "zh-Hant"]

    # YouTube URL 패턴
    YOUTUBE_PATTERNS = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
    ]

    def extract_video_id(self, url: str) -> Optional[str]:
        """URL에서 비디오 ID 추출"""
        for pattern in self.YOUTUBE_PATTERNS:
            match = re.search(pattern, url)
            if match:
                return match.group(1)

        # URL 파라미터에서 추출
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "v" in params:
            return params["v"][0]

        return None

    def get_transcript(
        self,
        video_id: str,
        languages: Optional[list[str]] = None
    ) -> tuple[Optional[str], Optional[str]]:
        """자막 추출 (transcript, language)"""
        if languages is None:
            languages = self.PREFERRED_LANGUAGES

        try:
            # 사용 가능한 자막 목록 조회
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            transcript = None
            used_language = None

            # 수동 생성 자막 우선 시도
            for lang in languages:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    used_language = lang
                    break
                except NoTranscriptFound:
                    continue

            # 자동 생성 자막 시도
            if transcript is None:
                try:
                    # 영어 자동 생성 자막을 한국어로 번역
                    transcript = transcript_list.find_generated_transcript(["en"])
                    used_language = "en (auto)"
                except NoTranscriptFound:
                    # 아무 자막이나 가져오기
                    try:
                        for t in transcript_list:
                            transcript = t
                            used_language = t.language_code
                            break
                    except Exception:
                        pass

            if transcript is None:
                return None, None

            # 자막 텍스트 추출
            transcript_data = transcript.fetch()
            text_parts = [entry["text"] for entry in transcript_data]
            full_text = " ".join(text_parts)

            # 텍스트 정리
            full_text = self._clean_transcript(full_text)

            return full_text, used_language

        except TranscriptsDisabled:
            print(f"[YouTube] 자막이 비활성화됨: {video_id}")
            return None, None
        except VideoUnavailable:
            print(f"[YouTube] 비디오를 찾을 수 없음: {video_id}")
            return None, None
        except Exception as e:
            print(f"[YouTube] 자막 추출 실패 ({video_id}): {e}")
            return None, None

    def _clean_transcript(self, text: str) -> str:
        """자막 텍스트 정리"""
        # 연속된 공백 정리
        text = re.sub(r"\s+", " ", text)

        # [음악], [박수] 등 제거
        text = re.sub(r"\[.*?\]", "", text)

        # 앞뒤 공백 제거
        text = text.strip()

        return text

    def get_video_info(self, url_or_id: str) -> Optional[YouTubeVideo]:
        """비디오 정보 및 자막 추출"""
        # URL인 경우 ID 추출
        if url_or_id.startswith("http"):
            video_id = self.extract_video_id(url_or_id)
        else:
            video_id = url_or_id

        if not video_id:
            return None

        # 자막 추출
        transcript, language = self.get_transcript(video_id)

        return YouTubeVideo(
            video_id=video_id,
            transcript=transcript,
            language=language
        )

    def get_transcript_with_timestamps(
        self,
        video_id: str,
        languages: Optional[list[str]] = None
    ) -> Optional[list[dict]]:
        """타임스탬프 포함 자막 추출"""
        if languages is None:
            languages = self.PREFERRED_LANGUAGES

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            for lang in languages:
                try:
                    transcript = transcript_list.find_transcript([lang])
                    return transcript.fetch()
                except NoTranscriptFound:
                    continue

            # 자동 생성 자막 시도
            try:
                transcript = transcript_list.find_generated_transcript(["en"])
                return transcript.fetch()
            except NoTranscriptFound:
                pass

            return None

        except Exception as e:
            print(f"[YouTube] 타임스탬프 자막 추출 실패: {e}")
            return None

    def format_transcript_with_timestamps(
        self,
        transcript_data: list[dict],
        interval_seconds: int = 60
    ) -> str:
        """타임스탬프 포맷팅 (분 단위)"""
        if not transcript_data:
            return ""

        formatted_parts = []
        current_minute = -1

        for entry in transcript_data:
            start_time = entry.get("start", 0)
            minute = int(start_time // 60)

            if minute > current_minute:
                current_minute = minute
                formatted_parts.append(f"\n[{minute:02d}:00]")

            formatted_parts.append(entry["text"])

        return " ".join(formatted_parts)


if __name__ == "__main__":
    extractor = YouTubeTranscriptExtractor()

    # 테스트
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    video_id = extractor.extract_video_id(test_url)
    print(f"Video ID: {video_id}")

    if video_id:
        video = extractor.get_video_info(video_id)
        if video and video.transcript:
            print(f"언어: {video.language}")
            print(f"자막 길이: {len(video.transcript)} 글자")
            print(f"자막 미리보기: {video.transcript[:500]}...")
        else:
            print("자막을 가져올 수 없습니다.")
