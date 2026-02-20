# Run Collection Pipeline

수집 파이프라인을 실행하고 결과를 확인한다.

## Steps

1. `python main.py --hours 48 --top 20` 실행
2. 출력 로그에서 각 소스별 수집 건수 확인
3. 에러가 있으면 해당 collector 코드를 읽고 수정
4. 수정 후 다시 실행하여 정상 동작 확인
5. 생성된 `output/digest_*.md` 파일 내용 확인
6. 수정사항이 있으면 git commit
