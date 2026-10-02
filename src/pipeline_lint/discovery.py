"""Find the files to lint."""

from __future__ import annotations

import errno
import os
from collections.abc import Iterable, Sequence
from contextlib import suppress
from fnmatch import fnmatchcase
from pathlib import Path

SUPPORTED_SUFFIXES = frozenset({".sql", ".py"})

# Directories that never contain user pipeline code. Hidden directories (".git", ".venv", ...)
# are skipped as well.
SKIPPED_DIRS = frozenset(
    {"__pycache__", "venv", "env", "node_modules", "build", "dist", "site-packages"}
)


def discover_files(
    paths: Iterable[Path], exclude: Sequence[str] = (), root: Path | None = None
) -> list[Path]:
    """Return every supported file under ``paths``, sorted and without duplicates.

    ``exclude`` holds glob patterns matched against POSIX-style paths, both as given and
    relative to ``root`` (the directory of the config file). Like Ruff, excludes apply to
    files found by walking directories; a file passed explicitly is always checked, because
    the user (or pre-commit) asked for exactly that file.
    """
    found: set[Path] = set()
    for target in paths:
        if not target.exists():
            raise FileNotFoundError(errno.ENOENT, "No such file or directory", str(target))

        if target.is_file():
            if _is_supported(target):
                found.add(target)
            continue

        # os.walk lets us prune directories in place, so we never descend into a large
        # virtual environment just to throw its contents away.
        for dirpath, dirnames, filenames in os.walk(target):
            dirnames[:] = sorted(d for d in dirnames if not _is_skipped_dir(d))
            for filename in filenames:
                path = Path(dirpath) / filename
                if _is_supported(path) and not _is_excluded(path, exclude, root):
                    found.add(path)

    return sorted(found)


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def _is_skipped_dir(name: str) -> bool:
    return name.startswith(".") or name in SKIPPED_DIRS


def _is_excluded(path: Path, patterns: Sequence[str], root: Path | None) -> bool:
    if not patterns:
        return False
    candidates = [path.as_posix().removeprefix("./")]
    if root is not None:
        with suppress(ValueError):  # ValueError: the file lives outside the project root
            candidates.append(path.resolve().relative_to(root.resolve()).as_posix())
    return any(fnmatchcase(c, pattern) for c in candidates for pattern in patterns)
