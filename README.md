# 나만의 용돈 기입장

Python 표준 라이브러리만 사용하는 콘솔 가계부입니다. Python 3.10 이상에서 실행합니다.

## 실행

이 폴더에서 실행합니다. 별도 설치는 필요 없습니다.

```sh
python3 -m budget_app --help
python3 -m budget_app add
python3 -m budget_app list --limit 5
```

`add`는 날짜, 타입, 카테고리, 금액, 메모, 태그를 순서대로 입력받습니다. 날짜를 비우면 오늘 날짜를 사용합니다. 날짜·타입·카테고리·금액은 입력 직후 검증하며, 잘못 입력하면 오류와 힌트를 표시하고 해당 항목만 다시 입력받습니다. 취소하려면 `Ctrl+C`를 누르세요. 저장 전까지 파일은 바뀌지 않습니다.

기본 카테고리는 `food`, `transport`, `rent`, `salary`, `etc`입니다. 날짜는 `YYYY-MM-DD`, 타입은 `income` 또는 `expense`, 금액은 양수 정수입니다. 태그는 쉼표로 구분합니다.

저장 폴더는 현재 작업 폴더의 `./data`입니다. 변경하려면 **명령 앞에** `--data-dir`을 지정하고, 이후 실행에도 같은 경로를 사용하세요.

```sh
python3 -m budget_app --data-dir ./my-data list
```

모든 명령과 하위 명령은 `--help`를 지원합니다.

## 명령 예시

```sh
python3 -m budget_app search --from 2026-10-01 --to 2026-10-31
python3 -m budget_app search --category food --type expense --q 점심 --tag 학교
python3 -m budget_app summary --month 2026-10 --top 3

python3 -m budget_app budget set --month 2026-10 --amount 500000
python3 -m budget_app budget show --month 2026-10

python3 -m budget_app category add
python3 -m budget_app category list
python3 -m budget_app category remove

python3 -m budget_app update --id 거래ID --amount 12000 --memo "친구와 점심"
python3 -m budget_app update --id 거래ID --memo "" --tags ""
python3 -m budget_app delete --id 거래ID

python3 -m budget_app import --from input.csv
python3 -m budget_app export --out october.csv --month 2026-10
python3 -m budget_app export --out period.csv --from 2026-10-01 --to 2026-10-15
```

- `거래ID`에는 추가 결과나 목록에 표시된 ID를 넣습니다.
- `update`는 **옵션 방식**입니다. 지정한 필드만 바꾸고 ID는 유지합니다.
- 카테고리 추가·삭제는 이름을 대화형으로 입력합니다. 사용 중이거나 마지막으로 남은 카테고리는 삭제할 수 없습니다.
- 검색 조건은 모두 함께 적용하며, 시작일과 종료일을 포함합니다. 메모는 부분 일치, 태그는 완전 일치로 찾습니다.
- 목록·검색은 거래 날짜 최신순입니다. 같은 날짜에서는 나중에 추가한 거래가 먼저 나오며, 수정하면 해당 날짜의 맨 앞으로 이동합니다.
- 요약은 총수입·총지출·잔액과 지출 TOP N을 보여줍니다. 예산이 있으면 사용률을 표시하고 지출이 예산보다 클 때 경고합니다. 빈 달은 `데이터 없음`을 표시합니다.
- 내보내기는 월 또는 시작일·종료일 중 한 가지 조건을 반드시 지정합니다. 같은 경로의 기존 CSV는 성공 시 교체합니다.
- 정상 종료 코드는 `0`, 입력·파일 오류는 `1`, 명령 형식 오류는 `2`입니다. 오류는 스택트레이스 없이 원인과 해결 힌트를 표시합니다.

## 저장 파일

첫 실행에 다음 세 파일을 자동 생성합니다. JSONL은 한 줄에 JSON 객체 하나를 저장하는 형식입니다.

| 파일 | 한 줄 예시 |
| --- | --- |
| `data/transactions.jsonl` | `{"id":"고유ID","date":"2026-10-01","type":"expense","category":"food","amount":1000,"memo":"점심","tags":["학교"]}` |
| `data/categories.jsonl` | `{"name":"food"}` |
| `data/budgets.jsonl` | `{"month":"2026-10","amount":500000}` |

카테고리 파일이 비어 있으면 기본 카테고리를 생성합니다. 거래 ID는 UUID로 생성합니다. 파일은 UTF-8이며 직접 편집하는 대신 명령으로 변경하세요. 실행 위치를 바꿔도 같은 데이터를 쓰려면 `--data-dir`에 절대 경로를 넣으세요.

## CSV 가져오기·내보내기

UTF-8, 헤더 포함 형식입니다. 가져올 때 UTF-8 BOM도 허용합니다. 내보내기는 아래 여섯 열을 순서대로 작성합니다.

| 열 | 필수 | 형식 |
| --- | --- | --- |
| date | 예 | YYYY-MM-DD |
| type | 예 | income / expense |
| category | 예 | 등록된 카테고리 |
| amount | 예 | 양수 정수 |
| memo | 아니요 | 문자열, 생략하면 빈 문자열 |
| tags | 아니요 | 쉼표로 구분한 문자열, 생략하면 빈 목록 |

```csv
date,type,category,amount,memo,tags
2026-10-01,income,salary,100000,용돈,
2026-10-02,expense,food,8000,점심,"식사,학교"
```

쉼표나 줄바꿈이 있는 값은 CSV 규칙에 맞게 큰따옴표로 감쌉니다. 가져오기는 전체 파일을 검증한 뒤 저장합니다. 잘못된 거래 행은 위치와 원인을 알려주고 **전체 취소**합니다. 깨진 따옴표 등 CSV 문법 오류도 반영 전에 취소됩니다.

가져올 때마다 새 ID를 생성합니다. 같은 CSV를 두 번 가져오면 거래가 중복됩니다. ID는 내보내지 않으며, 카테고리와 예산도 CSV에 포함하지 않습니다. 전체 백업이 필요하면 프로그램을 종료한 뒤 `data` 폴더를 복사하세요.

## 코드 읽는 순서

| 파일 | 책임 |
| --- | --- |
| `budget_app/__main__.py` | 프로그램 시작과 종료 코드 전달 |
| `budget_app/cli.py` | 명령 해석, 대화형 입력, 화면 출력 |
| `budget_app/service.py` | 거래 변경, 검색, 집계, 예산·카테고리 규칙, CSV 변환 |
| `budget_app/storage.py` | JSONL 읽기, 안전한 파일 교체 |
| `budget_app/models.py` | 거래 필드와 입력 검증 |
| `budget_app/decorators.py` | 공통 오류 처리 |

`Transaction`은 거래 한 건, `Repository`는 저장 파일, `BudgetService`는 업무 규칙을 담당합니다. 기능을 따라 읽으려면 `cli.main → BudgetService의 해당 메서드 → Repository` 순서로 보세요.

### 평가 때 설명할 핵심

1. **제너레이터:** `read_rows → iter_transactions → search`가 `yield`로 한 건씩 전달합니다. `list`는 `islice`로 필요한 개수만 읽습니다. 정렬된 파일 덕분에 목록·검색은 거래 전체를 메모리에 올리지 않습니다.
2. **정렬 유지:** 추가·수정할 거래와 기존 파일을 `heapq.merge`로 합쳐 날짜 내림차순을 유지합니다. 같은 날짜에서는 새 거래가 먼저입니다. CSV 안에서 날짜까지 같은 행은 CSV 순서를 유지합니다.
3. **안전한 저장:** `write_rows`는 같은 폴더의 임시 파일에 쓰고 `flush`, `fsync` 후 `os.replace`로 교체합니다. 중간 실패 시 원본을 유지하고 임시 파일을 지웁니다. 추가·수정·삭제·가져오기에 같은 방식을 사용합니다.
4. **데코레이터:** `@handle_errors`가 입력·파일 오류와 입력 취소를 메시지·종료 코드로 바꿉니다. 각 명령에 같은 예외 처리를 반복하지 않습니다. 명령 형식 오류는 `argparse`가 처리합니다.
5. **타입 힌트:** `iter_transactions() -> Iterator[Transaction]`은 거래가 하나씩 나온다는 계약입니다. `change(..., changes: dict | None)`에서 `None`은 삭제, 사전은 수정할 필드를 뜻합니다. 실제 값 검증은 별도 함수가 담당합니다.
6. **JSONL 선택:** 태그 목록을 그대로 저장하고 줄마다 파싱할 수 있어 선택했습니다. CSV는 표 계산 도구와 호환되지만 태그 같은 목록은 문자열 변환이 필요합니다. 저장은 JSONL로 통일하고 CSV는 교환에만 사용합니다.

### 범위와 개선 방향

- 한 번에 한 프로세스가 사용하는 학습용 프로그램입니다. 동시 실행의 덮어쓰기를 막는 파일 잠금은 구현하지 않았습니다.
- 목록·검색은 거래 수와 무관하게 한 건씩 읽습니다. 검색·요약은 전체 순회가 필요하며, 추가·수정·삭제도 파일 전체를 다시 쓰므로 O(N)입니다. 출력 개수를 제한한 목록은 앞부분만 읽습니다.
- CSV 가져오기는 전체 취소 정책을 단순하게 구현하려고 가져올 거래를 메모리에 모아 정렬합니다. 대량 CSV는 임시 파일과 외부 정렬로 개선할 수 있습니다.
- 10만 건 이상을 자주 변경한다면 날짜·ID 인덱스가 있는 SQLite로 저장소를 교체하는 것이 다음 단계입니다. 현재 과제의 JSONL 저장 제약 안에서는 월별 파일 분리와 변경 기록 방식 등을 검토할 수 있습니다.
- 제한된 목록은 읽은 구간만 검증합니다. 전체 데이터 검사는 목록 제한을 없애는 대신 `search`로 끝까지 읽어 확인할 수 있습니다. 오류 뒤쪽까지 읽지 않는 스트리밍 특성입니다.

## 검증

```sh
python3 -m unittest discover -s tests -v
```

입력 검증, 최신순 정렬, 복합 검색, 재실행 후 저장 유지, 수정·삭제, 예산 경고, 카테고리 보호, CSV 왕복, 잘못된 CSV 전체 취소, 저장 실패 시 원본 유지, 스트리밍, 명령별 도움말과 종료 코드를 검사합니다.

동료평가에서는 `add → list → update → search → budget set → summary → export → delete → import` 순서로 직접 실행하면 주요 기능을 확인할 수 있습니다. 가져오기 전에는 내보낸 거래를 삭제해야 중복을 피할 수 있습니다.
