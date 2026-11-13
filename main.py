#!/usr/bin/env python3
"""Entry point, including isolated (-I) installed launchers."""

from pathlib import Path
import sys

if sys.version_info < (3, 9):
    raise SystemExit("今日运势需要 Python 3.9 或更新版本。")

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_fortune.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
