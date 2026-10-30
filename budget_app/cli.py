import argparse
from datetime import date
from itertools import islice
from pathlib import Path
from collections.abc import Callable, Iterable

from .decorators import handle_errors
from .models import Transaction, check_category, check_date, check_type, positive_amount
from .service import BudgetService
from .storage import Repository


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        super().error(f"{message}\n[힌트] 해당 명령에 --help를 붙여 사용법을 확인하세요.")


def build_parser() -> Parser:
    parser = Parser(description="나만의 용돈 기입장")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="저장 폴더 (기본: ./data)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("add", help="대화형 거래 추가")
    listing = commands.add_parser("list", help="최신순 거래 목록")
    listing.add_argument("--limit", type=positive_amount, default=20, help="출력 개수 (기본: 20)")
    search = commands.add_parser("search", help="조건을 모두 만족하는 거래 검색")
    search.add_argument("--from", dest="start", help="시작일 (YYYY-MM-DD)")
    search.add_argument("--to", dest="end", help="종료일 (YYYY-MM-DD)")
    search.add_argument("--category", help="카테고리")
    search.add_argument("--type", dest="kind", choices=["income", "expense"], help="거래 타입")
    search.add_argument("--q", dest="query", help="메모에 포함된 키워드")
    search.add_argument("--tag", help="일치하는 태그")
    summary = commands.add_parser("summary", help="월별 수입·지출·예산 요약")
    summary.add_argument("--month", required=True, help="대상 월 (YYYY-MM)")
    summary.add_argument("--top", type=positive_amount, default=3, help="카테고리 개수 (기본: 3)")
    budget = commands.add_parser("budget", help="월 예산 설정·조회")
    budget_commands = budget.add_subparsers(dest="action", required=True)
    setting = budget_commands.add_parser("set", help="예산 설정")
    setting.add_argument("--month", required=True, help="대상 월 (YYYY-MM)")
    setting.add_argument("--amount", required=True, help="예산 (양수 정수)")
    showing = budget_commands.add_parser("show", help="설정된 월 예산 조회")
    showing.add_argument("--month", required=True, help="대상 월 (YYYY-MM)")
    category = commands.add_parser("category", help="카테고리 관리")
    category_commands = category.add_subparsers(dest="action", required=True)
    category_commands.add_parser("list", help="카테고리 목록")
    category_commands.add_parser("add", help="대화형 카테고리 추가")
    category_commands.add_parser("remove", help="대화형 카테고리 삭제")
    update = commands.add_parser("update", help="옵션으로 지정한 필드 수정")
    update.add_argument("--id", required=True, help="수정할 거래 ID")
    update.add_argument("--date", help="날짜 (YYYY-MM-DD)")
    update.add_argument("--type", choices=["income", "expense"], help="거래 타입")
    update.add_argument("--category", help="등록된 카테고리")
    update.add_argument("--amount", help="금액 (양수 정수)")
    update.add_argument("--memo", help="메모 (빈 문자열로 지우기 가능)")
    update.add_argument("--tags", help="쉼표로 구분한 태그 (빈 문자열로 지우기 가능)")
    delete = commands.add_parser("delete", help="거래 삭제")
    delete.add_argument("--id", required=True, help="삭제할 거래 ID")
    importing = commands.add_parser("import", help="CSV 전체 검증 후 가져오기")
    importing.add_argument("--from", dest="source", type=Path, required=True, help="가져올 CSV 경로")
    exporting = commands.add_parser("export", help="월 또는 기간 조건으로 CSV 내보내기")
    exporting.add_argument("--out", type=Path, required=True, help="출력 CSV 경로")
    exporting.add_argument("--month", help="대상 월 (YYYY-MM)")
    exporting.add_argument("--from", dest="start", help="시작일 (YYYY-MM-DD)")
    exporting.add_argument("--to", dest="end", help="종료일 (YYYY-MM-DD)")
    return parser


def read_value(prompt: str, check: Callable[[str], object], default: str = "") -> str:
    while True:
        value = input(prompt).strip() or default
        try:
            check(value)
            return value
        except ValueError as error:
            print(f"[오류] {error}")
            print("[힌트] 이 항목을 다시 입력하세요.")


def show_transactions(transactions: Iterable[Transaction]) -> None:
    count = 0
    for item in transactions:
        print(f"{item.id} | {item.date} | {item.type:7} | {item.category} | "
              f"{item.amount:,}원 | {item.memo} | {','.join(item.tags)}")
        count += 1
    if count == 0:
        print("데이터 없음")


def show_summary(service: BudgetService, month: str, top: int) -> None:
    result = service.summary(month)
    if not result["count"]:
        print("데이터 없음")
    income, expense = result["income"], result["expense"]
    print(f"총 수입: {income:,}원\n총 지출: {expense:,}원\n잔액: {income - expense:,}원")
    budget = result["budget"]
    if budget is not None:
        print(f"예산: {budget:,}원 (사용률 {expense / budget * 100:.1f}%)")
        if expense > budget:
            print(f"[경고] 예산을 {expense - budget:,}원 초과했습니다.")
    print(f"지출 TOP {top}")
    for number, (category, amount) in enumerate(result["categories"][:top], 1):
        print(f"{number}) {category} {amount:,}원")


@handle_errors
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service = BudgetService(Repository(args.data_dir))
    if args.command == "add":
        categories = service.repository.category_names()
        print("등록된 카테고리: " + ", ".join(categories))
        values = {
            "date": read_value("날짜(YYYY-MM-DD, 엔터: 오늘): ", check_date, date.today().isoformat()),
            "type": read_value("타입(income/expense): ", check_type),
            "category": read_value("카테고리: ", lambda value: check_category(value, categories)),
            "amount": read_value("금액(양수 정수): ", positive_amount),
            "memo": input("메모(선택): "),
            "tags": input("태그(쉼표 구분, 선택): "),
        }
        print(f"[저장 완료] id={service.add(values).id}")
    elif args.command == "list":
        # service.repository.iter_transactions()[:args.limit]
        show_transactions(islice(service.repository.iter_transactions(), args.limit))
    elif args.command == "search":
        show_transactions(service.search(args.start, args.end, args.category,
                                         args.kind, args.query, args.tag))
    elif args.command == "summary":
        show_summary(service, args.month, args.top)
    elif args.command == "budget":
        if args.action == "set":
            service.set_budget(args.month, args.amount)
            print(f"[저장 완료] {args.month} 예산 {args.amount}원")
        else:
            amount = service.get_budget(args.month)
            print(f"예산: {amount:,}원" if amount is not None else "설정된 예산 없음")
    elif args.command == "category":
        if args.action == "list":
            for name in service.repository.category_names():
                print(f"- {name}")
        else:
            name = input("카테고리명: ").strip()
            if args.action == "add":
                service.add_category(name)
            else:
                service.remove_category(name)
            print(f"[완료] category={name}")
    elif args.command == "update":
        changes = {key: getattr(args, key) for key in
                   ["date", "type", "category", "amount", "memo", "tags"]
                   if getattr(args, key) is not None}
        if not changes:
            raise ValueError("수정할 필드를 하나 이상 지정하세요. 예: --memo 점심")
        service.change(args.id, changes)
        print(f"[수정 완료] id={args.id}")
    elif args.command == "delete":
        service.change(args.id)
        print(f"[삭제 완료] id={args.id}")
    elif args.command == "import":
        print(f"[완료] imported={service.import_csv(args.source)}")
    elif args.command == "export":
        count = service.export_csv(args.out, args.month, args.start, args.end)
        print(f"[완료] {args.out} ({count}건)")
    return 0
