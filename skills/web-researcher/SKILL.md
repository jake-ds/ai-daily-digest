---
name: web-researcher
description: 기사 주제에 대한 웹 리서치를 수행하는 스킬. 제목/요약이 주어지면 검색 쿼리 생성 → 다중 소스 검색 → 핵심 콘텐츠 추출 → 구조화된 분석을 반환한다. 리서치, 배경 조사, 경쟁사 비교, 업계 맥락 조사, 추가 정보 수집 등의 작업에 사용한다.
---

# Web Researcher

기사 주제에 대한 배경지식, 경쟁사 비교, 업계 맥락을 조사하여 LinkedIn 포스트의 깊이를 높이는 스킬.

## 워크플로우

```
기사 제목/요약 → 쿼리 2개 생성 → Google CSE 검색 → 상위 3페이지 fetch → 구조화된 리서치 결과
```

### Step 1: 검색 쿼리 생성

Haiku 모델로 영어 검색 쿼리 2개 생성:
- **쿼리 1**: 배경 지식, 업계 맥락을 조사할 수 있는 쿼리
- **쿼리 2**: 경쟁사 비교, 대안 기술, 반론 등을 조사할 수 있는 쿼리

쿼리 전략 상세는 [references/query-strategies.md](references/query-strategies.md) 참조.

### Step 2: Google Custom Search

각 쿼리로 최대 5개 결과 검색. URL 기반 중복 제거 후 합산.

### Step 3: 페이지 콘텐츠 추출

상위 3페이지를 fetch하여 본문 추출:
- BeautifulSoup으로 HTML 파싱
- noise 제거 (nav, header, footer, sidebar, ads 등)
- 페이지당 최대 2,500자
- 총 리서치 결과 최대 6,000자

출처 신뢰도 판단 기준은 [references/source-reliability.md](references/source-reliability.md) 참조.

### Step 4: 결과 구조화

리서치 종합 패턴은 [references/synthesis-patterns.md](references/synthesis-patterns.md) 참조.

출력 형식:
```
## 리서치 결과

### 검색: "query 1"
### 검색: "query 2"

1. [제목] (URL)
   스니펫 요약

### 추출된 핵심 콘텐츠

**페이지 제목**:
추출된 본문 내용...
```

## 제약 사항

| 항목 | 값 |
|------|------|
| 전체 타임아웃 | 30초 |
| 페이지별 fetch 타임아웃 | 10초 |
| 페이지당 최대 글자 | 2,500자 |
| 총 리서치 최대 글자 | 6,000자 |
| 쿼리 수 | 2개 |
| fetch 페이지 수 | 3개 |

## 모델 사용

| 단계 | 모델 | 이유 |
|------|------|------|
| 쿼리 생성 | Haiku | 빠르고 저비용 |

## Graceful Degradation

- Google CSE API 키 없으면 리서치 건너뜀
- 검색 결과 없으면 None 반환
- 타임아웃 발생 시 그때까지의 결과 반환
- 개별 페이지 fetch 실패해도 나머지 계속
