"""Settings API endpoints for managing guidelines and configurations."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from web.config import LINKEDIN_GUIDELINES_PATH
from web.database import get_db
from web.models import Schedule, ReferencePost
from web.services.scheduler_service import scheduler_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


class GuidelinesUpdate(BaseModel):
    content: str


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    collection_type: str = Field(..., pattern="^(news|viral|all)$")
    cron_hour: int = Field(..., ge=0, le=23)
    cron_minute: int = Field(default=0, ge=0, le=59)
    is_active: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    collection_type: Optional[str] = Field(default=None, pattern="^(news|viral|all)$")
    cron_hour: Optional[int] = Field(default=None, ge=0, le=23)
    cron_minute: Optional[int] = Field(default=None, ge=0, le=59)
    is_active: Optional[bool] = None


class ReferencePostCreate(BaseModel):
    content: str = Field(..., min_length=10)
    author: Optional[str] = None
    source_url: Optional[str] = None
    scenario: Optional[str] = Field(default=None, pattern="^[A-F]$")


class ReferencePostScenarioUpdate(BaseModel):
    scenario: Optional[str] = Field(default=None, pattern="^[A-F]$")


class SuggestionApply(BaseModel):
    suggestion: dict


# --- Guidelines endpoints ---

@router.get("/linkedin-guidelines")
async def get_linkedin_guidelines():
    """Get the current LinkedIn guidelines content."""
    try:
        content = LINKEDIN_GUIDELINES_PATH.read_text(encoding="utf-8")
        return {
            "content": content,
            "path": str(LINKEDIN_GUIDELINES_PATH),
            "last_modified": LINKEDIN_GUIDELINES_PATH.stat().st_mtime,
        }
    except FileNotFoundError:
        return {
            "content": "",
            "path": str(LINKEDIN_GUIDELINES_PATH),
            "last_modified": None,
        }


@router.put("/linkedin-guidelines")
async def update_linkedin_guidelines(data: GuidelinesUpdate):
    """Update the LinkedIn guidelines content."""
    try:
        # Create backup
        if LINKEDIN_GUIDELINES_PATH.exists():
            backup_path = LINKEDIN_GUIDELINES_PATH.with_suffix(".md.backup")
            backup_path.write_text(
                LINKEDIN_GUIDELINES_PATH.read_text(encoding="utf-8"),
                encoding="utf-8"
            )

        # Write new content
        LINKEDIN_GUIDELINES_PATH.write_text(data.content, encoding="utf-8")

        return {
            "success": True,
            "message": "Guidelines updated successfully",
            "path": str(LINKEDIN_GUIDELINES_PATH),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save guidelines: {str(e)}")


@router.post("/linkedin-guidelines/restore")
async def restore_linkedin_guidelines():
    """Restore LinkedIn guidelines from backup."""
    backup_path = LINKEDIN_GUIDELINES_PATH.with_suffix(".md.backup")

    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="No backup file found")

    try:
        content = backup_path.read_text(encoding="utf-8")
        LINKEDIN_GUIDELINES_PATH.write_text(content, encoding="utf-8")

        return {
            "success": True,
            "message": "Guidelines restored from backup",
            "content": content,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restore: {str(e)}")


# --- Reference posts endpoints ---

@router.post("/reference-posts")
async def create_reference_post(
    data: ReferencePostCreate,
    db: Session = Depends(get_db),
):
    """Register and analyze a reference LinkedIn post."""
    from web.services.guidelines_learner import GuidelinesLearner

    learner = GuidelinesLearner(db)

    try:
        # Analyze the post
        analysis = learner.analyze_post(data.content)

        # Generate update suggestions
        suggestions = learner.suggest_updates(analysis)

        # Save to database
        post = learner.save_reference_post(
            content=data.content,
            author=data.author,
            source_url=data.source_url,
            analysis=analysis,
            scenario=data.scenario,
        )

        return {
            "success": True,
            "post": post.to_dict(),
            "analysis": analysis,
            "suggestions": suggestions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/reference-posts")
async def get_reference_posts(
    scenario: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get all reference posts, optionally filtered by scenario."""
    query = db.query(ReferencePost)
    if scenario:
        query = query.filter(ReferencePost.scenario == scenario)
    posts = query.order_by(ReferencePost.created_at.desc()).all()
    return {
        "posts": [p.to_dict() for p in posts],
        "total": len(posts),
    }


@router.delete("/reference-posts/{post_id}")
async def delete_reference_post(
    post_id: int,
    db: Session = Depends(get_db),
):
    """Delete a reference post."""
    post = db.query(ReferencePost).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Reference post not found")

    db.delete(post)
    db.commit()
    return {"success": True}


@router.patch("/reference-posts/{post_id}/scenario")
async def update_reference_post_scenario(
    post_id: int,
    data: ReferencePostScenarioUpdate,
    db: Session = Depends(get_db),
):
    """Update the scenario tag of a reference post."""
    post = db.query(ReferencePost).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Reference post not found")

    post.scenario = data.scenario
    db.commit()
    return {"success": True, "post": post.to_dict()}


@router.post("/guidelines/apply-suggestion")
async def apply_guideline_suggestion(
    data: SuggestionApply,
    db: Session = Depends(get_db),
):
    """Apply a suggestion to update the guidelines."""
    from web.services.guidelines_learner import GuidelinesLearner

    learner = GuidelinesLearner(db)

    try:
        updated_content = learner.apply_suggestion(data.suggestion)
        return {
            "success": True,
            "content": updated_content,
            "message": "Guideline updated successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply suggestion: {str(e)}")


# --- Schedule endpoints ---

@router.get("/schedules")
async def get_schedules(db: Session = Depends(get_db)):
    """Get all schedules with next run times."""
    schedules = scheduler_service.get_schedules(db)
    next_run_times = scheduler_service.get_next_run_times()

    return {
        "schedules": [
            {
                **s.to_dict(),
                "next_run_at": next_run_times.get(f"schedule_{s.id}"),
            }
            for s in schedules
        ]
    }


@router.post("/schedules")
async def create_schedule(data: ScheduleCreate, db: Session = Depends(get_db)):
    """Create a new schedule."""
    schedule = scheduler_service.create_schedule(
        db=db,
        name=data.name,
        collection_type=data.collection_type,
        cron_hour=data.cron_hour,
        cron_minute=data.cron_minute,
        is_active=data.is_active,
    )

    return {
        "success": True,
        "schedule": schedule.to_dict(),
    }


@router.get("/schedules/{schedule_id}")
async def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Get a single schedule."""
    schedule = scheduler_service.get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    next_run_times = scheduler_service.get_next_run_times()
    return {
        **schedule.to_dict(),
        "next_run_at": next_run_times.get(f"schedule_{schedule.id}"),
    }


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    db: Session = Depends(get_db),
):
    """Update a schedule."""
    schedule = scheduler_service.update_schedule(
        db=db,
        schedule_id=schedule_id,
        name=data.name,
        collection_type=data.collection_type,
        cron_hour=data.cron_hour,
        cron_minute=data.cron_minute,
        is_active=data.is_active,
    )

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return {
        "success": True,
        "schedule": schedule.to_dict(),
    }


@router.delete("/schedules/{schedule_id}")
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Delete a schedule."""
    success = scheduler_service.delete_schedule(db, schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return {"success": True}
