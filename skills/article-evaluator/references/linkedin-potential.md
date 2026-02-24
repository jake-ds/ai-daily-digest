# LinkedIn 포텐셜 계산

## ai_score 가중치

전체 콘텐츠 품질을 측정하는 가중 평균.

```python
AI_SCORE_WEIGHTS = {
    "curiosity": 1.5,
    "insight": 2.0,      # 인사이트가 가장 중요
    "relevance": 1.5,
    "timeliness": 1.0,
    "discussion": 1.0,
    "shareability": 1.0,
    "depth": 1.5,
}
# 총 가중치: 9.5
# ai_score = Σ(score × weight) / 9.5
```

## linkedin_potential 가중치

LinkedIn 플랫폼에서의 engagement 예측.

```python
LINKEDIN_WEIGHTS = {
    "curiosity": 1.5,
    "insight": 1.0,
    "discussion": 2.0,     # 댓글 유발이 핵심
    "shareability": 2.0,   # 공유 가치가 핵심
    "depth": 1.0,
}
# 총 가중치: 7.5
# linkedin_potential = Σ(score × weight) / 7.5
```

## 심층 평가 가중치

```python
EVAL_WEIGHTS = {
    "timeliness": 2.5,          # 시의성 최우선
    "discussion_trigger": 1.5,
    "shareability": 1.5,
    "explainability": 1.0,
    "unique_angle": 1.0,
}
# 총 가중치: 7.5
```

## verdict 기준

| verdict | 점수 범위 | 의미 |
|---------|----------|------|
| 추천 | 7.0+ | LinkedIn 포스트로 적합 |
| 보류 | 5.0-7.0 | 조건부 적합 (각도에 따라) |
| 탈락 | 5.0 미만 | 부적합 |

## 다양성 보장 규칙

최종 후보 선정 시:
1. research 카테고리 최소 1개 보장
2. news 카테고리(bigtech, vc, news, community, korean) 최소 1개 보장
3. 나머지는 순수 점수순
4. 최종 결과는 점수순 재정렬
