"""중복 제거 모듈"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..collectors.rss_collector import Article


class Deduplicator:
    """URL 및 제목 기반 중복 제거"""

    def __init__(self, history_path: str = "data/history.json"):
        self.history_path = Path(history_path)
        self.history = self._load_history()

    def _load_history(self) -> dict:
        """히스토리 파일 로드"""
        if self.history_path.exists():
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"seen_urls": [], "seen_hashes": []}

    def _save_history(self):
        """히스토리 파일 저장"""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def _get_title_hash(self, title: str) -> str:
        """제목 해시 생성 (유사 제목 감지용)"""
        normalized = title.lower().strip()
        words = sorted(normalized.split()[:5])
        return hashlib.md5(" ".join(words).encode()).hexdigest()[:16]

    def deduplicate(self, articles: list["Article"]) -> list["Article"]:
        """중복 기사 제거"""
        unique_articles = []
        seen_urls = set(self.history.get("seen_urls", []))
        seen_hashes = set(self.history.get("seen_hashes", []))

        session_urls = set()
        session_hashes = set()

        for article in articles:
            # URL 중복 체크
            if article.url in seen_urls or article.url in session_urls:
                continue

            # 제목 유사도 체크
            title_hash = self._get_title_hash(article.title)
            if title_hash in seen_hashes or title_hash in session_hashes:
                continue

            unique_articles.append(article)
            session_urls.add(article.url)
            session_hashes.add(title_hash)

        # 히스토리 업데이트 (최근 500개만 유지)
        all_urls = list(seen_urls | session_urls)[-500:]
        all_hashes = list(seen_hashes | session_hashes)[-500:]

        self.history["seen_urls"] = all_urls
        self.history["seen_hashes"] = all_hashes
        self.history["last_updated"] = datetime.now().isoformat()

        self._save_history()

        removed = len(articles) - len(unique_articles)
        print(f"중복 제거: {removed}개 제거됨 ({len(unique_articles)}개 유지)")

        return unique_articles

    def clear_history(self):
        """히스토리 초기화"""
        self.history = {"seen_urls": [], "seen_hashes": []}
        self._save_history()
        print("히스토리가 초기화되었습니다.")
