import csv
import sys
from collections.abc import Callable
from functools import wraps


def handle_errors(function: Callable[..., int]) -> Callable[..., int]:
    @wraps(function)
    def wrapper(*args, **kwargs) -> int:
        try:
            return function(*args, **kwargs)
        except (ValueError, OSError, UnicodeError, csv.Error) as error:
            print(f"[오류] {error}", file=sys.stderr)
            print("[힌트] 입력 형식, 파일 내용과 경로·권한을 확인하세요. --help로 사용법을 볼 수 있습니다.",
                  file=sys.stderr)
            return 1
        except (EOFError, KeyboardInterrupt):
            print("\n[오류] 입력이 취소되었습니다. 명령을 다시 실행하세요.", file=sys.stderr)
            return 1
    return wrapper
