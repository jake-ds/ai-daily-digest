# Ralph: Autonomous Improvement Cycle

프로젝트를 자율적으로 분석하고 개선한다. 돌려놓고 잠자는 모드.

## Phase 1: Health Check
1. `python -m py_compile main.py && python -m py_compile personal_digest_worker.py` — 문법 오류 확인
2. `python main.py --hours 24 --skip-summary` — 수집 파이프라인 동작 확인
3. 에러가 있으면 즉시 수정

## Phase 2: Code Quality
1. 모든 `src/collectors/*.py` 파일을 읽고 에러 처리 누락 확인
2. 모든 `src/processors/*.py` 파일을 읽고 edge case 확인
3. `web/` 코드에서 보안 이슈 확인 (SQL injection, XSS 등)
4. 발견된 문제를 수정하고 커밋

## Phase 3: Enhancement
1. `data/feeds.yaml`를 읽고 죽은 피드 URL 확인 (WebFetch로 테스트)
2. 수집 로그를 분석해서 자주 실패하는 소스 파악
3. collector별 타임아웃/재시도 로직 개선
4. 개선사항 커밋

## Phase 4: Documentation
1. 변경된 내용을 기반으로 CLAUDE.md 업데이트 (필요시)
2. 최종 `git log --oneline -10`으로 작업 요약
