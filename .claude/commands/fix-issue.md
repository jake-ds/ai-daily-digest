# Fix GitHub Issue

GitHub issue $ARGUMENTS를 분석하고 수정한다.

## Steps

1. `gh issue view $ARGUMENTS`로 이슈 내용 확인
2. 관련 코드 파일을 찾아서 읽기
3. 문제의 근본 원인 파악
4. 최소한의 변경으로 수정
5. `python -m py_compile`로 문법 검증
6. 관련 파이프라인 테스트 실행 (`python main.py --hours 24 --skip-summary`)
7. 수정 내용을 커밋: `fix: {이슈 설명} (#$ARGUMENTS)`
