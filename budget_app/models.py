from dataclasses import asdict, dataclass
from datetime import date
from uuid import uuid4


def check_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError as error:
        raise ValueError("실제 존재하는 날짜를 YYYY-MM-DD 형식으로 입력하세요.") from error
    return value


def check_month(value: str) -> str:
    check_date(value + "-01")
    return value


def positive_amount(value: str | int) -> int:
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdecimal():
        raise ValueError("금액은 양수 정수로 입력하세요.")
    amount = int(value)
    if amount <= 0:
        raise ValueError("금액은 0보다 커야 합니다.")
    return amount


def check_type(value: str) -> str:
    if value not in ("income", "expense"):
        raise ValueError("타입은 income 또는 expense로 입력하세요.")
    return value


def check_category(value: str, categories: list[str]) -> str:
    if value not in categories:
        raise ValueError("등록된 카테고리를 사용하세요: " + ", ".join(categories))
    return value


@dataclass
class Transaction:
    id: str
    date: str
    type: str
    category: str
    amount: int
    memo: str
    tags: list[str]

    @classmethod
    def create(cls, values: dict, categories: list[str]) -> "Transaction":
        day = check_date(values["date"])
        check_type(values["type"])
        check_category(values["category"], categories)
        tags = values.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError("태그는 문자열 목록이어야 합니다.")
        memo = values.get("memo", "")
        identifier = values.get("id", uuid4().hex)
        if not isinstance(memo, str) or not isinstance(identifier, str) or not identifier:
            raise ValueError("메모와 거래 ID를 확인하세요.")
        return cls(identifier, day, values["type"], values["category"],
                   positive_amount(values["amount"]), memo, tags)

    def to_dict(self) -> dict:
        return asdict(self)
