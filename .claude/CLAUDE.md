# AI Daily Digest

## Project Overview

AI Daily Digest는 글로벌 AI/Tech/VC 뉴스를 자동 수집하고, Claude를 활용해 요약·분석·개인화하는 파이프라인 시스템이다. 매일 자동으로 실행되어 Notion, Obsidian, 이메일, 웹 대시보드로 결과를 전달한다.

## Tech Stack

- **Language**: Python 3.11+
- **AI**: Anthropic Claude API (claude-sonnet-4-20250514)
- **Web**: FastAPI + Jinja2 + HTMX + SQLAlchemy
- **DB**: SQLite (web dashboard), Notion API (output)
- **Automation**: GitHub Actions (daily cron), schedule (hourly worker)
- **Data Sources**: RSS, Hacker News, YouTube, Gmail, Reddit, GitHub Trending, Product Hunt, Twitter

## Architecture

```
main.py                      # RSS/HN/YouTube 수집 → 요약 → Markdown/Notion 출력
personal_digest_worker.py    # Gmail/바이럴 수집 → 개인화 → Obsidian/Email 출력
run_web.py                   # FastAPI 웹 대시보드 (포트 8001)
linkedin_worker.py           # LinkedIn 포스트 생성

src/
  collectors/                # 데이터 수집 모듈
    rss_collector.py         # RSS 피드 파서 (Article 데이터클래스 정의)
    hn_collector.py          # Hacker News API
    youtube_collector.py     # YouTube Data API v3
    youtube_transcript.py    # YouTube 트랜스크립트 추출
    gmail_collector.py       # Gmail API (OAuth2)
    reddit_collector.py      # Reddit JSON API
    github_trending.py       # GitHub Trending 스크래핑
    producthunt_collector.py # Product Hunt API/스크래핑
    twitter_collector.py     # Twitter API v2
    viral_aggregator.py      # 크로스 플랫폼 바이럴 탐지

  processors/                # 데이터 처리 모듈
    dedup.py                 # URL 기반 중복 제거 (히스토리 관리)
    scorer.py                # 키워드/소스 기반 점수 부여
    summarizer.py            # Claude 기반 AI 요약
    evaluator.py             # 기사 평가
    content_parser.py        # 이메일 본문 파싱 (URL/YouTube/이미지 추출)
    image_analyzer.py        # 이미지 분석 (Claude Vision)
    personalization.py       # Obsidian 기반 개인화 분석
    viral_detector.py        # 바이럴 점수 계산
    linkedin_writer.py       # LinkedIn 포스트 작성
    linkedin_generator.py    # LinkedIn 시나리오 기반 생성
    linkedin_expert.py       # LinkedIn 전문가 톤 생성

  outputs/                   # 출력 모듈
    markdown_output.py       # Markdown 파일 저장
    notion_output.py         # Notion API 페이지 생성
    obsidian_output.py       # Obsidian vault 노트 저장
    email_sender.py          # SMTP 이메일 발송

web/                         # FastAPI 웹 대시보드
  app.py                     # FastAPI 앱 (라우터, 템플릿)
  database.py                # SQLAlchemy 설정
  config.py                  # 환경변수 기반 설정
  models/                    # DB 모델 (Article, LinkedInDraft, Collection)
  services/                  # 비즈니스 로직
  api/                       # API 엔드포인트
  templates/                 # Jinja2 HTML 템플릿 (HTMX)

data/
  feeds.yaml                 # RSS 피드 목록 및 키워드 설정
  youtube_channels.yaml      # YouTube 채널 목록
  dedup_history.json         # 중복 제거 히스토리
```

## Commands

```bash
# 뉴스 수집 파이프라인 (RSS + HN + YouTube → 요약 → Markdown)
python main.py --hours 48 --top 20

# Notion에도 저장
python main.py --hours 24 --notion

# 개인 다이제스트 워커 (Gmail + 바이럴 → Obsidian)
python personal_digest_worker.py --once --hours 48

# 바이럴만 수집
python personal_digest_worker.py --viral-only

# 스케줄러 모드 (매시간 Gmail, 매3시간 바이럴, 매일 5시 이메일)
python personal_digest_worker.py

# 웹 대시보드
python run_web.py  # http://localhost:8001

# 의존성 설치
pip install -r requirements.txt

# 문법 검사
python -m py_compile main.py
python -m py_compile personal_digest_worker.py
```

## Code Conventions

- **언어**: 코드는 영어, 주석/문서/로그는 한국어
- **데이터 클래스**: `@dataclass`로 정의 (Article, EmailContent, ViralContent 등)
- **에러 처리**: 컴포넌트별 try/except로 부분 실패 허용 (하나가 실패해도 나머지 계속)
- **환경변수**: `.env` 파일로 관리, 없으면 graceful skip
- **출력**: `print(f"[Module] 메시지")` 형식으로 구조화된 로그
- **파일 구조**: collector → processor → output 파이프라인 패턴
- **타입**: `Optional`, `list[]` 등 타입 힌트 적극 사용
- **새 collector 추가 시**: `src/collectors/`에 클래스 생성 → `__init__.py`에 export → `main.py`에서 호출

## Data Flow

```
[Sources] → [Collectors] → [Dedup] → [Score] → [Enrich] → [Summarize] → [Output]
  RSS          rss_collector    dedup     scorer   arxiv      summarizer   markdown
  HN           hn_collector                                                notion
  YouTube      youtube_collector                                           obsidian
  Gmail        gmail_collector                                             email
  Reddit       reddit_collector                                            web dashboard
  GitHub       github_trending
  ProductHunt  producthunt_collector
  Twitter      twitter_collector
```

## Key Patterns

1. **Article 데이터클래스** (`src/collectors/rss_collector.py`): 모든 collector가 이 형식으로 반환
2. **Graceful Degradation**: API 키 없으면 해당 소스 skip, 요약 실패해도 제목만으로 진행
3. **중복 제거**: URL 정규화 + 히스토리 파일로 같은 기사 중복 방지
4. **개인화**: Obsidian vault의 기존 노트를 context로 활용해 관련성 분석

## Important Files

- `.env` - 모든 API 키 (절대 커밋 금지)
- `.env.example` - 환경변수 템플릿
- `data/feeds.yaml` - RSS 소스 설정 (카테고리, 우선순위, 키워드)
- `data/dedup_history.json` - 중복 제거 히스토리 (자동 생성)
- `output/` - 일일 다이제스트 마크다운 파일들

## Adding New Data Sources

새로운 collector를 추가할 때:
1. `src/collectors/new_source.py` 생성
2. `collect()` 메서드에서 `list[Article]` 반환
3. `src/collectors/__init__.py`에 import 추가
4. `main.py`의 수집 단계에서 호출
5. 필요 시 `.env.example`에 API 키 추가
