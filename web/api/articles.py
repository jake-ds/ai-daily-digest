"""Articles API endpoints."""

from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from web.database import get_db
from web.models import Article
from web.config import ANTHROPIC_API_KEY

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("")
async def get_articles(
    q: Optional[str] = Query(default=None, description="Search query for title/summary"),
    category: Optional[str] = Query(default=None),
    linkedin_status: Optional[str] = Query(default=None),
    collection_id: Optional[int] = Query(default=None),
    favorite: Optional[bool] = Query(default=None, description="Filter favorites only"),
    unread: Optional[bool] = Query(default=None, description="Filter unread only"),
    min_score: Optional[float] = Query(default=None, description="Minimum keyword score filter"),
    max_score: Optional[float] = Query(default=None, description="Maximum keyword score filter"),
    min_ai_score: Optional[float] = Query(default=None, description="Minimum AI score filter (0-10)"),
    date_range: Optional[str] = Query(default=None, description="today/week/month/all"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=100),
    sort_by: str = Query(default="collected_at"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    """
    Get paginated list of articles with search and filtering.

    - **q**: Search in title and summary
    - **category**: Filter by category (bigtech, research, news, viral, etc.)
    - **linkedin_status**: Filter by LinkedIn status (none, generated, posted)
    - **collection_id**: Filter by collection
    - **favorite**: Filter favorites only (true/false)
    - **unread**: Filter unread only (true/false)
    - **min_score**: Minimum score filter
    - **max_score**: Maximum score filter
    - **date_range**: Filter by date (today/week/month/all)
    - **page**: Page number
    - **per_page**: Items per page
    - **min_ai_score**: Minimum AI evaluation score (0-10)
    - **sort_by**: Field to sort by (collected_at, score, ai_score, published_at)
    - **sort_order**: Sort order (asc, desc)
    """
    query = db.query(Article)

    # Apply search query
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Article.title.ilike(search_pattern),
                Article.summary.ilike(search_pattern),
                Article.ai_summary.ilike(search_pattern),
            )
        )

    # Apply filters
    if category:
        query = query.filter(Article.category == category)
    if linkedin_status:
        query = query.filter(Article.linkedin_status == linkedin_status)
    if collection_id:
        query = query.filter(Article.collection_id == collection_id)

    # Favorite/Read filters
    if favorite is True:
        query = query.filter(Article.is_favorite == True)
    if unread is True:
        query = query.filter(Article.is_read == False)

    # Score filters
    if min_score is not None:
        query = query.filter(Article.score >= min_score)
    if max_score is not None:
        query = query.filter(Article.score <= max_score)
    if min_ai_score is not None:
        query = query.filter(Article.ai_score >= min_ai_score)

    # Date range filter
    if date_range:
        now = datetime.utcnow()
        if date_range == "today":
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "week":
            cutoff = now - timedelta(days=7)
        elif date_range == "month":
            cutoff = now - timedelta(days=30)
        else:
            cutoff = None

        if cutoff:
            query = query.filter(Article.collected_at >= cutoff)

    # Get total count
    total = query.count()

    # Apply sorting
    sort_column = getattr(Article, sort_by, Article.collected_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    offset = (page - 1) * per_page
    articles = query.offset(offset).limit(per_page).all()

    return {
        "articles": [a.to_dict() for a in articles],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }


@router.get("/top")
async def get_top_articles(
    limit: int = Query(default=5, le=20),
    db: Session = Depends(get_db),
):
    """Get top-scoring articles from recent collections (ai_score preferred)."""
    from sqlalchemy import case
    cutoff = datetime.utcnow() - timedelta(days=7)

    # ai_score 있는 기사 우선, 없으면 keyword score fallback
    articles = (
        db.query(Article)
        .filter(Article.collected_at >= cutoff)
        .order_by(
            case((Article.ai_score != None, 0), else_=1),
            Article.ai_score.desc().nullslast(),
            Article.score.desc(),
        )
        .limit(limit)
        .all()
    )

    return {"articles": [a.to_dict() for a in articles]}


@router.get("/categories")
async def get_categories(db: Session = Depends(get_db)):
    """Get list of unique categories with counts."""
    from sqlalchemy import func

    results = (
        db.query(Article.category, func.count(Article.id))
        .group_by(Article.category)
        .all()
    )

    return {
        "categories": [
            {"name": cat or "unknown", "count": count}
            for cat, count in results
        ]
    }


@router.get("/{article_id}")
async def get_article(
    article_id: int,
    include_drafts: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Get article details."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    return article.to_dict(include_drafts=include_drafts)


@router.patch("/{article_id}")
async def update_article(
    article_id: int,
    linkedin_status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Update article fields."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if linkedin_status is not None:
        if linkedin_status not in ("none", "generated", "posted"):
            raise HTTPException(status_code=400, detail="Invalid linkedin_status")
        article.linkedin_status = linkedin_status

    db.commit()
    db.refresh(article)

    return article.to_dict()


@router.post("/{article_id}/favorite")
async def toggle_favorite(
    article_id: int,
    db: Session = Depends(get_db),
):
    """Toggle article favorite status."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    article.is_favorite = not article.is_favorite
    db.commit()
    db.refresh(article)

    return {
        "id": article.id,
        "is_favorite": article.is_favorite,
    }


@router.post("/{article_id}/read")
async def mark_as_read(
    article_id: int,
    db: Session = Depends(get_db),
):
    """Mark article as read."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    if not article.is_read:
        article.is_read = True
        article.read_at = datetime.utcnow()
        db.commit()
        db.refresh(article)

    return {
        "id": article.id,
        "is_read": article.is_read,
        "read_at": article.read_at.isoformat() if article.read_at else None,
    }


@router.post("/batch-evaluate")
async def batch_evaluate(
    limit: int = Query(default=50, le=100),
    force: bool = Query(default=False, description="Force re-evaluate all articles"),
    db: Session = Depends(get_db),
):
    """Batch AI evaluation for articles using Claude Haiku."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    from web.services.evaluation_service import EvaluationService
    service = EvaluationService(db)
    result = service.batch_evaluate(limit=limit, force=force)

    return {
        **result,
        "message": f"{result['processed']}개 기사 AI 평가 완료",
    }


@router.post("/{article_id}/evaluate")
async def evaluate_article(
    article_id: int,
    db: Session = Depends(get_db),
):
    """Single article AI evaluation (force re-evaluate)."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    from web.services.evaluation_service import EvaluationService
    service = EvaluationService(db)
    result = service.evaluate_article(article, force=True)

    if result is None:
        raise HTTPException(status_code=500, detail="Evaluation failed")

    return {
        "ai_score": article.ai_score,
        "linkedin_potential": article.linkedin_potential,
        "eval_data": result,
    }


@router.post("/batch-summarize")
async def batch_summarize(
    limit: int = Query(default=20, le=50),
    offset: int = Query(default=0, ge=0),
    force: bool = Query(default=False, description="Force re-summarize all articles including existing ones"),
    db: Session = Depends(get_db),
):
    """Batch generate Korean AI summaries for articles."""
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    import anthropic

    if force:
        # Re-summarize all articles (overwrite English summaries)
        articles = (
            db.query(Article)
            .order_by(Article.score.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    else:
        # Only articles without ai_summary
        articles = (
            db.query(Article)
            .filter(or_(Article.ai_summary == None, Article.ai_summary == ""))
            .order_by(Article.score.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    if not articles:
        return {"processed": 0, "remaining": 0, "message": "처리할 기사가 없습니다"}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    processed = 0

    for article in articles:
        prompt = f"""다음 기사를 한글로 1-2문장으로 핵심만 요약해주세요.
반드시 한글로 작성하세요. 영어 전문용어(AI, LLM, GPT 등)는 그대로 사용해도 됩니다.
마크다운 헤더(#)나 서식 없이 순수 텍스트로만 작성하세요.

제목: {article.title}
출처: {article.source or ""}
내용: {article.summary or "내용 없음"}

한글 요약:"""

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            article.ai_summary = response.content[0].text.strip()
            processed += 1
        except Exception as e:
            print(f"[Summarize] Failed for article {article.id}: {e}")
            continue

    db.commit()

    # Count remaining
    total_articles = db.query(Article).count()

    return {
        "processed": processed,
        "remaining": total_articles - processed if force else (
            db.query(Article)
            .filter(or_(Article.ai_summary == None, Article.ai_summary == ""))
            .count()
        ),
        "total": total_articles,
        "message": f"{processed}개 기사 한글 요약 완료",
    }
