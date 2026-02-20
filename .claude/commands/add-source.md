# Add New Data Source

새로운 데이터 소스를 파이프라인에 추가한다. $ARGUMENTS에 소스 이름과 타입이 주어진다.

## Steps

1. 기존 collector 중 가장 유사한 것을 읽어 패턴 파악 (RSS → rss_collector.py, API → hn_collector.py, 스크래핑 → github_trending.py)
2. `src/collectors/$ARGUMENTS_collector.py` 생성
   - Article 데이터클래스를 import
   - `collect(hours: int) -> list[Article]` 메서드 구현
   - 에러 처리 포함
3. `src/collectors/__init__.py`에 새 클래스 export 추가
4. `main.py`의 수집 단계에 새 collector 호출 추가
5. 필요한 패키지가 있으면 `requirements.txt`에 추가
6. API 키가 필요하면 `.env.example`에 추가
7. `python -m py_compile`로 문법 검증
8. 변경사항을 git commit
