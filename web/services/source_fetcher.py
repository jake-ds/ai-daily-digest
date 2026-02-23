"""Source content fetcher for deep reading of article URLs."""

import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup


# Domains that block scraping or return useless content
SKIP_DOMAINS = [
    "twitter.com", "x.com",
    "linkedin.com",
    "facebook.com", "fb.com",
    "instagram.com",
    "tiktok.com",
    "reddit.com",
    "youtube.com", "youtu.be",
    "t.co",
]

# Noise elements to remove from HTML
NOISE_SELECTORS = [
    "nav", "header", "footer", "aside",
    ".sidebar", ".nav", ".menu", ".ad", ".ads", ".advertisement",
    ".cookie", ".popup", ".modal", ".banner",
    "[role='navigation']", "[role='banner']", "[role='complementary']",
    "script", "style", "noscript", "iframe",
    ".social-share", ".share-buttons", ".comments",
]

TIMEOUT_SECONDS = 15
MAX_CONTENT_LENGTH = 4000
USER_AGENT = "Mozilla/5.0 (compatible; AIDigestBot/1.0)"


def _is_skip_domain(url: str) -> bool:
    """Check if URL belongs to a domain we should skip."""
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or ""
        return any(domain in hostname for domain in SKIP_DOMAINS)
    except Exception:
        return False


def _clean_html(soup: BeautifulSoup) -> str:
    """Remove noise elements and extract clean text."""
    for selector in NOISE_SELECTORS:
        for element in soup.select(selector):
            element.decompose()

    # Try article-specific selectors first
    article_selectors = ["article", "[role='main']", "main", ".post-content", ".article-body", ".entry-content"]
    for selector in article_selectors:
        article = soup.select_one(selector)
        if article:
            text = article.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

    # Fallback to body
    body = soup.find("body")
    if body:
        return body.get_text(separator="\n", strip=True)

    return soup.get_text(separator="\n", strip=True)


def _truncate(text: str, max_length: int = MAX_CONTENT_LENGTH) -> str:
    """Truncate text to max_length at a sentence boundary."""
    if len(text) <= max_length:
        return text

    # Try to cut at sentence boundary
    truncated = text[:max_length]
    last_period = max(truncated.rfind("."), truncated.rfind("。"), truncated.rfind("\n"))
    if last_period > max_length * 0.7:
        return truncated[:last_period + 1]

    return truncated + "..."


def _collapse_whitespace(text: str) -> str:
    """Collapse multiple blank lines into single blank lines."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def fetch(url: str) -> Optional[str]:
    """Fetch and extract main content from a URL.

    Args:
        url: Article URL to fetch

    Returns:
        Extracted text content (max 4000 chars), or None on failure
    """
    if not url:
        return None

    if _is_skip_domain(url):
        return None

    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        # Only process HTML content
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type.lower() and "text" not in content_type.lower():
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        text = _clean_html(soup)
        text = _collapse_whitespace(text)

        if len(text) < 100:
            return None

        return _truncate(text)

    except Exception:
        return None
