# Add New Output Format

새로운 출력 형식을 추가한다. $ARGUMENTS에 출력 타입이 주어진다 (예: slack, telegram, discord).

## Steps

1. 기존 output 모듈 중 하나를 읽어 패턴 파악 (email_sender.py, notion_output.py 등)
2. `src/outputs/$ARGUMENTS_output.py` 생성
   - `save(articles)` 또는 `send(items)` 메서드 구현
   - 환경변수 없으면 graceful skip
3. `src/outputs/__init__.py`에 export 추가
4. `main.py` 또는 `personal_digest_worker.py`의 출력 단계에 연결
5. CLI 인자 추가 (argparse)
6. `.env.example`에 필요한 설정 추가
7. `python -m py_compile`로 검증
8. git commit
