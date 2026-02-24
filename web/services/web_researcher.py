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
MAX_RESEARCH_CHARS = 6000


def _get_cse_config() -> tuple[Optional[str], Optional[str]]:
    """Get Google CSE credentials (lazy import to avoid circular)."""
    from web.config import GOOGLE_CSE_API_KEY, GOOGLE_CSE_ENGINE_ID
    return GOOGLE_CSE_API_KEY, GOOGLE_CSE_ENGINE_ID


def _generate_search_queries(title: str, summary: str) -> list[str]:
    """Generate two effective search queries from article title/summary using Haiku."""
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        prompt = f"""다음 기사 제목과 요약에서 Google 검색에 적합한 영어 검색 쿼리를 2개 생성해주세요.
- 쿼리 1: 배경 지식, 업계 맥락을 조사할 수 있는 쿼리
- 쿼리 2: 경쟁사 비교, 대안 기술, 반론 등을 조사할 수 있는 쿼리

제목: {title}
요약: {summary or '없음'}

각 쿼리를 한 줄에 하나씩 출력하세요 (따옴표 없이, 번호 없이)."""

        response = client.messages.create(
            model=MODEL_QUERY,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        lines = [line.strip().strip('"').strip("'") for line in response.content[0].text.strip().split("\n") if line.strip()]
        # Return up to 2 queries, fallback to title
        return lines[:2] if lines else [title]
    except Exception:
        # Fallback: use title as-is
        return [title]


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


def _fetch_top_pages(results: list[dict], max_pages: int = 3) -> list[dict]:
    """Fetch full content from top search result pages."""
    enriched = []
    for result in results[:max_pages]:
        try:
            content = fetch_source_content(result["link"])
            if content:
                # Truncate individual page to 2500 chars
                if len(content) > 2500:
                    content = content[:2500] + "..."
                enriched.append({
                    **result,
                    "content": content,
                })
            else:
                enriched.append(result)
        except Exception:
            enriched.append(result)
    return enriched


def _format_research(queries: list[str], all_results: list[dict], enriched: list[dict]) -> str:
    """Format research results into structured text."""
    lines = [
        "## 리서치 결과",
        "",
    ]

    for query in queries:
        lines.append(f'### 검색: "{query}"')
        lines.append("")

    # All results with snippets
    for i, r in enumerate(all_results, 1):
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
        Formatted research text (max 6000 chars), or None if unavailable
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
            return _format_research([query], results, [])

        # Step 2: Fetch top pages for deeper content
        enriched = _fetch_top_pages(results, max_pages=3)

        # Check timeout
        if time.time() - start_time > RESEARCH_TIMEOUT:
            return _format_research([query], results, [])

        return _format_research([query], results, enriched)

    except Exception as e:
        print(f"[WebResearcher] 리서치 실패: {e}")
        return None


def research_article(title: str, summary: str = "", num_results: int = 5) -> Optional[str]:
    """Research a topic based on article title and summary.

    Generates two optimized search queries from the article info,
    then runs web research with both.

    Args:
        title: Article title
        summary: Article summary (optional)
        num_results: Number of search results per query

    Returns:
        Formatted research text, or None if unavailable
    """
    api_key, engine_id = _get_cse_config()
    if not api_key or not engine_id:
        return None

    start_time = time.time()

    try:
        # Generate search queries (2 queries)
        queries = _generate_search_queries(title, summary)

        # Check timeout
        if time.time() - start_time > RESEARCH_TIMEOUT:
            return None

        # Search with all queries, merge results (deduplicate by URL)
        all_results = []
        seen_urls = set()
        for query in queries:
            if time.time() - start_time > RESEARCH_TIMEOUT:
                break
            results = _search_google(query, num_results)
            for r in results:
                if r["link"] not in seen_urls:
                    seen_urls.add(r["link"])
                    all_results.append(r)

        if not all_results:
            return None

        # Check timeout
        if time.time() - start_time > RESEARCH_TIMEOUT:
            return _format_research(queries, all_results, [])

        # Fetch top pages for deeper content
        enriched = _fetch_top_pages(all_results, max_pages=3)

        # Check timeout
        if time.time() - start_time > RESEARCH_TIMEOUT:
            return _format_research(queries, all_results, [])

        return _format_research(queries, all_results, enriched)

    except Exception as e:
        print(f"[WebResearcher] 리서치 실패: {e}")
        return None
