#!/usr/bin/env python3
"""販売パッケージ展開後にも使える自己試験。"""

from __future__ import annotations

import pathlib
import sys
import unittest


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

