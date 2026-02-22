"""LinkedIn API endpoints."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from web.database import get_db
from web.models import Article, LinkedInDraft
from web.services.linkedin_service import LinkedInService, SCENARIOS

router = APIRouter(prefix="/api/linkedin", tags=["linkedin"])


# --- Pydantic models ---

class AgentInputData(BaseModel):
    direction: Optional[str] = None
    feedback: Optional[str] = None


class ChatMessage(BaseModel):
    message: str


class ContentUpdate(BaseModel):
    content: str


class PostUpdate(BaseModel):
    status: Optional[str] = None
    linkedin_url: Optional[str] = None


# --- Existing endpoints ---

@router.get("/scenarios")
async def get_scenarios():
    """Get available LinkedIn post scenarios."""
    return {
        "scenarios": {
            key: {
                "name": value["name"],
                "description": value["description"],
            }
            for key, value in SCENARIOS.items()
        }
    }


@router.get("/scenario/{article_id}")
async def get_scenario_with_alternatives(
    article_id: int,
    db: Session = Depends(get_db),
):
    """Get recommended scenario with confidence and alternatives."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    service = LinkedInService(db)

    try:
        result = service.detect_scenario_with_alternatives(article)
        return {
            "article_id": article_id,
            "primary": result["primary"],
            "alternatives": result["alternatives"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scenario detection failed: {str(e)}")


@router.post("/hooks/{article_id}")
async def generate_hooks(
    article_id: int,
    scenario: Optional[str] = Query(default=None, regex="^[A-F]$"),
    count: int = Query(default=5, ge=1, le=10),
    db: Session = Depends(get_db),
):
    """Generate multiple hook options for an article before full draft."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    service = LinkedInService(db)

    try:
        hooks = service.generate_hooks(article, scenario=scenario, count=count)
        return {
            "article_id": article_id,
            "scenario": scenario or service.detect_scenario(article),
            "hooks": hooks,
            "count": len(hooks),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Hook generation failed: {str(e)}")


@router.post("/generate/{article_id}")
async def generate_draft(
    article_id: int,
    scenario: Optional[str] = Query(default=None, regex="^[A-F]$"),
    hook: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Generate a LinkedIn draft for an article.

    - **article_id**: Article ID to generate draft for
    - **scenario**: Scenario (A-F), auto-detected if not provided
    - **hook**: Pre-selected hook text to use as opening
    """
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    service = LinkedInService(db)

    try:
        draft = service.generate_draft(article, scenario=scenario, hook=hook)
        return {
            "message": "Draft generated successfully",
            "draft": draft.to_dict(),
            "detected_scenario": scenario or service.detect_scenario(article),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@router.get("/drafts/{article_id}")
async def get_drafts(
    article_id: int,
    db: Session = Depends(get_db),
):
    """Get all drafts for an article."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    service = LinkedInService(db)
    drafts = service.get_drafts_for_article(article_id)

    return {
        "article_id": article_id,
        "drafts": [d.to_dict() for d in drafts],
        "total": len(drafts),
    }


@router.post("/regenerate/{draft_id}")
async def regenerate_draft(
    draft_id: int,
    db: Session = Depends(get_db),
):
    """Regenerate a draft with the same scenario."""
    existing = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Draft not found")

    service = LinkedInService(db)

    try:
        new_draft = service.regenerate_draft(draft_id)
        return {
            "message": "Draft regenerated successfully",
            "draft": new_draft.to_dict(),
            "previous_version": existing.version,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: int,
    db: Session = Depends(get_db),
):
    """Delete a specific draft."""
    draft = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    db.delete(draft)
    db.commit()

    return {"message": "Draft deleted successfully"}


# --- Agent endpoints ---

@router.post("/agent/start/{article_id}")
async def agent_start(
    article_id: int,
    scenario: Optional[str] = Query(default=None, regex="^[A-F]$"),
    hook: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Start an agent session for article. Returns SSE stream."""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    from web.services.linkedin_agent import LinkedInAgent

    agent = LinkedInAgent(db)

    async def event_generator():
        async for event in agent.run(article_id, scenario, hook=hook):
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/agent/{session_id}/input")
async def agent_input(
    session_id: str,
    data: AgentInputData,
):
    """Send user input to a waiting agent session."""
    from web.services.linkedin_agent import get_session

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "waiting":
        raise HTTPException(status_code=400, detail=f"Session not waiting for input (status: {session.status})")

    # Store input data and signal the event
    session.input_data = data.model_dump(exclude_none=True)
    session.input_event.set()

    return {"success": True, "session_id": session_id}


@router.get("/agent/{session_id}/status")
async def agent_status(session_id: str):
    """Get the current status of an agent session."""
    from web.services.linkedin_agent import get_session

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "status": session.status,
        "current_step": session.current_step,
        "article_id": session.article_id,
        "scenario": session.scenario,
    }


# --- Posts endpoints ---

@router.get("/posts")
async def get_posts(
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Get posts (final/published drafts)."""
    query = db.query(LinkedInDraft).filter(
        LinkedInDraft.status.in_(["final", "published"])
    )

    if status:
        query = query.filter(LinkedInDraft.status == status)

    posts = query.order_by(LinkedInDraft.created_at.desc()).all()

    return {
        "posts": [p.to_dict() for p in posts],
        "total": len(posts),
    }


@router.patch("/posts/{draft_id}")
async def update_post(
    draft_id: int,
    data: PostUpdate,
    db: Session = Depends(get_db),
):
    """Update post status or LinkedIn URL."""
    draft = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Post not found")

    if data.status:
        draft.status = data.status
        if data.status == "published" and not draft.published_at:
            draft.published_at = datetime.utcnow()

    if data.linkedin_url is not None:
        draft.linkedin_url = data.linkedin_url
        if data.linkedin_url and draft.status != "published":
            draft.status = "published"
            draft.published_at = datetime.utcnow()

    db.commit()
    db.refresh(draft)

    return {"success": True, "post": draft.to_dict()}


@router.post("/drafts/{draft_id}/finalize")
async def finalize_draft(
    draft_id: int,
    db: Session = Depends(get_db),
):
    """Mark a draft as final (ready to post)."""
    draft = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft.status = "final"
    db.commit()
    db.refresh(draft)

    return {"success": True, "post": draft.to_dict()}


# --- Chat & Edit endpoints ---

@router.post("/agent/{session_id}/chat")
async def agent_chat(
    session_id: str,
    data: ChatMessage,
    db: Session = Depends(get_db),
):
    """Send a chat message to refine the agent's draft."""
    from web.services.linkedin_agent import get_session, LinkedInAgent

    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "completed":
        raise HTTPException(status_code=400, detail=f"Session not completed (status: {session.status})")

    agent = LinkedInAgent(db)
    result = agent.chat_refine(session, data.message)

    return result


@router.post("/drafts/{draft_id}/chat")
async def draft_chat(
    draft_id: int,
    data: ChatMessage,
    db: Session = Depends(get_db),
):
    """Send a chat message to refine a draft (draft-based, no session needed)."""
    draft = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    service = LinkedInService(db)

    try:
        result = service.chat_refine_by_draft(draft_id, data.message)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat refine failed: {str(e)}")


@router.patch("/drafts/{draft_id}/content")
async def update_draft_content(
    draft_id: int,
    data: ContentUpdate,
    db: Session = Depends(get_db),
):
    """Directly update draft content (manual edit)."""
    draft = db.query(LinkedInDraft).filter(LinkedInDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft.draft_content = data.content
    db.commit()

    return {"success": True, "char_count": len(data.content)}
