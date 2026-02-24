---
name: digest-pipeline
description: AI Daily Digest 뉴스 수집/요약 파이프라인 운영 스킬. 새 데이터 소스 추가, 수집 문제 디버깅, 출력 포맷 커스터마이징, 파이프라인 구조 이해에 사용한다. 파이프라인, 수집, collector, 데이터 소스, RSS, 다이제스트, 요약 등의 작업에 사용한다.
---

# Digest Pipeline

AI Daily Digest의 뉴스 수집 → 처리 → 출력 파이프라인 운영 가이드.

## 아키텍처

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

## 핵심 파이프라인 패턴

### Collector → Processor → Output

각 단계가 독립적. collector 하나가 실패해도 나머지는 계속 실행.

### Article 데이터클래스

모든 collector가 반환하는 표준 데이터 형식 (`src/collectors/rss_collector.py`에 정의):

```python
@dataclass
class Article:
    title: str
    url: str
    summary: str
    source: str
    category: str
    published: datetime
    score: float = 0.0
    ai_summary: str = ""
    authors: str = ""
    # ... (추가 필드)
```

## 실행 명령

```bash
# 뉴스 수집 (RSS + HN + YouTube → 요약 → Markdown)
python main.py --hours 48 --top 20

# Notion에도 저장
python main.py --hours 24 --notion

# 개인 다이제스트 (Gmail + 바이럴 → Obsidian)
python personal_digest_worker.py --once --hours 48

# 웹 대시보드
python run_web.py  # http://localhost:8001
```

## 새 데이터 소스 추가

collector 추가 패턴은 [references/collector-patterns.md](references/collector-patterns.md) 참조.

1. `src/collectors/{name}_collector.py` 생성
2. `collect(hours: int) -> list[Article]` 메서드 구현
3. `src/collectors/__init__.py`에 import 추가
4. `main.py`의 수집 단계에서 호출
5. `.env.example`에 API 키 추가 (필요 시)

## 출력 포맷

각 출력 포맷의 스펙은 [references/output-formats.md](references/output-formats.md) 참조.

| 포맷 | 모듈 | 트리거 |
|------|------|--------|
| Markdown | `markdown_output.py` | main.py |
| Notion DB | `notion_output.py` | main.py --notion |
| Obsidian Vault | `obsidian_output.py` | personal_digest_worker.py |
| Email | `email_sender.py` | personal_digest_worker.py (5am) |
| Web Dashboard | `web/app.py` | run_web.py |

## 피드 설정

feeds.yaml 설정 가이드는 [references/feeds-config.md](references/feeds-config.md) 참조.

## 에러 처리 원칙

1. **부분 실패 허용**: 한 collector가 실패해도 나머지 계속
2. **API 키 없으면 skip**: graceful degradation
3. **rate limit 존중**: 외부 API 호출 시
4. **히스토리 보존**: dedup_history.json 자동 관리

## 모델 사용

| 단계 | 모델 | 용도 |
|------|------|------|
| 기사 요약 | Haiku | 1-2문장 한글 요약 |
| 연구 논문 요약 | Haiku | 요약 + 기관 추출 |
| 기사 평가 | Haiku | 7차원 스코어링 |
| 이미지 분석 | Sonnet | Vision API |
| 개인화 분석 | Sonnet | Obsidian 맥락 분석 |
