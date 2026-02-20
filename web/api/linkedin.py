"""LinkedIn API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from web.database import get_db
from web.models import Article, LinkedInDraft
from web.services.linkedin_service import LinkedInService, SCENARIOS

router = APIRouter(prefix="/api/linkedin", tags=["linkedin"])


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


@router.post("/generate/{article_id}")
async def generate_draft(
    article_id: int,
    scenario: Optional[str] = Query(default=None, regex="^[A-E]$"),
    db: Session = Depends(get_db),
):
    """
    Generate a LinkedIn draft for an article.

    - **article_id**: Article ID to generate draft for
    - **scenario**: Scenario (A-E), auto-detected if not provided
    """
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    service = LinkedInService(db)

    try:
        draft = service.generate_draft(article, scenario=scenario)
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
