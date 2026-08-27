from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _write_crash(message: str) -> None:
    log_path = Path(__file__).resolve().parent.parent / "data" / "last_error.txt"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(message, encoding="utf-8")


def main() -> None:
    try:
        from app.gui import run_app

        run_app()
    except Exception:
        text = traceback.format_exc()
        _write_crash(text)
        print(text, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
