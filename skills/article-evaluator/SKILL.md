---
name: article-evaluator
description: AI/Tech 기사의 품질과 LinkedIn 포스팅 적합성을 평가하는 스킬. 기사 목록이 주어지면 7차원 스코어링 → LinkedIn 포텐셜 계산 → 상위 후보 추천. 기사 평가, 스코어링, LinkedIn 후보 선정, 기사 순위 매기기 등의 작업에 사용한다.
---

# Article Evaluator

AI/Tech 기사를 다차원으로 평가하여 LinkedIn 포스팅 최적 후보를 선정하는 스킬.

## 워크플로우

```
기사 목록 → 1차 스크리닝(배치) → 2차 심층 평가(개별) → 테마 그룹핑 → 최종 후보 선정
```

### 1차 스크리닝 (배치 처리)

15개 단위로 배치 처리. 각 기사에 점수(0-10) + verdict(추천/보류/탈락) 부여.

**평가자 프로필**:
- AI와 스타트업에 관심이 많은 사람
- 과장된 마케팅 톤 싫어함
- 실용적인 인사이트와 흥미로운 발견을 좋아함

**즉시 탈락 기준**:
- 단순 제품 출시 발표 (새 버전, 새 기능)
- 너무 기술적이라 설명이 어려운 논문
- 이미 많이 알려진 뻔한 내용
- 한국 독자가 관심 없을 지역 뉴스
- 스캔들/가십성 기사 (업계 시사점이 있으면 예외)

### 2차 심층 평가

상위 후보를 5차원으로 정밀 분석. 스코어링 상세는 [references/scoring-dimensions.md](references/scoring-dimensions.md) 참조.

### 테마 그룹핑

연관 기사를 주제별로 묶어 synthesis 포스트 가능성 탐색.
그룹핑 기준: 같은 기술 분야, 같은 회사, 같은 트렌드, 같은 문제/과제.
최소 3개 이상이어야 그룹 인정.

### 최종 후보 선정

카테고리 다양성 보장: research 최소 1개, news 최소 1개 포함.

## 스코어링 체계

두 가지 가중 평균 점수를 산출. 상세는 [references/linkedin-potential.md](references/linkedin-potential.md) 참조.

**ai_score** (전체 품질):
- curiosity(1.5) + insight(2.0) + relevance(1.5) + timeliness(1.0) + discussion(1.0) + shareability(1.0) + depth(1.5)

**linkedin_potential** (LinkedIn 특화):
- curiosity(1.5) + insight(1.0) + discussion(2.0) + shareability(2.0) + depth(1.0)

## 가중치 조정

가중치 조정 방법론은 [references/weight-tuning.md](references/weight-tuning.md) 참조.

## 모델 사용

| 단계 | 모델 | 이유 |
|------|------|------|
| 1차 스크리닝 | Haiku | 대량 배치, 속도 우선 |
| 2차 심층 평가 | Haiku | 개별 정밀 분석 |
| 테마 그룹핑 | Haiku | 분류 작업 |
