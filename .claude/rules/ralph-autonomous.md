# Ralph Mode: Autonomous Operation Guidelines

이 프로젝트는 "Ralph" 패턴으로 운영된다 — 코딩 에이전트가 자율적으로 작업하고, 사람은 결과를 확인한다.

## Autonomous Task Execution

자율 작업 시 반드시 따를 규칙:

1. **변경 전 항상 기존 코드 읽기** — 패턴을 파악한 뒤 수정
2. **작은 단위로 커밋** — 하나의 기능/수정 = 하나의 커밋
3. **py_compile로 문법 검증** — 파일 수정 후 반드시 실행
4. **기존 패턴 따르기** — 새 collector는 기존 collector 구조를 복사
5. **환경변수 없이도 동작** — API 키 없으면 graceful skip

## Task Priority (자율 모드에서)

1. 버그 수정 (기존 기능이 깨진 경우)
2. 기존 collector 안정성 개선
3. 새 데이터 소스 추가
4. 출력 형식 개선
5. 웹 대시보드 기능 추가

## Safety Rules

- `.env` 파일 읽거나 수정하지 않는다
- `git push` 전에 반드시 사람 확인
- 외부 API 호출은 rate limit 존중
- 기존 동작하는 코드를 불필요하게 리팩토링하지 않는다
- `output/` 디렉토리의 기존 다이제스트 파일을 삭제하지 않는다
