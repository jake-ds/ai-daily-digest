"""Settings API endpoints for managing guidelines and configurations."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path

from web.config import LINKEDIN_GUIDELINES_PATH

router = APIRouter(prefix="/api/settings", tags=["settings"])


class GuidelinesUpdate(BaseModel):
    content: str


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
