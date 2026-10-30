import csv
from collections import defaultdict
from collections.abc import Iterator
from heapq import merge
from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from .models import Transaction, check_date, check_month, positive_amount
from .storage import Repository, read_rows, write_rows


CSV_FIELDS = ["date", "type", "category", "amount", "memo", "tags"]


class BudgetService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def add(self, values: dict) -> Transaction:
        transaction = Transaction.create(values, self.repository.category_names())
        self.insert([transaction])
        return transaction

    def insert(self, transactions: list[Transaction]) -> None:
        ordered = sorted(transactions, key=lambda item: item.date, reverse=True)
        combined = merge(ordered, self.repository.iter_transactions(),
                         key=lambda item: item.date, reverse=True)
        self.repository.save_transactions(combined)

    def search(self, start: str | None = None, end: str | None = None,
               category: str | None = None, kind: str | None = None,
               query: str | None = None, tag: str | None = None,
               month: str | None = None) -> Iterator[Transaction]:
        if start is not None:
            check_date(start)
        if end is not None:
            check_date(end)
        if start and end and start > end:
            raise ValueError("시작일은 종료일보다 늦을 수 없습니다.")
        if month is not None:
            check_month(month)
        for item in self.repository.iter_transactions():
            if start and item.date < start:
                continue
            if end and item.date > end:
                continue
            if month and not item.date.startswith(month):
                continue
            if category and item.category != category:
                continue
            if kind and item.type != kind:
                continue
            if query and query.casefold() not in item.memo.casefold():
                continue
            if tag and tag not in item.tags:
                continue
            yield item

    def change(self, identifier: str, changes: dict | None = None) -> None:
        original = next((item for item in self.repository.iter_transactions()
                         if item.id == identifier), None)
        if original is None:
            raise ValueError("없는 데이터입니다. list 또는 search로 ID를 확인하세요.")
        replacement = []
        if changes is not None:
            values = original.to_dict()
            values.update(changes)
            replacement.append(Transaction.create(values, self.repository.category_names()))
        remaining = (item for item in self.repository.iter_transactions()
                     if item.id != identifier)
        self.repository.save_transactions(merge(replacement, remaining,
                                                key=lambda item: item.date, reverse=True))

    def add_category(self, name: str) -> None:
        names = self.repository.category_names()
        if not name.strip() or name != name.strip() or name in names:
            raise ValueError("카테고리는 중복 없이, 앞뒤 공백 없이 입력하세요.")
        names.append(name)
        write_rows(self.repository.categories, ({"name": value} for value in names))

    def remove_category(self, name: str) -> None:
        names = self.repository.category_names()
        if name not in names:
            raise ValueError("등록되지 않은 카테고리입니다. category list로 확인하세요.")
        if any(item.category == name for item in self.repository.iter_transactions()):
            raise ValueError("사용 중인 카테고리입니다. 관련 거래를 먼저 수정하거나 삭제하세요.")
        if len(names) == 1:
            raise ValueError("마지막 카테고리는 삭제할 수 없습니다. 새 카테고리를 먼저 추가하세요.")
        write_rows(self.repository.categories, ({"name": value} for value in names if value != name))

    def get_budgets(self) -> dict[str, int]:
        budgets = {}
        for row in read_rows(self.repository.budgets):
            try:
                budgets[check_month(row["month"])] = positive_amount(row["amount"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("예산 파일이 손상되었습니다. 백업 파일을 확인하세요.") from error
        return budgets

    def set_budget(self, month: str, amount: str) -> None:
        check_month(month)
        value = positive_amount(amount)
        budgets = self.get_budgets()
        budgets[month] = value
        write_rows(self.repository.budgets,
                   ({"month": key, "amount": value} for key, value in sorted(budgets.items())))

    def get_budget(self, month: str) -> int | None:
        check_month(month)
        return self.get_budgets().get(month)

    def summary(self, month: str) -> dict:
        income = expense = count = 0
        categories: dict[str, int] = defaultdict(int)
        for item in self.search(month=month):
            count += 1
            if item.type == "income":
                income += item.amount
            else:
                expense += item.amount
                categories[item.category] += item.amount
        return {"income": income, "expense": expense, "count": count,
                "categories": sorted(categories.items(), key=lambda pair: (-pair[1], pair[0])),
                "budget": self.get_budget(month)}

    def import_csv(self, path: Path) -> int:
        transactions = []
        categories = self.repository.category_names()
        with path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source, strict=True)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("CSV 헤더가 없거나 중복되었습니다. README의 스키마를 확인하세요.")
            if not set(CSV_FIELDS[:4]).issubset(reader.fieldnames):
                raise ValueError("CSV 필수 헤더는 date,type,category,amount입니다.")
            for row in reader:
                try:
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError("열 수가 헤더와 다릅니다.")
                    values = {key: row.get(key, "") for key in CSV_FIELDS}
                    transactions.append(Transaction.create(values, categories))
                except (KeyError, TypeError, ValueError) as error:
                    raise ValueError(f"CSV {reader.line_num}행 오류: {error} 전체 가져오기를 취소했습니다.") from error
        if transactions:
            self.insert(transactions)
        return len(transactions)

    def export_csv(self, path: Path, month: str | None = None,
                   start: str | None = None, end: str | None = None) -> int:
        if not month and not (start and end):
            raise ValueError("--month 또는 --from과 --to를 함께 지정하세요.")
        if month and (start or end):
            raise ValueError("월 조건과 기간 조건 중 하나만 사용하세요.")
        saved_paths = (self.repository.transactions, self.repository.categories, self.repository.budgets)
        if any(path.resolve() == saved.resolve() for saved in saved_paths):
            raise ValueError("저장 파일에 덮어쓸 수 없습니다. 다른 출력 경로를 지정하세요.")
        temporary = None
        count = 0
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                    dir=path.parent, delete=False) as target:
                temporary = Path(target.name)
                writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
                writer.writeheader()
                for item in self.search(month=month, start=start, end=end):
                    row = item.to_dict()
                    del row["id"]
                    row["tags"] = ",".join(item.tags)
                    writer.writerow(row)
                    count += 1
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return count
