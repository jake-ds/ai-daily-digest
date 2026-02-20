"""Claude API 요약 모듈"""

import os
from typing import TYPE_CHECKING

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

if TYPE_CHECKING:
    from ..collectors.rss_collector import Article


class Summarizer:
    """Claude API를 사용한 기사 요약 및 링크드인 포스트 생성"""

    def __init__(self):
        self.client = None
        if Anthropic and os.getenv("ANTHROPIC_API_KEY"):
            self.client = Anthropic()

    def summarize_article(self, article: "Article") -> str:
        """개별 기사 한글 요약"""
        if not self.client:
            return article.summary[:200] if article.summary else ""

        # 연구 논문의 경우 기관 정보도 추출
        if article.category == "research":
            return self._summarize_research(article)

        prompt = f"""다음 기사를 한글로 1-2문장으로 핵심만 요약해주세요.
반드시 한글로 작성하세요. 영어 전문용어(AI, LLM, GPT 등)는 그대로 사용해도 됩니다.

제목: {article.title}
출처: {article.source}
내용: {article.summary or "내용 없음"}

한글 요약:"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"요약 실패 [{article.title[:30]}]: {e}")
            return article.summary[:200] if article.summary else ""

    def _summarize_research(self, article: "Article") -> str:
        """연구 논문 요약 + 기관 정보 추출"""
        prompt = f"""다음 연구 논문을 분석해주세요.

제목: {article.title}
저자: {article.authors or "정보 없음"}
초록: {article.summary or "내용 없음"}

다음 형식으로 정확히 답변해주세요 (각 항목 한 줄씩):
기관: [초록이나 제목에서 언급된 대학/연구소/기업명. 예: Google Research, MIT, Stanford University, Microsoft Research. 찾을 수 없으면 "미확인"]
요약: [한글로 1-2문장 핵심 요약]"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=250,
                messages=[{"role": "user", "content": prompt}]
            )
            result = response.content[0].text.strip()

            # 기관 정보 파싱
            lines = result.split("\n")
            institution = ""
            summary = ""

            for line in lines:
                line = line.strip()
                if line.startswith("기관:"):
                    institution = line.replace("기관:", "").strip()
                elif line.startswith("요약:"):
                    summary = line.replace("요약:", "").strip()

            # 기관 정보가 있으면 업데이트, 없으면 첫 번째 저자만 표시
            if institution and institution not in ["미확인", "정보 없음", "없음"]:
                article.authors = institution
            elif article.authors:
                # 첫 번째 저자만 간략히 표시
                first_author = article.authors.split(",")[0].strip()
                if " 외" not in first_author:
                    article.authors = f"{first_author} et al."

            return summary if summary else result

        except Exception as e:
            print(f"연구 요약 실패 [{article.title[:30]}]: {e}")
            return article.summary[:200] if article.summary else ""

    def summarize_all(self, articles: list["Article"], limit: int = 20) -> list["Article"]:
        """상위 기사들 요약"""
        for i, article in enumerate(articles[:limit]):
            article.ai_summary = self.summarize_article(article)
            if (i + 1) % 5 == 0:
                print(f"요약 진행 중: {i + 1}/{min(limit, len(articles))}")

        print(f"요약 완료: {min(limit, len(articles))}개 기사")
        return articles

    def generate_linkedin_post(self, articles: list["Article"], top_n: int = 3) -> str:
        """링크드인 포스트 초안 생성"""
        if not self.client:
            return self._fallback_linkedin_post(articles[:top_n])

        top_articles = articles[:top_n]
        articles_text = "\n".join([
            f"- {a.title} ({a.source}): {a.ai_summary or a.summary or ''}"
            for a in top_articles
        ])

        prompt = f"""오늘의 AI 뉴스 중 하이라이트를 바탕으로 링크드인 포스트를 작성해주세요.

대상: AI/Tech 업계 전문가
스타일: 인사이트 있고 전문적이지만 읽기 쉽게
언어: 한글 (영어 용어는 그대로 사용)
길이: 200-300자

하이라이트:
{articles_text}

포스트 (해시태그 포함):"""

        try:
            response = self.client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            print(f"포스트 생성 실패: {e}")
            return self._fallback_linkedin_post(top_articles)

    def _fallback_linkedin_post(self, articles: list["Article"]) -> str:
        """API 없을 때 기본 포스트 템플릿"""
        lines = ["오늘의 AI 하이라이트\n"]
        for article in articles:
            lines.append(f"- {article.title}")
        lines.append("\n#AI #Tech #LLM")
        return "\n".join(lines)
