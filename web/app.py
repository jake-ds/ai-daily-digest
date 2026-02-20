"""FastAPI main application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

from web.database import init_db, get_db
from web.api import digest_router, articles_router, linkedin_router, settings_router
from web.models import Article, Collection, LinkedInDraft, Schedule
from web.services.digest_service import DigestService
from web.services.linkedin_service import SCENARIOS
from web.services.scheduler_service import scheduler_service
from web.config import LINKEDIN_GUIDELINES_PATH


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup/shutdown events."""
    # Startup
    init_db()
    scheduler_service.start()

    yield

    # Shutdown
    scheduler_service.shutdown()

    # Cleanup agent sessions
    from web.services.linkedin_agent import cleanup_old_sessions
    cleanup_old_sessions(max_age_seconds=0)

# Initialize app
app = FastAPI(
    title="AI Daily Digest",
    description="Web interface for news collection and LinkedIn post generation",
    version="1.0.0",
    lifespan=lifespan,
)

# Templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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
    q: Optional[str] = None,
    category: Optional[str] = None,
    date_range: Optional[str] = None,
    min_score: Optional[float] = None,
    favorite: Optional[str] = None,
    unread: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """Articles list page with search and filters."""
    per_page = 20

    query = db.query(Article)

    # Search query
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Article.title.ilike(search_pattern),
                Article.summary.ilike(search_pattern),
                Article.ai_summary.ilike(search_pattern),
            )
        )

    # Category filter
    if category:
        query = query.filter(Article.category == category)

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

    # Score filter
    if min_score:
        query = query.filter(Article.score >= min_score)

    # Favorite filter
    if favorite == "1":
        query = query.filter(Article.is_favorite == True)

    # Unread filter
    if unread == "1":
        query = query.filter(Article.is_read == False)

    total = query.count()
    articles = (
        query.order_by(Article.score.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    # Get categories for filter
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
            "search_query": q,
            "date_range": date_range,
            "min_score": min_score,
            "show_favorite": favorite == "1",
            "show_unread": unread == "1",
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

    # Detect recommended scenario (Claude-based with fallback)
    from web.services.linkedin_service import LinkedInService
    linkedin_service = LinkedInService(db)
    scenario_result = linkedin_service.detect_scenario_detailed(article)

    return templates.TemplateResponse(
        "articles/detail.html",
        {
            "request": request,
            "article": article,
            "scenarios": SCENARIOS,
            "drafts": article.linkedin_drafts,
            "recommended_scenario": scenario_result["scenario"],
            "scenario_reason": scenario_result.get("reason", ""),
            "scenario_confidence": scenario_result.get("confidence", 0),
        },
    )


# Posts pages
@app.get("/posts", response_class=HTMLResponse)
async def posts_list(
    request: Request,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Posts list page showing finalized/published LinkedIn posts."""
    query = db.query(LinkedInDraft).filter(
        LinkedInDraft.status.in_(["final", "published"])
    )

    if status:
        query = query.filter(LinkedInDraft.status == status)

    posts = query.order_by(LinkedInDraft.created_at.desc()).all()

    return templates.TemplateResponse(
        "posts/list.html",
        {
            "request": request,
            "posts": posts,
            "current_status": status,
            "scenarios": SCENARIOS,
        },
    )


@app.get("/posts/{draft_id}", response_class=HTMLResponse)
async def post_detail(
    request: Request,
    draft_id: int,
    db: Session = Depends(get_db),
):
    """Post detail page."""
    post = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    if not post:
        return templates.TemplateResponse(
            "404.html",
            {"request": request, "message": "Post not found"},
            status_code=404,
        )

    return templates.TemplateResponse(
        "posts/detail.html",
        {
            "request": request,
            "post": post,
            "scenarios": SCENARIOS,
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
    draft = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    return templates.TemplateResponse(
        "partials/draft_card.html",
        {"request": request, "draft": draft, "scenarios": SCENARIOS},
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """Settings page for managing LinkedIn guidelines."""
    content = ""
    try:
        content = LINKEDIN_GUIDELINES_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        pass

    # Load reference posts
    from web.models import ReferencePost
    reference_posts = db.query(ReferencePost).order_by(ReferencePost.created_at.desc()).all()

    return templates.TemplateResponse(
        "settings/guidelines.html",
        {
            "request": request,
            "content": content,
            "scenarios": SCENARIOS,
            "reference_posts": reference_posts,
        },
    )


@app.get("/settings/schedule", response_class=HTMLResponse)
async def settings_schedule_page(request: Request, db: Session = Depends(get_db)):
    """Settings page for managing collection schedules."""
    schedules = scheduler_service.get_schedules(db)
    next_run_times = scheduler_service.get_next_run_times()

    # Attach next_run_at to each schedule for template
    schedules_with_next = []
    for s in schedules:
        s_dict = {
            "id": s.id,
            "name": s.name,
            "collection_type": s.collection_type,
            "cron_hour": s.cron_hour,
            "cron_minute": s.cron_minute,
            "is_active": s.is_active,
            "last_run_at": s.last_run_at,
            "next_run_at": next_run_times.get(f"schedule_{s.id}"),
        }
        schedules_with_next.append(type("Schedule", (), s_dict)())

    return templates.TemplateResponse(
        "settings/schedule.html",
        {
            "request": request,
            "schedules": schedules_with_next,
        },
    )
