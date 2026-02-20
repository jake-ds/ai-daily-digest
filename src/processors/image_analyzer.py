"""이미지 분석기 - Claude Vision API 연동"""

import os
import base64
import httpx
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Union

import anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ImageAnalysis:
    """이미지 분석 결과"""
    description: str
    text_content: Optional[str] = None
    tags: list[str] = None
    summary: Optional[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


class ImageAnalyzer:
    """Claude Vision을 사용한 이미지 분석"""

    # 지원되는 이미지 형식
    SUPPORTED_FORMATS = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY가 설정되지 않았습니다.")

        self.client = anthropic.Anthropic(api_key=self.api_key)

    def _get_media_type(self, file_path: Union[str, Path]) -> Optional[str]:
        """파일 확장자로 미디어 타입 결정"""
        path = Path(file_path)
        ext = path.suffix.lower()
        return self.SUPPORTED_FORMATS.get(ext)

    def _encode_image_file(self, file_path: Union[str, Path]) -> tuple[str, str]:
        """이미지 파일을 base64로 인코딩"""
        path = Path(file_path)
        media_type = self._get_media_type(path)

        if not media_type:
            raise ValueError(f"지원되지 않는 이미지 형식: {path.suffix}")

        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")

        return data, media_type

    def _fetch_image_url(self, url: str) -> tuple[str, str]:
        """URL에서 이미지 다운로드 및 인코딩"""
        response = httpx.get(url, follow_redirects=True, timeout=30)
        response.raise_for_status()

        # Content-Type에서 미디어 타입 추출
        content_type = response.headers.get("content-type", "image/jpeg")
        media_type = content_type.split(";")[0].strip()

        # 지원되는 형식인지 확인
        if media_type not in self.SUPPORTED_FORMATS.values():
            # 기본값으로 jpeg 사용
            media_type = "image/jpeg"

        data = base64.standard_b64encode(response.content).decode("utf-8")
        return data, media_type

    def analyze_image(
        self,
        image_source: Union[str, Path, bytes],
        prompt: Optional[str] = None,
        extract_text: bool = True
    ) -> ImageAnalysis:
        """이미지 분석 수행"""
        # 기본 프롬프트
        if prompt is None:
            prompt = """이 이미지를 분석해주세요. 다음 정보를 제공해주세요:

1. **설명**: 이미지에 무엇이 있는지 상세히 설명
2. **텍스트**: 이미지에 텍스트가 있다면 추출
3. **태그**: 이미지를 설명하는 키워드 5개
4. **요약**: 한 문장으로 요약

JSON 형식으로 응답해주세요:
{
  "description": "상세 설명",
  "text_content": "추출된 텍스트 또는 null",
  "tags": ["태그1", "태그2", ...],
  "summary": "한 문장 요약"
}"""

        # 이미지 데이터 준비
        if isinstance(image_source, bytes):
            # 바이트 데이터인 경우
            data = base64.standard_b64encode(image_source).decode("utf-8")
            media_type = "image/jpeg"  # 기본값
        elif isinstance(image_source, (str, Path)):
            path_str = str(image_source)
            if path_str.startswith(("http://", "https://")):
                # URL인 경우
                data, media_type = self._fetch_image_url(path_str)
            else:
                # 파일 경로인 경우
                data, media_type = self._encode_image_file(path_str)
        else:
            raise ValueError(f"지원되지 않는 이미지 소스 타입: {type(image_source)}")

        # API 호출
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ],
                }
            ],
        )

        # 응답 파싱
        response_text = message.content[0].text

        # JSON 파싱 시도
        try:
            import json
            # JSON 블록 추출
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0]

            result = json.loads(json_match.strip())
            return ImageAnalysis(
                description=result.get("description", response_text),
                text_content=result.get("text_content"),
                tags=result.get("tags", []),
                summary=result.get("summary")
            )
        except (json.JSONDecodeError, IndexError):
            # JSON 파싱 실패 시 텍스트 그대로 반환
            return ImageAnalysis(
                description=response_text,
                text_content=None,
                tags=[],
                summary=None
            )

    def describe_image(
        self,
        image_source: Union[str, Path, bytes],
        language: str = "ko"
    ) -> str:
        """이미지 간단 설명"""
        lang_prompt = "한국어로" if language == "ko" else "in English"

        prompt = f"이 이미지를 {lang_prompt} 2-3문장으로 간결하게 설명해주세요."

        analysis = self.analyze_image(image_source, prompt)
        return analysis.description

    def extract_text_from_image(
        self,
        image_source: Union[str, Path, bytes]
    ) -> Optional[str]:
        """이미지에서 텍스트 추출 (OCR)"""
        prompt = """이 이미지에서 모든 텍스트를 추출해주세요.
텍스트가 없다면 "텍스트 없음"이라고 응답해주세요.
텍스트만 출력하고 다른 설명은 하지 마세요."""

        analysis = self.analyze_image(image_source, prompt)
        text = analysis.description.strip()

        if text == "텍스트 없음" or text == "No text":
            return None

        return text


if __name__ == "__main__":
    analyzer = ImageAnalyzer()

    # 테스트 URL
    test_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"

    print("이미지 분석 중...")
    try:
        analysis = analyzer.analyze_image(test_url)
        print(f"설명: {analysis.description}")
        print(f"텍스트: {analysis.text_content}")
        print(f"태그: {analysis.tags}")
        print(f"요약: {analysis.summary}")
    except Exception as e:
        print(f"분석 실패: {e}")
