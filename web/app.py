"""FastAPI main application."""

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime

from web.database import init_db, get_db
from web.api import digest_router, articles_router, linkedin_router, settings_router
from web.models import Article, Collection
from web.services.digest_service import DigestService
from web.services.linkedin_service import SCENARIOS
from web.config import LINKEDIN_GUIDELINES_PATH

# Initialize app
app = FastAPI(
    title="AI Daily Digest",
    description="Web interface for news collection and LinkedIn post generation",
    version="1.0.0",
)

# Templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()


# Include API routers
app.include_router(digest_router)
app.include_router(articles_router)
app.include_router(linkedin_router)
app.include_router(settings_router)


# Web pages
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard page."""
    service = DigestService(db)

    # Get stats
    stats = service.get_today_stats()

    # Get recent collections
    recent_collections = service.get_recent_collections(limit=5)

    # Get top articles
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=7)
    top_articles = (
        db.query(Article)
        .filter(Article.collected_at >= cutoff)
        .order_by(Article.score.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": stats,
            "recent_collections": recent_collections,
            "top_articles": top_articles,
        },
    )


@app.get("/articles", response_class=HTMLResponse)
async def articles_list(
    request: Request,
    category: str = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """Articles list page."""
    per_page = 20

    query = db.query(Article)
    if category:
        query = query.filter(Article.category == category)

    total = query.count()
    articles = (
        query.order_by(Article.collected_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Get categories for filter
    from sqlalchemy import func
    categories = (
        db.query(Article.category, func.count(Article.id))
        .group_by(Article.category)
        .all()
    )

    return templates.TemplateResponse(
        "articles/list.html",
        {
            "request": request,
            "articles": articles,
            "categories": categories,
            "current_category": category,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
        },
    )


@app.get("/articles/{article_id}", response_class=HTMLResponse)
async def article_detail(
    request: Request,
    article_id: int,
    db: Session = Depends(get_db),
):
    """Article detail page with LinkedIn generation."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Article not found"},
            status_code=404,
        )

    # Detect recommended scenario
    from web.services.linkedin_service import LinkedInService
    linkedin_service = LinkedInService(db)
    recommended_scenario = linkedin_service.detect_scenario(article)

    return templates.TemplateResponse(
        "articles/detail.html",
        {
            "request": request,
            "article": article,
            "scenarios": SCENARIOS,
            "drafts": article.linkedin_drafts,
            "recommended_scenario": recommended_scenario,
        },
    )


# HTMX partials
@app.get("/partials/collection-status/{collection_id}", response_class=HTMLResponse)
async def collection_status_partial(
    request: Request,
    collection_id: int,
    db: Session = Depends(get_db),
):
    """HTMX partial for collection status polling."""
    collection = db.query(Collection).filter(Collection.id == collection_id).first()
    return templates.TemplateResponse(
        "partials/collection_status.html",
        {"request": request, "collection": collection},
    )


@app.get("/partials/draft/{draft_id}", response_class=HTMLResponse)
async def draft_partial(
    request: Request,
    draft_id: int,
    db: Session = Depends(get_db),
):
    """HTMX partial for draft card."""
    from web.models import LinkedInDraft
    draft = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    return templates.TemplateResponse(
        "partials/draft_card.html",
        {"request": request, "draft": draft, "scenarios": SCENARIOS},
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page for managing LinkedIn guidelines."""
    content = ""
    try:
        content = LINKEDIN_GUIDELINES_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        pass

    return templates.TemplateResponse(
        "settings/guidelines.html",
        {
            "request": request,
            "content": content,
            "scenarios": SCENARIOS,
        },
    )
