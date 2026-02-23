"""AI evaluation service for articles using Claude Haiku."""

import json
from typing import Optional

from anthropic import Anthropic
from sqlalchemy.orm import Session

from web.models import Article
from web.config import ANTHROPIC_API_KEY
from src.processors.evaluator import ArticleEvaluator


class EvaluationService:
    """웹용 AI 평가 서비스 — 배치/단건 평가, DB 저장"""

    MODEL = "claude-haiku-4-5-20251001"

    def __init__(self, db: Session):
        self.db = db
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
        self.evaluator = ArticleEvaluator()

    def evaluate_article(self, article: Article, force: bool = False) -> Optional[dict]:
        """단건 AI 평가 → DB 저장, 결과 반환"""
        if not self.client:
            return None

        if article.ai_score is not None and not force:
            return json.loads(article.eval_data) if article.eval_data else None

        raw = self._call_evaluator(article)
        if not raw:
            return None

        ai_score, linkedin_potential = ArticleEvaluator.calculate_scores(raw)

        article.ai_score = ai_score
        article.linkedin_potential = linkedin_potential
        article.eval_data = json.dumps(raw, ensure_ascii=False)
        self.db.commit()

        return raw

    def batch_evaluate(self, limit: int = 50, force: bool = False) -> dict:
        """미평가 기사 배치 평가

        Args:
            limit: 최대 처리 개수
            force: True면 전체 재평가, False면 ai_score IS NULL만

        Returns:
            {processed, remaining, total}
        """
        if not self.client:
            return {"processed": 0, "remaining": 0, "total": 0, "error": "ANTHROPIC_API_KEY not configured"}

        if force:
            articles = (
                self.db.query(Article)
                .order_by(Article.collected_at.desc())
                .limit(limit)
                .all()
            )
        else:
            articles = (
                self.db.query(Article)
                .filter(Article.ai_score == None)
                .order_by(Article.collected_at.desc())
                .limit(limit)
                .all()
            )

        processed = 0
        for article in articles:
            raw = self._call_evaluator(article)
            if raw:
                ai_score, linkedin_potential = ArticleEvaluator.calculate_scores(raw)
                article.ai_score = ai_score
                article.linkedin_potential = linkedin_potential
                article.eval_data = json.dumps(raw, ensure_ascii=False)
                processed += 1

        self.db.commit()

        remaining = (
            self.db.query(Article)
            .filter(Article.ai_score == None)
            .count()
        )
        total = self.db.query(Article).count()

        return {
            "processed": processed,
            "remaining": remaining,
            "total": total,
        }

    def _call_evaluator(self, article: Article) -> Optional[dict]:
        """Claude Haiku 호출 → 7차원 + key_insight + hook_suggestion"""
        prompt = ArticleEvaluator.EVALUATION_PROMPT.format(
            title=article.title,
            source=article.source or "",
            category=article.category or "",
            summary=article.ai_summary or article.summary or "요약 없음"
        )

        try:
            response = self.client.messages.create(
                model=self.MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            result_text = response.content[0].text.strip()

            # JSON 파싱
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            return json.loads(result_text.strip())

        except Exception as e:
            print(f"[EvalService] 평가 실패 [{article.title[:30]}]: {e}")
            return None
