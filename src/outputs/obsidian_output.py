"""Obsidian 노트 출력 모듈"""

import os
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class DigestNote:
    """Obsidian에 저장할 노트"""
    title: str
    content: str
    source_url: Optional[str] = None
    source_type: str = "article"
    tags: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    personalized_note: Optional[str] = None
    related_interests: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


class ObsidianOutput:
    """Obsidian 볼트에 노트 저장"""

    def __init__(
        self,
        vault_path: Optional[str] = None,
        output_folder: str = "Inbox/AI-Digest"
    ):
        self.vault_path = Path(vault_path or os.getenv("OBSIDIAN_VAULT_PATH", ""))
        if not self.vault_path.exists():
            raise ValueError(f"Obsidian 볼트를 찾을 수 없습니다: {self.vault_path}")

        self.output_folder = output_folder
        self.output_path = self.vault_path / output_folder
        self.output_path.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, title: str, max_length: int = 100) -> str:
        """파일명으로 사용 가능하게 정리"""
        # 파일명에 사용할 수 없는 문자 제거
        sanitized = re.sub(r'[<>:"/\\|?*]', '', title)

        # 공백 정리
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()

        # 길이 제한
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rsplit(' ', 1)[0]

        return sanitized or "Untitled"

    def _generate_frontmatter(self, note: DigestNote) -> str:
        """YAML frontmatter 생성"""
        frontmatter = {
            "created": note.created_at.strftime("%Y-%m-%d %H:%M"),
            "source": note.source_url or "",
            "type": note.source_type,
            "tags": note.tags if note.tags else ["ai-digest"],
        }

        if note.related_interests:
            frontmatter["related"] = note.related_interests

        yaml_str = yaml.dump(
            frontmatter,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False
        )

        return f"---\n{yaml_str}---\n"

    def _generate_content(self, note: DigestNote) -> str:
        """노트 본문 생성"""
        lines = []

        # 제목
        lines.append(f"# {note.title}\n")

        # 메타 정보
        lines.append(f"> **출처**: {note.source_url or 'N/A'}")
        lines.append(f"> **유형**: {note.source_type}")
        lines.append(f"> **수집일**: {note.created_at.strftime('%Y-%m-%d %H:%M')}\n")

        # 개인화 노트 (있을 경우)
        if note.personalized_note:
            lines.append("## 나에게 중요한 이유\n")
            lines.append(f"{note.personalized_note}\n")

        # 요약
        if note.summary:
            lines.append("## 요약\n")
            lines.append(f"{note.summary}\n")

        # 본문
        lines.append("## 내용\n")
        lines.append(note.content)

        # 관련 관심사 태그
        if note.related_interests:
            lines.append("\n---")
            links = [f"[[{interest}]]" for interest in note.related_interests]
            lines.append(f"관련: {' '.join(links)}")

        return "\n".join(lines)

    def save_note(self, note: DigestNote) -> str:
        """노트를 파일로 저장"""
        # 파일명 생성
        date_prefix = note.created_at.strftime("%Y-%m-%d")
        safe_title = self._sanitize_filename(note.title)
        filename = f"{date_prefix}_{safe_title}.md"

        # 전체 내용 생성
        frontmatter = self._generate_frontmatter(note)
        content = self._generate_content(note)
        full_content = frontmatter + "\n" + content

        # 파일 저장
        file_path = self.output_path / filename

        # 같은 이름 파일이 있으면 번호 추가
        counter = 1
        original_path = file_path
        while file_path.exists():
            stem = original_path.stem
            file_path = original_path.parent / f"{stem}_{counter}.md"
            counter += 1

        file_path.write_text(full_content, encoding="utf-8")
        print(f"[Obsidian] 노트 저장: {file_path.relative_to(self.vault_path)}")

        return str(file_path)

    def save_daily_digest(
        self,
        notes: list[DigestNote],
        date: Optional[datetime] = None
    ) -> str:
        """일일 다이제스트 노트 저장"""
        if date is None:
            date = datetime.now()

        date_str = date.strftime("%Y-%m-%d")

        # 다이제스트 노트 생성
        lines = [f"# Daily Digest - {date_str}\n"]

        # 통계
        by_type = {}
        for note in notes:
            t = note.source_type
            by_type[t] = by_type.get(t, 0) + 1

        lines.append("## 오늘의 통계\n")
        for source_type, count in by_type.items():
            lines.append(f"- {source_type}: {count}개")
        lines.append("")

        # 콘텐츠 목록
        lines.append("## 수집된 콘텐츠\n")

        for note in notes:
            # 제목과 링크
            note_date = note.created_at.strftime("%Y-%m-%d")
            safe_title = self._sanitize_filename(note.title)
            note_link = f"[[{note_date}_{safe_title}]]"

            lines.append(f"### {note_link}")

            if note.summary:
                lines.append(f"> {note.summary[:200]}")

            if note.tags:
                tag_str = " ".join([f"#{tag}" for tag in note.tags[:5]])
                lines.append(f"태그: {tag_str}")

            lines.append("")

        # frontmatter
        frontmatter = {
            "created": date_str,
            "type": "daily-digest",
            "tags": ["ai-digest", "daily"],
            "count": len(notes)
        }

        yaml_str = yaml.dump(
            frontmatter,
            allow_unicode=True,
            default_flow_style=False
        )

        full_content = f"---\n{yaml_str}---\n\n" + "\n".join(lines)

        # 저장
        filename = f"Daily-Digest-{date_str}.md"
        file_path = self.output_path / filename

        file_path.write_text(full_content, encoding="utf-8")
        print(f"[Obsidian] 일일 다이제스트 저장: {file_path.relative_to(self.vault_path)}")

        return str(file_path)

    def save_to_folder(
        self,
        note: DigestNote,
        folder: str
    ) -> str:
        """특정 폴더에 노트 저장"""
        target_path = self.vault_path / folder
        target_path.mkdir(parents=True, exist_ok=True)

        # 임시로 output_path 변경
        original_output = self.output_path
        self.output_path = target_path

        result = self.save_note(note)

        self.output_path = original_output
        return result


if __name__ == "__main__":
    # 테스트
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")

    if vault_path:
        output = ObsidianOutput(vault_path)

        # 테스트 노트
        test_note = DigestNote(
            title="OpenAI GPT-5 발표 테스트",
            content="OpenAI가 새로운 GPT-5 모델을 발표했습니다.\n\n## 주요 특징\n- 멀티모달 기능 강화\n- 추론 능력 향상",
            source_url="https://example.com/gpt5",
            source_type="article",
            tags=["AI", "OpenAI", "GPT"],
            summary="OpenAI의 새로운 GPT-5 모델 발표 소식",
            personalized_note="AI 기술 발전에 관심 있는 나에게 중요한 소식",
            related_interests=["AI", "LLM", "OpenAI"]
        )

        saved_path = output.save_note(test_note)
        print(f"저장 완료: {saved_path}")
    else:
        print("OBSIDIAN_VAULT_PATH 환경변수를 설정하세요.")
