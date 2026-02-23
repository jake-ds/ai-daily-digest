"""Web researcher using Google Custom Search for topic research."""

import json
import time
from typing import Optional

import httpx
from anthropic import Anthropic

from web.config import ANTHROPIC_API_KEY
from web.services.source_fetcher import fetch as fetch_source_content

# Use Haiku for query generation (fast, cheap)
MODEL_QUERY = "claude-haiku-4-5-20251001"

RESEARCH_TIMEOUT = 30  # seconds total
FETCH_TIMEOUT = 10  # per-page fetch
MAX_RESEARCH_CHARS = 3000


def _get_cse_config() -> tuple[Optional[str], Optional[str]]:
    """Get Google CSE credentials (lazy import to avoid circular)."""
    from web.config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_ENGINE_ID
    return GOOGLE_CSE_API_KEY, GOOGLE_CSE_ENGINE_ID


def _generate_search_query(title: str, summary: str) -> str:
    """Generate an effective search query from article title/summary using Haiku."""
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = f"""다음 기사 제목과 요약에서 Google 검색에 적합한 영어 검색 쿼리를 1개만 생성해주세요.
배경 지식, 업계 맥락, 경쟁사 비교 등 추가 리서치에 유용한 쿼리여야 합니다.

제목: {title}
요약: {summary or '없음'}

검색 쿼리만 출력하세요 (따옴표 없이, 한 줄로)."""

        response = client.messages.create(
            model=MODEL_QUERY,
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )
        query = response.content[0].text.strip().strip('"').strip("'")
        return query
    except Exception:
        # Fallback: use title as-is
        return title


def _search_google(query: str, num_results: int = 5) -> list[dict]:
    """Search Google Custom Search API.

    Returns list of {title, link, snippet}.
    """
    api_key, engine_id = _get_cse_config()
    if not api_key or not engine_id:
        return []

    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": api_key,
                    "cx": engine_id,
                    "q": query,
                    "num": min(num_results, 10),
                },
            )
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results

    except Exception as e:
        print(f"[WebResearcher] Google CSE 검색 실패: {e}")
        return []


def _fetch_top_pages(results: list[dict], max_pages: int = 2) -> list[dict]:
    """Fetch full content from top search result pages."""
    enriched = []
    for result in results[:max_pages]:
        try:
            content = fetch_source_content(result["link"])
            if content:
                # Truncate individual page to 1500 chars
                if len(content) > 1500:
                    content = content[:1500] + "..."
                enriched.append({
                    **result,
                    "content": content,
                })
            else:
                enriched.append(result)
        except Exception:
            enriched.append(result)
    return enriched


def _format_research(query: str, results: list[dict], enriched: list[dict]) -> str:
    """Format research results into structured text."""
    lines = [
        "## 리서치 결과",
        f"",
        f'### 검색: "{query}"',
        "",
    ]

    # All results with snippets
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. [{r['title']}] ({r['link']})")
        if r.get("snippet"):
            lines.append(f"   {r['snippet']}")
        lines.append("")

    # Enriched content from top pages
    if enriched:
        lines.append("### 추출된 핵심 콘텐츠")
        lines.append("")
        for r in enriched:
            if r.get("content"):
                lines.append(f"**{r['title']}**:")
                lines.append(r["content"])
                lines.append("")

    result = "\n".join(lines)

    # Enforce max length
    if len(result) > MAX_RESEARCH_CHARS:
        result = result[:MAX_RESEARCH_CHARS - 3] + "..."

    return result


def research(query: str, num_results: int = 5) -> Optional[str]:
    """Run web research for a topic.

    Args:
        query: Search query string
        num_results: Number of search results to fetch

    Returns:
        Formatted research text (max 3000 chars), or None if unavailable
    """
    api_key, engine_id = _get_cse_config()
    if not api_key or not engine_id:
        print("[WebResearcher] Google CSE API 키 미설정 — 리서치 건너뜀")
        return None

    start_time = time.time()

    try:
        # Step 1: Search
        results = _search_google(query, num_results)
        if not results:
            return None

        # Check timeout
        if time.time() - start_time > RESEARCH_TIMEOUT:
            return _format_research(query, results, [])

        # Step 2: Fetch top pages for deeper content
        enriched = _fetch_top_pages(results, max_pages=2)

        # Check timeout
        if time.time() - start_time > RESEARCH_TIMEOUT:
            return _format_research(query, results, [])

        return _format_research(query, results, enriched)

    except Exception as e:
        print(f"[WebResearcher] 리서치 실패: {e}")
        return None


def research_article(title: str, summary: str = "", num_results: int = 5) -> Optional[str]:
    """Research a topic based on article title and summary.

    Generates an optimized search query from the article info,
    then runs web research.

    Args:
        title: Article title
        summary: Article summary (optional)
        num_results: Number of search results

    Returns:
        Formatted research text, or None if unavailable
    """
    api_key, engine_id = _get_cse_config()
    if not api_key or not engine_id:
        return None

    start_time = time.time()

    try:
        # Generate search query
        query = _generate_search_query(title, summary)

        # Check timeout
        if time.time() - start_time > RESEARCH_TIMEOUT:
            return None

        return research(query, num_results)

    except Exception as e:
        print(f"[WebResearcher] 리서치 실패: {e}")
        return None
