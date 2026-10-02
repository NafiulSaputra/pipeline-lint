"""Find the files to lint."""

from __future__ import annotations

import errno
import os
from collections.abc import Iterable, Sequence
from fnmatch import fnmatchcase
from pathlib import Path

SUPPORTED_SUFFIXES = frozenset({".sql", ".py"})

# Directories that never contain user pipeline code. Hidden directories (".git", ".venv", ...)
# are skipped as well.
SKIPPED_DIRS = frozenset(
    {"__pycache__", "venv", "env", "node_modules", "build", "dist", "site-packages"}
)


def discover_files(paths: Iterable[Path], exclude: Sequence[str] = ()) -> list[Path]:
    """Return every supported file under ``paths``, sorted and without duplicates.

    Files passed explicitly are included even if they live in a skipped directory, because
    the user asked for them. ``exclude`` holds glob patterns matched against POSIX-style paths.
    """
    found: set[Path] = set()
    for root in paths:
        if not root.exists():
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(root))

        if root.is_file():
            if _is_supported(root) and not _is_excluded(root, exclude):
                found.add(root)
            continue

        # os.walk lets us prune directories in place, so we never descend into a large
        # virtual environment just to throw its contents away.
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if not _is_skipped_dir(d))
            for filename in filenames:
                path = Path(dirpath) / filename
                if _is_supported(path) and not _is_excluded(path, exclude):
                    found.add(path)

    return sorted(found)


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def _is_skipped_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIPPED_DIRS


def _is_excluded(path: Path, patterns: Sequence[str]) -> bool:
    posix = path.as_posix().removeprefix("./")
    return any(fnmatchcase(posix, pattern) for pattern in patterns)
