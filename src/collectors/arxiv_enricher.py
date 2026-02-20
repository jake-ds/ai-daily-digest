"""arXiv API를 사용하여 논문 상세 정보(기관 등) 보강"""

import re
import time
import xml.etree.ElementTree as ET
from typing import Optional, TYPE_CHECKING
import httpx

if TYPE_CHECKING:
    from .rss_collector import Article


class ArxivEnricher:
    """arXiv API로 논문 메타데이터 보강"""

    API_URL = "https://export.arxiv.org/api/query"
    NAMESPACES = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom"
    }

    def __init__(self):
        self.client = httpx.Client(timeout=30.0)

    def _extract_arxiv_id(self, url: str) -> Optional[str]:
        """URL에서 arXiv ID 추출"""
        # https://arxiv.org/abs/2601.06037 -> 2601.06037
        match = re.search(r'arxiv\.org/abs/([0-9]+\.[0-9]+)', url)
        if match:
            return match.group(1)
        return None

    def _fetch_paper_info(self, arxiv_id: str) -> Optional[dict]:
        """arXiv API로 논문 정보 조회"""
        try:
            params = {"id_list": arxiv_id}
            resp = self.client.get(self.API_URL, params=params)
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            entry = root.find("atom:entry", self.NAMESPACES)

            if entry is None:
                return None

            # 저자 및 소속 기관 추출
            authors_info = []
            for author in entry.findall("atom:author", self.NAMESPACES):
                name = author.find("atom:name", self.NAMESPACES)
                affiliation = author.find("arxiv:affiliation", self.NAMESPACES)

                author_data = {
                    "name": name.text if name is not None else "",
                    "affiliation": affiliation.text if affiliation is not None else ""
                }
                authors_info.append(author_data)

            # 기관만 추출 (중복 제거)
            affiliations = []
            for author in authors_info:
                if author["affiliation"] and author["affiliation"] not in affiliations:
                    affiliations.append(author["affiliation"])

            return {
                "authors": authors_info,
                "affiliations": affiliations
            }

        except Exception as e:
            print(f"arXiv API 오류 [{arxiv_id}]: {e}")
            return None

    def _format_affiliations(self, affiliations: list) -> str:
        """기관 목록을 문자열로 포맷"""
        if not affiliations:
            return ""

        # 최대 3개 기관만 표시
        if len(affiliations) <= 3:
            return ", ".join(affiliations)
        else:
            return ", ".join(affiliations[:3]) + f" 외 {len(affiliations) - 3}개 기관"

    def enrich_article(self, article: "Article") -> "Article":
        """단일 논문에 기관 정보 추가"""
        if article.category != "research":
            return article

        arxiv_id = self._extract_arxiv_id(article.url)
        if not arxiv_id:
            return article

        info = self._fetch_paper_info(arxiv_id)
        if not info:
            return article

        affiliations = info.get("affiliations", [])
        if affiliations:
            # 기관 정보가 있으면 업데이트
            article.authors = self._format_affiliations(affiliations)
        # 기관 정보가 없으면 기존 저자 정보 유지 (LLM이 나중에 추론)

        return article

    def enrich_articles(self, articles: list["Article"], limit: int = 10) -> list["Article"]:
        """여러 논문에 기관 정보 추가 (API 부하 고려하여 제한)"""
        research_articles = [a for a in articles if a.category == "research"]
        enriched_count = 0

        for article in research_articles:
            if enriched_count >= limit:
                break

            arxiv_id = self._extract_arxiv_id(article.url)
            if not arxiv_id:
                continue

            self.enrich_article(article)
            enriched_count += 1

            # API 부하 방지를 위한 딜레이
            time.sleep(0.5)

        print(f"arXiv 기관 정보 보강: {enriched_count}개 논문")
        return articles

    def __del__(self):
        if hasattr(self, 'client'):
            self.client.close()
