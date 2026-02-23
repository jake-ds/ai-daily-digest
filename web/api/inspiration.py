"""Inspiration Library API endpoints for managing reference posts and style profiles."""

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from web.database import get_db
from web.models import ReferencePost

router = APIRouter(prefix="/api/inspiration", tags=["inspiration"])


# --- Request models ---

class InspirationPostCreate(BaseModel):
    content: str = Field(..., min_length=10)
    author: Optional[str] = None
    source_url: Optional[str] = None
    scenario: Optional[str] = Field(default=None, pattern="^[A-F]$")
    tags: Optional[list[str]] = None


class InspirationPostUpdate(BaseModel):
    scenario: Optional[str] = Field(default=None, pattern="^[A-F]$")
    tags: Optional[list[str]] = None
    author: Optional[str] = None


class FetchUrlRequest(BaseModel):
    url: str = Field(..., min_length=5)


class LearnFeedback(BaseModel):
    feedback: str = ""
    is_positive: bool = True


class StyleProfileRebuild(BaseModel):
    pass


# --- Inspiration post endpoints ---

@router.post("/posts")
async def create_inspiration_post(
    data: InspirationPostCreate,
    db: Session = Depends(get_db),
):
    """글 추가 + 자동 AI 분석 + 태그."""
    from web.services.guidelines_learner import GuidelinesLearner

    learner = GuidelinesLearner(db)

    try:
        # AI 분석
        analysis = learner.analyze_post(data.content)

        # 태그 직렬화
        tags_json = json.dumps(data.tags, ensure_ascii=False) if data.tags else None

        # DB 저장
        post = ReferencePost(
            content=data.content,
            author=data.author,
            source_url=data.source_url,
            analysis=json.dumps(analysis, ensure_ascii=False) if analysis else None,
            scenario=data.scenario,
            tags=tags_json,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        return {
            "success": True,
            "post": post.to_dict(),
            "analysis": analysis,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 실패: {str(e)}")


@router.get("/posts")
async def list_inspiration_posts(
    scenario: Optional[str] = None,
    tag: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
    db: Session = Depends(get_db),
):
    """목록 조회 (scenario, tag, q 필터, 페이지네이션)."""
    query = db.query(ReferencePost)

    if scenario:
        query = query.filter(ReferencePost.scenario == scenario)

    if tag:
        # JSON 배열 내 태그 검색 (SQLite LIKE)
        query = query.filter(ReferencePost.tags.like(f'%"{tag}"%'))

    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            ReferencePost.content.ilike(search_pattern)
            | ReferencePost.author.ilike(search_pattern)
        )

    total = query.count()
    posts = (
        query.order_by(ReferencePost.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "posts": [p.to_dict() for p in posts],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page if total > 0 else 1,
    }


@router.get("/posts/{post_id}")
async def get_inspiration_post(
    post_id: int,
    db: Session = Depends(get_db),
):
    """상세 조회 (분석 포함)."""
    post = db.query(ReferencePost).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    result = post.to_dict()
    # analysis를 파싱된 JSON으로 제공
    if post.analysis:
        try:
            result["analysis_parsed"] = json.loads(post.analysis)
        except json.JSONDecodeError:
            result["analysis_parsed"] = None

    return {"post": result}


@router.patch("/posts/{post_id}")
async def update_inspiration_post(
    post_id: int,
    data: InspirationPostUpdate,
    db: Session = Depends(get_db),
):
    """태그/시나리오/저자 수정."""
    post = db.query(ReferencePost).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if data.scenario is not None:
        post.scenario = data.scenario
    if data.tags is not None:
        post.tags = json.dumps(data.tags, ensure_ascii=False)
    if data.author is not None:
        post.author = data.author

    db.commit()
    return {"success": True, "post": post.to_dict()}


@router.delete("/posts/{post_id}")
async def delete_inspiration_post(
    post_id: int,
    db: Session = Depends(get_db),
):
    """삭제."""
    post = db.query(ReferencePost).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    db.delete(post)
    db.commit()
    return {"success": True}


@router.get("/tags")
async def list_tags(db: Session = Depends(get_db)):
    """전체 태그 목록 + 사용 횟수."""
    posts = db.query(ReferencePost).filter(ReferencePost.tags != None).all()

    tag_counts: dict[str, int] = {}
    for post in posts:
        try:
            tags = json.loads(post.tags) if post.tags else []
            for tag in tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except json.JSONDecodeError:
            continue

    # 사용 횟수 내림차순 정렬
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)

    return {
        "tags": [{"name": name, "count": count} for name, count in sorted_tags],
    }


@router.post("/posts/{post_id}/reanalyze")
async def reanalyze_inspiration_post(
    post_id: int,
    db: Session = Depends(get_db),
):
    """AI 재분석."""
    post = db.query(ReferencePost).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    from web.services.guidelines_learner import GuidelinesLearner

    learner = GuidelinesLearner(db)

    try:
        analysis = learner.analyze_post(post.content)
        post.analysis = json.dumps(analysis, ensure_ascii=False)
        db.commit()

        return {
            "success": True,
            "analysis": analysis,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"재분석 실패: {str(e)}")


@router.post("/posts/{post_id}/learn")
async def learn_from_post(
    post_id: int,
    db: Session = Depends(get_db),
):
    """이 글에서 지침 업데이트 제안 생성."""
    post = db.query(ReferencePost).filter(ReferencePost.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    from web.services.guidelines_learner import GuidelinesLearner

    learner = GuidelinesLearner(db)

    try:
        # 분석이 없으면 먼저 분석
        if post.analysis:
            try:
                analysis = json.loads(post.analysis)
            except json.JSONDecodeError:
                analysis = learner.analyze_post(post.content)
                post.analysis = json.dumps(analysis, ensure_ascii=False)
                db.commit()
        else:
            analysis = learner.analyze_post(post.content)
            post.analysis = json.dumps(analysis, ensure_ascii=False)
            db.commit()

        # 지침 업데이트 제안 생성
        suggestions = learner.suggest_updates(analysis)

        # StyleProfile도 업데이트
        try:
            from web.services.style_analyzer import StyleAnalyzer
            analyzer = StyleAnalyzer(db)
            analyzer.update_from_post(post.content)
        except Exception:
            pass  # StyleProfile 업데이트 실패가 학습을 막으면 안 됨

        return {
            "success": True,
            "suggestions": suggestions,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"학습 실패: {str(e)}")


@router.post("/posts/fetch-url")
async def fetch_url_content(data: FetchUrlRequest):
    """URL → 본문 크롤링 시도."""
    from web.services.source_fetcher import fetch

    try:
        content = fetch(data.url)
        if content:
            return {
                "success": True,
                "content": content,
                "url": data.url,
            }
        else:
            return {
                "success": False,
                "message": "본문을 추출할 수 없습니다. 직접 입력해주세요.",
                "url": data.url,
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"크롤링 실패: {str(e)}",
            "url": data.url,
        }


# --- Style Profile endpoints ---

@router.post("/style-profile/rebuild")
async def rebuild_style_profile(db: Session = Depends(get_db)):
    """스타일 프로필 전체 재빌드."""
    from web.services.style_analyzer import StyleAnalyzer

    analyzer = StyleAnalyzer(db)

    try:
        result = analyzer.build_profile()
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, "profile": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"프로필 빌드 실패: {str(e)}")


@router.get("/style-profile")
async def get_style_profile(db: Session = Depends(get_db)):
    """현재 스타일 프로필 조회."""
    from web.services.style_analyzer import StyleAnalyzer

    analyzer = StyleAnalyzer(db)
    profile = analyzer.get_current_profile()

    if not profile:
        return {
            "profile": None,
            "message": "스타일 프로필이 없습니다. 레퍼런스 추가 후 빌드하세요.",
        }

    return {"profile": profile}
