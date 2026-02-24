# 검색 쿼리 생성 전략

## 2-쿼리 전략

### 쿼리 1: 배경 맥락

기사 주제의 업계 배경, 역사, 핵심 플레이어를 조사.

**패턴**:
- `[technology/product] industry overview 2025`
- `[company] [technology] background context`
- `[topic] market landscape analysis`

**예시**:
- 기사: "OpenAI launches GPT-5" → 쿼리: `GPT-5 OpenAI language model capabilities 2025`
- 기사: "Anthropic MCP 도입" → 쿼리: `Anthropic Model Context Protocol MCP adoption impact`

### 쿼리 2: 경쟁/비교/반론

경쟁사, 대안 기술, 비판적 시각을 조사.

**패턴**:
- `[product A] vs [product B] comparison`
- `[technology] alternatives competitors`
- `[technology] criticism limitations concerns`

**예시**:
- 기사: "OpenAI launches GPT-5" → 쿼리: `GPT-5 vs Claude vs Gemini comparison limitations`
- 기사: "AI Agent 시장 성장" → 쿼리: `AI agent frameworks comparison LangChain CrewAI alternatives`

## 쿼리 최적화 규칙

1. **영어로 작성**: Google 검색은 영어 쿼리가 결과가 풍부
2. **구체적 키워드**: 추상적 표현 대신 제품명, 기술명, 회사명 사용
3. **시기 포함**: 최신 정보를 위해 연도 포함 권장
4. **길이**: 3-8 단어가 최적
5. **따옴표 없이**: 자연어 쿼리 형태

## 쿼리 생성 실패 시

- LLM 호출 실패: 기사 제목을 그대로 쿼리로 사용
- 빈 결과: 제목에서 핵심 키워드만 추출하여 재시도
