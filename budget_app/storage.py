import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile

from .models import Transaction


def read_rows(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as source:
        for number, line in enumerate(source, 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("객체가 아닙니다.")
            except ValueError as error:
                raise ValueError(f"{path.name} {number}행이 손상되었습니다. 백업 파일을 확인하세요.") from error
            yield row


def write_rows(path: Path, rows: Iterable[dict]) -> None:
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                delete=False) as target:
            temporary = Path(target.name)
            for row in rows:
                target.write(json.dumps(row, ensure_ascii=False) + "\n")
            target.flush()
            os.fsync(target.fileno())
        # 모든 행의 저장이 끝난 뒤에만 원본을 교체한다.
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Repository:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.transactions = directory / "transactions.jsonl"
        self.categories = directory / "categories.jsonl"
        self.budgets = directory / "budgets.jsonl"
        for path in (self.transactions, self.categories, self.budgets):
            path.touch(exist_ok=True)
        if self.categories.stat().st_size == 0:
            write_rows(self.categories, ({"name": name} for name in
                                        ["food", "transport", "rent", "salary", "etc"]))

    def category_names(self) -> list[str]:
        names = []
        for row in read_rows(self.categories):
            name = row.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("카테고리 파일이 손상되었습니다. 백업 파일을 확인하세요.")
            names.append(name)
        return names

    def iter_transactions(self) -> Iterator[Transaction]:
        categories = self.category_names()
        previous_date = "9999-12-31"
        for number, row in enumerate(read_rows(self.transactions), 1):
            try:
                transaction = Transaction.create(row, categories)
                if "id" not in row or transaction.date > previous_date:
                    raise ValueError("거래 ID 또는 날짜 정렬을 확인하세요.")
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"거래 파일 {number}행이 잘못되었습니다: {error}") from error
            previous_date = transaction.date
            yield transaction

    def save_transactions(self, transactions: Iterable[Transaction]) -> None:
        write_rows(self.transactions, (item.to_dict() for item in transactions))
