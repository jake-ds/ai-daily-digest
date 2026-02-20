"""Digest collection API endpoints."""

from fastapi import APIRouter, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session
from typing import Literal
from datetime import datetime

from web.database import get_db
from web.services.digest_service import DigestService
from web.models import Collection

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.post("/run")
async def run_collection(
    background_tasks: BackgroundTasks,
    type: Literal["news", "viral", "all"] = Query(default="all"),
    skip_notion: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """
    Run a collection.

    - **type**: Collection type (news, viral, all)
    - **skip_notion**: Skip Notion synchronization
    """
    # Create collection record first
    collection = Collection(
        name=f"{type.title()} Digest {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        type=type,
        status="running",
        progress_stage="starting",
        progress_detail="컬렉션 시작 준비 중...",
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)

    collection_id = collection.id

    # Run in background
    def run_task():
        from web.database import get_db_session

        with get_db_session() as task_db:
            task_service = DigestService(task_db)
            try:
                coll = task_db.query(Collection).filter(Collection.id == collection_id).first()
                articles = []

                # Collect based on type
                if type in ("news", "all"):
                    articles.extend(task_service._collect_news(48, collection_id))

                if type in ("viral", "all"):
                    articles.extend(task_service._collect_viral(collection_id))

                # Process articles
                articles = task_service._process_articles(articles, 50, collection_id)

                # Store
                task_service._update_progress(collection_id, "storing", "데이터베이스에 저장 중...")
                stored_count = task_service._store_articles(articles, collection_id)
                task_service._update_progress(collection_id, "storing", f"{stored_count}개 기사 저장 완료")

                # Notion sync
                notion_url = None
                if not skip_notion and articles:
                    try:
                        task_service._update_progress(collection_id, "syncing_notion", "Notion 페이지 생성 중...")
                        notion_url = task_service.notion_output.create_page(articles)
                        task_service._update_progress(collection_id, "syncing_notion", "Notion 동기화 완료")
                    except Exception as e:
                        task_service._update_progress(collection_id, "syncing_notion", f"Notion 실패: {str(e)[:50]}")
                        print(f"Notion sync failed: {e}")

                # Final update
                coll = task_db.query(Collection).filter(Collection.id == collection_id).first()
                coll.status = "completed"
                coll.article_count = stored_count
                coll.notion_page_url = notion_url
                coll.completed_at = datetime.utcnow()
                coll.progress_stage = "completed"
                coll.progress_detail = f"총 {stored_count}개 기사 수집 완료"
                task_db.commit()

            except Exception as e:
                coll = task_db.query(Collection).filter(Collection.id == collection_id).first()
                coll.status = "failed"
                coll.error_message = str(e)
                coll.completed_at = datetime.utcnow()
                coll.progress_stage = "failed"
                coll.progress_detail = str(e)[:100]
                task_db.commit()
                print(f"Collection failed: {e}")

    background_tasks.add_task(run_task)

    return {
        "message": "Collection started",
        "collection_id": collection_id,
        "type": type,
        "status": "running",
        "progress_stage": "starting",
    }


@router.get("/collections")
async def get_collections(
    limit: int = Query(default=10, le=100),
    db: Session = Depends(get_db),
):
    """Get recent collection history."""
    service = DigestService(db)
    collections = service.get_recent_collections(limit=limit)
    return {"collections": [c.to_dict() for c in collections]}


@router.get("/collections/{collection_id}/status")
async def get_collection_status(
    collection_id: int,
    db: Session = Depends(get_db),
):
    """Get status of a specific collection."""
    service = DigestService(db)
    collection = service.get_collection_status(collection_id)
    if not collection:
        return {"error": "Collection not found"}, 404
    return collection.to_dict()


@router.get("/stats/today")
async def get_today_stats(db: Session = Depends(get_db)):
    """Get today's collection statistics."""
    service = DigestService(db)
    return service.get_today_stats()
