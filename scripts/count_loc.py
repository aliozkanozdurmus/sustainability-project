#!/usr/bin/env python3
"""
Count non-empty lines of code in the repository, skipping vendor and build artifacts.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

SKIP_DIR_NAMES = {
    ".git",
    "node_modules",
    "output",
    "tmp",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    ".turbo",
}

INCLUDE_EXTS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".json",
    ".yml",
    ".yaml",
    ".md",
    ".html",
    ".css",
    ".scss",
    ".go",
    ".rs",
    ".java",
    ".kt",
}


def iter_code_files(root: Path):
    """Yield code file paths under root while pruning skipped folders."""

    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        for name in files:
            path = Path(current_root, name)
            if path.suffix.lower() not in INCLUDE_EXTS:
                continue
            yield path


def count_loc(root: Path) -> tuple[int, int]:
    files_counted = 0
    line_count = 0

    for path in iter_code_files(root):
        files_counted += 1
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip():
                        line_count += 1
        except (OSError, UnicodeDecodeError):
            # Skip unreadable files without stopping the run.
            continue

    return files_counted, line_count


def main():
    parser = argparse.ArgumentParser(description="Count project lines of code")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="project root (defaults to repository root)",
    )
    args = parser.parse_args()

    files_counted, line_count = count_loc(args.root)
    print(f"files scanned: {files_counted}")
    print(f"result completed: {line_count}")


if __name__ == "__main__":
    main()
