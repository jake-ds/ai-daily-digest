# 출력 포맷 스펙

## Markdown

**모듈**: `src/outputs/markdown_output.py`
**저장 위치**: `output/YYYY-MM-DD.md`

**구조**:
```markdown
# AI Daily Digest - YYYY-MM-DD

## Highlights
1. [기사 제목](URL) - 요약
2. ...
3. ...

## By Category

### BigTech
- [제목](URL) | 출처 | 요약

### Research
- [제목](URL) | 출처 | 요약

### News
- ...

## Media Content
- [YouTube 영상 제목](URL) | 채널명

## LinkedIn Post Draft
(자동 생성된 포스트 초안)
```

---

## Notion

**모듈**: `src/outputs/notion_output.py`
**API**: Notion API v1

**Collections DB 속성**:
- Title: 다이제스트 제목 (날짜 기반)
- Date: 생성일
- Articles: 기사 목록 (rich text)
- Highlights: 하이라이트 기사 (rich text)

**Articles DB 속성** (개별 기사 페이지):
- Title: 기사 제목
- URL: 원문 링크
- Source: 출처
- Category: 카테고리
- Score: 평가 점수
- AI Summary: AI 요약
- LinkedIn Status: 선택/미선택/작성중/완료

---

## Obsidian Vault

**모듈**: `src/outputs/obsidian_output.py`
**저장 위치**: 사용자 Obsidian vault 경로

**일일 노트 구조**:
```markdown
---
tags: [ai-digest, YYYY-MM-DD]
---

# AI Digest - YYYY-MM-DD

## Personalized Highlights
(Obsidian 기존 노트 기반 개인화)

## Articles
- [[관련 노트]] 연결
- 태그: #ai #tech #llm

## Viral Content
(크로스 플랫폼 바이럴 콘텐츠)
```

---

## Email

**모듈**: `src/outputs/email_sender.py`
**프로토콜**: SMTP

**HTML 템플릿**:
- 헤더: 날짜 + 기사 수
- 본문: 카테고리별 기사 목록
- LinkedIn 미리보기 (포스트 초안)
- 푸터: 구독 해지 링크

**발송 스케줄**: 매일 오전 5시

---

## Web Dashboard

**모듈**: `web/app.py` (FastAPI + Jinja2 + HTMX)
**포트**: 8000 또는 8001

**주요 페이지**:
- `/` — 기사 브라우저 (필터: 카테고리, 출처, 날짜)
- `/linkedin` — LinkedIn 초안 에디터
- `/linkedin/agent` — Agent 모드 (6단계 SSE 스트리밍)
- `/settings` — 설정 (피드, 스케줄)

## 새 출력 포맷 추가

1. `src/outputs/{name}_output.py` 생성
2. `save(articles)` 또는 동등한 메서드 구현
3. `src/outputs/__init__.py`에 export 추가
4. `main.py` 출력 단계에서 호출
