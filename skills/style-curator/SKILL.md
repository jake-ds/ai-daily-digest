---
name: style-curator
description: LinkedIn 스타일 가이드를 학습하고 관리하는 스킬. 승인된 포스트를 분석하여 스타일 패턴 추출 → StyleProfile 업데이트 → 가이드라인 개선안 제시. 스타일 분석, 가이드라인 업데이트, 톤 조정, 패턴 학습, 레퍼런스 포스트 관리 등의 작업에 사용한다.
---

# Style Curator

승인된 LinkedIn 포스트에서 스타일 패턴을 추출하고, 가이드라인을 지속적으로 개선하는 스킬.

## 데이터 소스

```
guidelines.md → StyleBriefBuilder.build() → StyleBrief → Consumers
StyleProfile DB                                          Hook (Step 0)
ReferencePost DB                                         Draft (Step 3)
Past Learnings                                           Review (Step 4)
```

### 1. guidelines.md

`data/linkedin_guidelines.md` — Jake의 LinkedIn 작성 지침 (529줄).
구조: Persona → 글쓰기 기법 → 시나리오별 가이드(A-F) → 공통 규칙 → 예시

### 2. StyleProfile (DB)

`web/models/` StyleProfile 테이블. JSON 구조:
```json
{
  "tone": {"formality": "...", "persona_voice": "..."},
  "structure_patterns": {"preferred_hooks": [], "body_flow": "...", "preferred_closings": []},
  "vocabulary": {"preferred_phrases": [], "forbidden_phrases": []},
  "positive_patterns": [],
  "negative_patterns": []
}
```

### 3. ReferencePost (DB)

시나리오별 레퍼런스 포스트. 최대 2개/시나리오 + fallback.

### 4. Past Learnings

최근 5개 draft의 평가 결과에서 추출:
- FAIL 패턴 (반복 실수)
- 고득점 패턴 (효과적이었던 것)
- 사용자 피드백/수정 이력

## 워크플로우

### 스타일 분석

승인된 포스트가 입력되면:
1. **톤 분석**: formality 수준, persona_voice 일치도
2. **구조 분석**: 훅 패턴, 본문 흐름, 마무리 패턴
3. **어휘 분석**: 선호/금지 표현 사용 빈도
4. **패턴 추출**: 효과적/비효과적 패턴 식별

분석 프레임워크 상세는 [references/analysis-framework.md](references/analysis-framework.md) 참조.

### StyleProfile 업데이트

분석 결과를 StyleProfile DB에 반영:
- 새로운 선호 표현 추가
- 금지 표현 목록 갱신
- 구조 패턴 업데이트
- positive/negative 패턴 갱신

### 가이드라인 개선안 제시

실제 작성 스타일과 문서화된 가이드라인의 차이(드리프트)를 감지하여 개선안 제시.

시나리오별 이상적 포스트 특성은 [references/scenario-archetypes.md](references/scenario-archetypes.md) 참조.
가이드라인 작성 규격은 [references/guidelines-format.md](references/guidelines-format.md) 참조.

## StyleBrief 조립

StyleBriefBuilder가 4개 소스를 조립하여 StyleBrief 객체 생성:

| Consumer | 사용하는 섹션 |
|----------|-------------|
| Hook (Step 0) | persona + tone + hook guidelines + preferred_phrases |
| Outline (Step 2) | structure_patterns + positive_patterns + reference_examples |
| Writer (Step 3) | 전체 (persona, tone, guidelines, structure, examples, vocab, patterns, learnings) |
| Reviewer (Step 4) | scenario_guidelines + negative_patterns + forbidden_phrases |
| Chat Refine | writer 섹션 + analysis + chat context |

## 드리프트 감지

감지할 불일치:
- 가이드라인은 "하십시오체"인데 실제로 "해요체"가 많은 경우
- 가이드라인에 없는 새로운 효과적 패턴이 반복되는 경우
- 금지 표현인데 사용자가 승인한 경우
- 특정 시나리오의 가이드라인이 실제 작성과 크게 다른 경우
