"""Obsidian 기반 개인화 모듈"""

import os
import re
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter

import anthropic
from dotenv import load_dotenv

load_dotenv()


@dataclass
class UserProfile:
    """사용자 프로필 (관심사, 프로젝트 등)"""
    interests: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    frequent_tags: list[str] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    folder_structure: dict = field(default_factory=dict)


@dataclass
class PersonalizedAnalysis:
    """개인화된 분석 결과"""
    relevance_score: float  # 0-1
    related_interests: list[str]
    related_projects: list[str]
    suggested_tags: list[str]
    personalized_summary: str
    suggested_folder: Optional[str] = None


class ObsidianPersonalizer:
    """Obsidian 볼트 기반 개인화 분석"""

    def __init__(
        self,
        vault_path: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.vault_path = Path(vault_path or os.getenv("OBSIDIAN_VAULT_PATH", ""))
        if not self.vault_path.exists():
            raise ValueError(f"Obsidian 볼트를 찾을 수 없습니다: {self.vault_path}")

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else None

        self._profile: Optional[UserProfile] = None

    def scan_vault(self, max_files: int = 500) -> UserProfile:
        """볼트 스캔하여 사용자 프로필 구축"""
        tags = Counter()
        folders = {}
        recent_titles = []

        # 마크다운 파일 스캔
        md_files = list(self.vault_path.rglob("*.md"))[:max_files]

        # 최근 수정 파일 우선
        md_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        recent_cutoff = datetime.now() - timedelta(days=30)

        for file_path in md_files:
            try:
                # 폴더 구조 수집
                relative_path = file_path.relative_to(self.vault_path)
                folder = str(relative_path.parent)
                if folder not in folders:
                    folders[folder] = 0
                folders[folder] += 1

                # 파일 내용 분석
                content = file_path.read_text(encoding="utf-8", errors="ignore")

                # 태그 추출 (#태그 형식)
                found_tags = re.findall(r"#([a-zA-Z가-힣0-9_-]+)", content)
                tags.update(found_tags)

                # YAML frontmatter에서 태그 추출
                yaml_tags = self._extract_yaml_tags(content)
                tags.update(yaml_tags)

                # 최근 파일 제목 수집
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if mtime > recent_cutoff:
                    recent_titles.append(file_path.stem)

            except Exception as e:
                continue

        # 프로필 구성
        frequent_tags = [tag for tag, count in tags.most_common(50)]

        # 관심사 추출 (태그 기반)
        interests = self._extract_interests(frequent_tags)

        # 프로젝트 추출 (폴더 기반)
        projects = self._extract_projects(folders)

        # 최근 토픽 추출
        recent_topics = recent_titles[:20]

        self._profile = UserProfile(
            interests=interests,
            projects=projects,
            frequent_tags=frequent_tags,
            recent_topics=recent_topics,
            folder_structure=folders
        )

        return self._profile

    def _extract_yaml_tags(self, content: str) -> list[str]:
        """YAML frontmatter에서 태그 추출"""
        tags = []

        # YAML frontmatter 추출
        if content.startswith("---"):
            try:
                end_idx = content.index("---", 3)
                yaml_content = content[3:end_idx]
                data = yaml.safe_load(yaml_content)

                if data and "tags" in data:
                    yaml_tags = data["tags"]
                    if isinstance(yaml_tags, list):
                        tags.extend(yaml_tags)
                    elif isinstance(yaml_tags, str):
                        tags.append(yaml_tags)
            except Exception:
                pass

        return tags

    def _extract_interests(self, tags: list[str]) -> list[str]:
        """태그에서 관심사 추출"""
        # 일반적인 메타 태그 제외
        exclude_tags = {
            "todo", "done", "inbox", "archive", "draft",
            "daily", "weekly", "monthly", "yearly",
            "meeting", "note", "idea", "project"
        }

        interests = []
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower not in exclude_tags and len(tag) > 1:
                interests.append(tag)
                if len(interests) >= 20:
                    break

        return interests

    def _extract_projects(self, folders: dict) -> list[str]:
        """폴더 구조에서 프로젝트 추출"""
        # Projects, 프로젝트 등의 폴더 하위 항목 추출
        project_folders = []

        for folder, count in folders.items():
            parts = Path(folder).parts
            if len(parts) >= 2:
                # Projects/XXX 형태
                if parts[0].lower() in ["projects", "프로젝트", "project"]:
                    project_folders.append(parts[1])

        return list(set(project_folders))[:10]

    def get_profile(self) -> UserProfile:
        """현재 프로필 반환 (없으면 스캔)"""
        if self._profile is None:
            self.scan_vault()
        return self._profile

    def analyze_content(
        self,
        title: str,
        content: str,
        content_type: str = "article"
    ) -> PersonalizedAnalysis:
        """콘텐츠를 사용자 프로필과 비교 분석"""
        profile = self.get_profile()

        if not self.client:
            # API 없이 간단 분석
            return self._simple_analysis(title, content, profile)

        # Claude를 사용한 상세 분석
        return self._ai_analysis(title, content, content_type, profile)

    def _simple_analysis(
        self,
        title: str,
        content: str,
        profile: UserProfile
    ) -> PersonalizedAnalysis:
        """API 없이 키워드 매칭 기반 분석"""
        text = f"{title} {content}".lower()

        # 관심사 매칭
        related_interests = []
        for interest in profile.interests:
            if interest.lower() in text:
                related_interests.append(interest)

        # 프로젝트 매칭
        related_projects = []
        for project in profile.projects:
            if project.lower() in text:
                related_projects.append(project)

        # 태그 매칭
        suggested_tags = []
        for tag in profile.frequent_tags[:20]:
            if tag.lower() in text:
                suggested_tags.append(tag)

        # 관련도 점수 계산
        match_count = len(related_interests) + len(related_projects) + len(suggested_tags)
        relevance_score = min(1.0, match_count / 10)

        return PersonalizedAnalysis(
            relevance_score=relevance_score,
            related_interests=related_interests[:5],
            related_projects=related_projects[:3],
            suggested_tags=suggested_tags[:5],
            personalized_summary="",
            suggested_folder=self._suggest_folder(related_interests, related_projects, profile)
        )

    def _ai_analysis(
        self,
        title: str,
        content: str,
        content_type: str,
        profile: UserProfile
    ) -> PersonalizedAnalysis:
        """Claude를 사용한 상세 분석"""
        # 콘텐츠 요약 (너무 길면 자르기)
        content_preview = content[:3000] if content else ""

        prompt = f"""다음 콘텐츠를 사용자의 관심사와 프로젝트를 기준으로 분석해주세요.

## 사용자 프로필
- 관심사: {', '.join(profile.interests[:15])}
- 프로젝트: {', '.join(profile.projects)}
- 자주 사용하는 태그: {', '.join(profile.frequent_tags[:20])}

## 분석할 콘텐츠
- 제목: {title}
- 유형: {content_type}
- 내용: {content_preview}

## 요청 사항
JSON 형식으로 응답해주세요:
{{
  "relevance_score": 0.0-1.0 (사용자와의 관련도),
  "related_interests": ["관련 관심사 목록"],
  "related_projects": ["관련 프로젝트 목록"],
  "suggested_tags": ["추천 태그 5개"],
  "personalized_summary": "이 사용자에게 특화된 2-3문장 요약. 왜 이 콘텐츠가 관심을 가질만한지 설명",
  "suggested_folder": "저장 추천 폴더명"
}}"""

        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text

            # JSON 파싱
            import json
            json_match = response_text
            if "```json" in response_text:
                json_match = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                json_match = response_text.split("```")[1].split("```")[0]

            result = json.loads(json_match.strip())

            return PersonalizedAnalysis(
                relevance_score=float(result.get("relevance_score", 0.5)),
                related_interests=result.get("related_interests", []),
                related_projects=result.get("related_projects", []),
                suggested_tags=result.get("suggested_tags", []),
                personalized_summary=result.get("personalized_summary", ""),
                suggested_folder=result.get("suggested_folder")
            )

        except Exception as e:
            print(f"[개인화] AI 분석 실패: {e}")
            return self._simple_analysis(title, content, profile)

    def _suggest_folder(
        self,
        interests: list[str],
        projects: list[str],
        profile: UserProfile
    ) -> Optional[str]:
        """저장할 폴더 추천"""
        # 프로젝트 관련이면 해당 프로젝트 폴더
        if projects:
            return f"Projects/{projects[0]}"

        # 관심사 기반 폴더 찾기
        for interest in interests:
            for folder in profile.folder_structure:
                if interest.lower() in folder.lower():
                    return folder

        # 기본 Inbox 폴더
        return "Inbox/AI-Digest"


if __name__ == "__main__":
    # 테스트
    vault_path = os.getenv("OBSIDIAN_VAULT_PATH")
    if vault_path:
        personalizer = ObsidianPersonalizer(vault_path)
        profile = personalizer.scan_vault()

        print("=== 사용자 프로필 ===")
        print(f"관심사: {profile.interests[:10]}")
        print(f"프로젝트: {profile.projects}")
        print(f"빈출 태그: {profile.frequent_tags[:10]}")
        print(f"최근 토픽: {profile.recent_topics[:5]}")

        # 테스트 분석
        analysis = personalizer.analyze_content(
            title="OpenAI GPT-5 발표",
            content="OpenAI가 새로운 GPT-5 모델을 발표했습니다. 이 모델은 멀티모달 기능이 강화되었습니다.",
            content_type="article"
        )
        print("\n=== 분석 결과 ===")
        print(f"관련도: {analysis.relevance_score}")
        print(f"관련 관심사: {analysis.related_interests}")
        print(f"추천 태그: {analysis.suggested_tags}")
    else:
        print("OBSIDIAN_VAULT_PATH 환경변수를 설정하세요.")
