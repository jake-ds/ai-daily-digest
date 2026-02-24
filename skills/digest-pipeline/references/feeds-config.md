# feeds.yaml 설정 가이드

## 파일 위치

`data/feeds.yaml`

## 구조

```yaml
feeds:
  - name: "피드 이름"
    url: "https://example.com/rss"
    category: "bigtech"
    priority: 1              # 1(높음) ~ 3(낮음)
    language: "en"           # en 또는 ko

keywords:
  high_priority:             # 가중치 +3
    - "artificial intelligence"
    - "large language model"
    - "GPT"
    - "Claude"
  medium_priority:           # 가중치 +2
    - "machine learning"
    - "neural network"
    - "transformer"
  low_priority:              # 가중치 +1
    - "automation"
    - "robotics"
```

## 카테고리 설명

| 카테고리 | 설명 | 피드 예시 |
|----------|------|-----------|
| bigtech | 빅테크 공식 블로그 | Google AI Blog, OpenAI Blog, Meta AI |
| vc | 벤처/투자 관련 | a16z, Sequoia, First Round |
| news | AI/Tech 뉴스 | TechCrunch, The Verge, Ars Technica |
| research | 논문/연구 | arXiv AI, Papers With Code |
| community | 개발자 커뮤니티 | Hacker News (별도 collector) |
| korean | 한국어 소스 | 한국 AI 관련 블로그/뉴스 |

## Priority 설명

| 값 | 의미 | 스코어 영향 |
|----|------|------------|
| 1 | 핵심 소스 (놓치면 안 됨) | +3점 |
| 2 | 중요 소스 | +1점 |
| 3 | 보조 소스 | 0점 |

## 키워드 스코어링

기사 제목/요약에서 키워드 매칭:
- `high_priority` 키워드 매치: +3점
- `medium_priority` 키워드 매치: +2점
- `low_priority` 키워드 매치: +1점

최종 score = 소스 priority 점수 + 키워드 점수

## 피드 추가 체크리스트

1. RSS URL이 유효한지 확인 (직접 접속)
2. 카테고리 분류
3. priority 설정 (처음에는 2로 시작, 관찰 후 조정)
4. language 설정
5. `python main.py --hours 24`로 수집 테스트
6. 중복이 많으면 dedup이 처리하므로 걱정 불필요

## YouTube 채널 설정

별도 파일: `data/youtube_channels.yaml`

```yaml
channels:
  - name: "채널명"
    channel_id: "UC..."
    category: "media"
```
