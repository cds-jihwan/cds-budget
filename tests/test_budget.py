import csv
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from budget_app.cli import main
from budget_app.models import Transaction
from budget_app.service import BudgetService, CSV_FIELDS
from budget_app.storage import Repository, write_rows


class BudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.service = BudgetService(Repository(self.directory / "data"))

    def values(self, **changes) -> dict:
        values = {"date": "2026-10-01", "type": "expense", "category": "food",
                  "amount": "1000", "memo": "점심", "tags": "식사,학교"}
        values.update(changes)
        return values

    def write_csv(self, rows: list[dict]) -> Path:
        path = self.directory / "input.csv"
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_validation(self) -> None:
        for changes in [{"date": "2026-02-29"}, {"date": "20261001"},
                        {"amount": "0"}, {"amount": "-1"}, {"amount": "1.5"},
                        {"amount": True}, {"type": "other"}, {"category": "unknown"}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                Transaction.create(self.values(**changes), self.service.repository.category_names())

    def test_order_search_and_restart(self) -> None:
        old = self.service.add(self.values())
        new = self.service.add(self.values(date="2026-10-03"))
        same_day = self.service.add(self.values(date="2026-10-03", category="transport"))
        reopened = BudgetService(Repository(self.directory / "data"))
        self.assertEqual([item.id for item in reopened.search()], [same_day.id, new.id, old.id])
        matches = list(reopened.search(start="2026-10-02", end="2026-10-03", category="food",
                                       kind="expense", query="점", tag="학교"))
        self.assertEqual([item.id for item in matches], [new.id])
        self.assertEqual(list(reopened.search(tag="학")), [])
        with self.assertRaises(ValueError):
            list(reopened.search(start="2026-10-04", end="2026-10-01"))
        with self.assertRaises(ValueError):
            reopened.summary("")

    def test_update_delete_and_missing_id(self) -> None:
        first = self.service.add(self.values())
        second = self.service.add(self.values(date="2026-10-03"))
        self.service.change(first.id, {"date": "2026-10-04", "memo": "", "tags": ""})
        results = list(self.service.search())
        self.assertEqual([item.id for item in results], [first.id, second.id])
        self.assertEqual((results[0].memo, results[0].tags), ("", []))
        self.service.change(first.id)
        self.assertEqual([item.id for item in self.service.search()], [second.id])
        with self.assertRaisesRegex(ValueError, "없는 데이터"):
            self.service.change(first.id)
        before = self.service.repository.transactions.read_bytes()
        with self.assertRaises(ValueError):
            self.service.change(second.id, {"amount": "0"})
        self.assertEqual(self.service.repository.transactions.read_bytes(), before)

    def test_categories_and_budget_persist(self) -> None:
        self.service.add_category("취미")
        self.service.add(self.values(category="취미", amount="1500"))
        with self.assertRaisesRegex(ValueError, "사용 중"):
            self.service.remove_category("취미")
        with self.assertRaises(ValueError):
            self.service.add_category("취미")
        self.service.remove_category("rent")
        self.service.set_budget("2026-10", "1000")
        reopened = BudgetService(Repository(self.directory / "data"))
        self.assertIn("취미", reopened.repository.category_names())
        self.assertNotIn("rent", reopened.repository.category_names())
        self.assertEqual(reopened.summary("2026-10")["budget"], 1000)
        self.assertEqual(reopened.summary("2026-11")["count"], 0)
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--data-dir", str(self.directory / "data"),
                         "summary", "--month", "2026-10"])
        self.assertEqual(code, 0)
        self.assertIn("150.0%", output.getvalue())
        self.assertIn("[경고]", output.getvalue())

    def test_summary_totals(self) -> None:
        self.service.add(self.values(type="income", category="salary", amount="5000"))
        self.service.add(self.values(amount="1200"))
        self.service.add(self.values(category="transport", amount="500"))
        self.service.add(self.values(date="2026-11-01", amount="9999"))
        result = self.service.summary("2026-10")
        self.assertEqual((result["income"], result["expense"]), (5000, 1700))
        self.assertEqual(result["categories"], [("food", 1200), ("transport", 500)])

    def test_import_export_roundtrip(self) -> None:
        original = self.values(memo='점심, "친구"\n둘째 줄')
        path = self.write_csv([original, self.values(date="2026-09-30")])
        self.assertEqual(self.service.import_csv(path), 2)
        exported = self.directory / "output.csv"
        self.assertEqual(self.service.export_csv(exported, month="2026-10"), 1)
        other = BudgetService(Repository(self.directory / "other"))
        self.assertEqual(other.import_csv(exported), 1)
        item = next(other.search())
        self.assertEqual(item.memo, original["memo"])
        self.assertEqual(item.tags, ["식사", "학교"])
        self.assertEqual(self.service.export_csv(exported, start="2026-09-30", end="2026-10-01"), 2)

    def test_bad_import_changes_nothing(self) -> None:
        self.service.add(self.values())
        before = self.service.repository.transactions.read_bytes()
        path = self.write_csv([self.values(), self.values(amount="-1")])
        with self.assertRaisesRegex(ValueError, "CSV 3행"):
            self.service.import_csv(path)
        self.assertEqual(self.service.repository.transactions.read_bytes(), before)
        path.write_text('date,type,category,amount\n2026-10-01,expense,food,"1000', encoding="utf-8")
        with self.assertRaises(csv.Error):
            self.service.import_csv(path)
        self.assertEqual(self.service.repository.transactions.read_bytes(), before)

    def test_failed_rewrite_preserves_original(self) -> None:
        self.service.add(self.values())
        path = self.service.repository.transactions
        before = path.read_bytes()

        def broken_rows():
            yield {"id": "임시 데이터"}
            raise OSError("저장 공간 부족")

        with self.assertRaises(OSError):
            write_rows(path, broken_rows())
        self.assertEqual(path.read_bytes(), before)
        with patch("budget_app.storage.os.replace", side_effect=OSError("교체 실패")):
            with self.assertRaises(OSError):
                self.service.change(next(self.service.search()).id)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list(path.parent.iterdir())), 3)

    def test_streaming_reads_only_requested_rows(self) -> None:
        item = self.service.add(self.values())
        with self.service.repository.transactions.open("a", encoding="utf-8") as target:
            target.write("손상된 뒤쪽 행\n")
        iterator = self.service.repository.iter_transactions()
        self.assertEqual(next(iterator).id, item.id)
        with self.assertRaises(ValueError):
            next(iterator)
        before = self.service.repository.transactions.read_bytes()
        with self.assertRaises(ValueError):
            self.service.add(self.values())
        self.assertEqual(self.service.repository.transactions.read_bytes(), before)

    def test_export_validation_preserves_existing_output(self) -> None:
        path = self.directory / "output.csv"
        path.write_text("기존 파일", encoding="utf-8")
        for conditions in [{}, {"month": "2026-13"},
                           {"month": "2026-10", "start": "2026-10-01"},
                           {"start": "2026-10-03", "end": "2026-10-01"}]:
            with self.subTest(conditions=conditions), self.assertRaises(ValueError):
                self.service.export_csv(path, **conditions)
            self.assertEqual(path.read_text(encoding="utf-8"), "기존 파일")
        with self.assertRaises(ValueError):
            self.service.export_csv(self.service.repository.transactions, month="2026-10")

    def test_cli_error_and_help(self) -> None:
        error = io.StringIO()
        with redirect_stderr(error):
            code = main(["--data-dir", str(self.directory / "data"), "delete", "--id", "missing"])
        self.assertNotEqual(code, 0)
        self.assertIn("[힌트]", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
        for command in [[], ["add"], ["list"], ["search"], ["summary"], ["update"],
                        ["delete"], ["import"], ["export"], ["category"], ["category", "add"],
                        ["category", "list"], ["category", "remove"], ["budget"],
                        ["budget", "set"], ["budget", "show"]]:
            result = subprocess.run([sys.executable, "-m", "budget_app", *command, "--help"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, "-m", "budget_app", "list", "--limit", "0"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[힌트]", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_workflow(self) -> None:
        def run(*arguments: str, user_input: str = "") -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, "-m", "budget_app", "--data-dir",
                                   str(self.directory / "data"), *arguments],
                                  input=user_input, capture_output=True, text=True)

        added = run("add", user_input="2026-10-01\nexpense\nfood\n1500\n점심\n학교\n")
        self.assertEqual(added.returncode, 0, added.stderr)
        identifier = added.stdout.split("id=")[-1].strip()
        self.assertIn(identifier, run("list", "--limit", "1").stdout)
        self.assertEqual(run("update", "--id", identifier, "--amount", "2000").returncode, 0)
        self.assertIn("2,000원", run("search", "--tag", "학교").stdout)
        self.assertEqual(run("budget", "set", "--month", "2026-10", "--amount", "1000").returncode, 0)
        self.assertIn("1,000원", run("budget", "show", "--month", "2026-10").stdout)
        self.assertIn("[경고]", run("summary", "--month", "2026-10").stdout)
        exported = self.directory / "workflow.csv"
        self.assertEqual(run("export", "--out", str(exported), "--month", "2026-10").returncode, 0)
        self.assertEqual(run("delete", "--id", identifier).returncode, 0)
        self.assertIn("데이터 없음", run("list").stdout)
        self.assertIn("imported=1", run("import", "--from", str(exported)).stdout)
        self.assertEqual(run("category", "add", user_input="도서\n").returncode, 0)
        self.assertIn("도서", run("category", "list").stdout)
        self.assertEqual(run("category", "remove", user_input="도서\n").returncode, 0)
        for result in [run("delete", "--id", "missing"),
                       run("import", "--from", str(self.directory / "missing.csv")),
                       run("add", user_input="")]:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("[오류]", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_add_retries_each_invalid_field(self) -> None:
        entries = ["2026-02-30", "2026-10-01", "other", "expense",
                   "unknown", "food", "0", "-1", "1500", "점심", "학교"]
        prompts = []
        output = io.StringIO()

        def enter(prompt: str) -> str:
            prompts.append(prompt)
            return entries[len(prompts) - 1]

        with patch("builtins.input", side_effect=enter), redirect_stdout(output):
            code = main(["--data-dir", str(self.directory / "data"), "add"])
        self.assertEqual(code, 0)
        self.assertEqual(prompts[0], prompts[1])
        self.assertEqual(prompts[2], prompts[3])
        self.assertEqual(prompts[4], prompts[5])
        self.assertEqual(prompts[6:9], ["금액(양수 정수): "] * 3)
        self.assertEqual(output.getvalue().count("[오류]"), 5)
        saved = list(self.service.search())
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0].date, saved[0].amount, saved[0].memo),
                         ("2026-10-01", 1500, "점심"))

    def test_add_cancellation_preserves_existing_data(self) -> None:
        self.service.add(self.values())
        before = self.service.repository.transactions.read_bytes()
        for interruption in (EOFError(), KeyboardInterrupt()):
            with self.subTest(interruption=type(interruption).__name__):
                with patch("builtins.input", side_effect=["bad-date", interruption]), \
                        redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    code = main(["--data-dir", str(self.directory / "data"), "add"])
                self.assertNotEqual(code, 0)
                self.assertEqual(self.service.repository.transactions.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
