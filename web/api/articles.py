"""Articles API endpoints."""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from web.database import get_db
from web.models import Article

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("")
async def get_articles(
    category: Optional[str] = Query(default=None),
    linkedin_status: Optional[str] = Query(default=None),
    collection_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=100),
    sort_by: str = Query(default="collected_at"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
):
    """
    Get paginated list of articles.

    - **category**: Filter by category (bigtech, research, news, viral, etc.)
    - **linkedin_status**: Filter by LinkedIn status (none, generated, posted)
    - **collection_id**: Filter by collection
    - **page**: Page number
    - **per_page**: Items per page
    - **sort_by**: Field to sort by (collected_at, score, published_at)
    - **sort_order**: Sort order (asc, desc)
    """
    query = db.query(Article)

    # Apply filters
    if category:
        query = query.filter(Article.category == category)
    if linkedin_status:
        query = query.filter(Article.linkedin_status == linkedin_status)
    if collection_id:
        query = query.filter(Article.collection_id == collection_id)

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
    """Get top-scoring articles from recent collections."""
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=7)

    articles = (
        db.query(Article)
        .filter(Article.collected_at >= cutoff)
        .order_by(Article.score.desc())
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
