# AI Daily Digest

글로벌 AI/Tech/VC 뉴스를 자동 수집하고, Claude를 활용해 요약·분석·개인화하는 파이프라인 시스템. 매일 자동으로 실행되어 Notion, Obsidian, 이메일, 웹 대시보드로 결과를 전달한다.

## Tech Stack

- **Language**: Python 3.11+
- **AI**: Anthropic Claude API (claude-sonnet-4-20250514)
- **Web**: FastAPI + Jinja2 + HTMX + SQLAlchemy
- **DB**: SQLite (web dashboard), Notion API (output)
- **Automation**: GitHub Actions (daily cron), schedule (hourly worker)

## Data Sources

RSS, Hacker News, YouTube, Gmail, Reddit, GitHub Trending, Product Hunt, Twitter

## Quick Start

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 웹 대시보드 실행
python run_web.py  # http://localhost:8001
```

## Usage

```bash
# 뉴스 수집 파이프라인 (RSS + HN + YouTube → 요약 → Markdown)
python main.py --hours 48 --top 20

# Notion에도 저장
python main.py --hours 24 --notion

# 개인 다이제스트 워커 (Gmail + 바이럴 → Obsidian)
python personal_digest_worker.py --once --hours 48

# 스케줄러 모드 (매시간 Gmail, 매3시간 바이럴, 매일 5시 이메일)
python personal_digest_worker.py
```

## Architecture

```
[Sources] → [Collectors] → [Dedup] → [Score] → [Summarize] → [Output]
```

```
main.py                      # 뉴스 수집 → 요약 → Markdown/Notion
personal_digest_worker.py    # Gmail/바이럴 → Obsidian/Email
run_web.py                   # FastAPI 웹 대시보드
linkedin_worker.py           # LinkedIn 포스트 생성

src/
  collectors/                # 데이터 수집 (RSS, HN, YouTube, Gmail, Reddit 등)
  processors/                # 처리 (중복제거, 점수, 요약, 개인화)
  outputs/                   # 출력 (Markdown, Notion, Obsidian, Email)

web/                         # FastAPI 웹 대시보드
  app.py                     # 앱 & 라우터
  models/                    # DB 모델 (Article, LinkedInDraft, ReferencePost)
  services/                  # 비즈니스 로직 (LinkedIn Agent, Guidelines Learner)
  api/                       # REST API 엔드포인트
  templates/                 # Jinja2 + HTMX 템플릿
```

## Web Dashboard Features

- **Articles**: 수집된 기사 검색, 필터링, 즐겨찾기
- **LinkedIn Agent Mode**: 6단계 AI 에이전트가 실시간으로 LinkedIn 포스트 생성 (분석 → 방향 설정 → 가이드라인 검토 → 초안 → 자기 검토 → 평가)
- **Posts**: 완성된 LinkedIn 포스팅 모아보기, 발행 상태 관리
- **Guidelines Learning**: 레퍼런스 포스팅 분석 → AI가 지침서 업데이트 제안
- **Settings**: LinkedIn 지침서 편집, 수집 스케줄 관리

## Environment Variables

`.env.example`을 참고하여 `.env` 파일을 생성하세요.

| 변수 | 필수 | 설명 |
|------|------|------|
| `ANTHROPIC_API_KEY` | Yes | Claude API 키 |
| `NOTION_API_KEY` | No | Notion 출력 시 필요 |
| `NOTION_DATABASE_ID` | No | Notion 데이터베이스 ID |
| `GOOGLE_CREDENTIALS_PATH` | No | Gmail 수집 시 필요 |
| `YOUTUBE_API_KEY` | No | YouTube 수집 시 필요 |

## License

Private
