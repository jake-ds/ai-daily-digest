"""Unified article context builder for LinkedIn post generation.

Shared by both Agent mode (linkedin_agent.py) and Simple mode (linkedin_service.py).
"""

from web.models import Article


def build_article_context(article: Article, source_content: str = "", research_context: str = "") -> str:
    """Build enriched article context with metadata, source content, and research."""
    lines = [
        f"## 기사 정보",
        f"- 제목: {article.title}",
        f"- 출처: {article.source}",
        f"- URL: {article.url}",
        f"- 카테고리: {article.category or '미분류'}",
        f"- 요약: {article.ai_summary or article.summary or '없음'}",
    ]

    # Score 기반 톤 가이드 (AI 점수 우선, fallback keyword 점수)
    ai = article.ai_score if article.ai_score is not None else article.score
    if ai and ai >= 8:
        lines.append(f"- 품질 점수: {ai}/10 (고품질 기사 → 깊은 분석과 구체적 인사이트를 포함하세요)")
    elif ai and ai <= 4:
        lines.append(f"- 품질 점수: {ai}/10 (간결한 코멘터리와 핵심 포인트 위주로 작성하세요)")
    elif ai:
        lines.append(f"- 품질 점수: {ai}/10")
    if article.linkedin_potential:
        lines.append(f"- LinkedIn 잠재력: {article.linkedin_potential}/10")

    # Viral score 맥락
    if article.viral_score and article.viral_score > 0:
        lines.append(f"- 바이럴 점수: {article.viral_score} (화제성 높은 뉴스 → 독자의 관심을 활용하되, 과장은 피하세요)")

    # Source 기반 맥락
    authority_sources = ["mit", "stanford", "google", "deepmind", "openai", "anthropic", "meta ai", "microsoft research"]
    if article.source and any(src in article.source.lower() for src in authority_sources):
        lines.append(f"- 출처 권위: {article.source}는 권위 있는 연구/기술 기관입니다. 연구 권위를 강조하세요.")

    result = "\n".join(lines)

    # Append source content if available
    if source_content:
        result += f"""

## 원문 콘텐츠
아래는 기사 원문에서 추출한 내용입니다. 구체적 수치, 인용구, 사례, 대비 소재를 반드시 활용하세요.

{source_content}"""

    # Append research context if available
    if research_context:
        result += f"""

{research_context}

위 리서치 결과에서 신뢰도 있는 수치, 인용구, 업계 맥락, 경쟁사 비교 데이터를 활용하여 포스트의 깊이를 높이세요."""

    return result
