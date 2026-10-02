from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_lint.discovery import discover_files


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_finds_supported_files_recursively(tmp_path: Path) -> None:
    job = touch(tmp_path / "jobs" / "load.py")
    query = touch(tmp_path / "sql" / "orders.SQL")
    touch(tmp_path / "README.md")
    touch(tmp_path / "config.yaml")

    assert discover_files([tmp_path]) == sorted([job, query])


def test_skips_hidden_and_tooling_directories(tmp_path: Path) -> None:
    keep = touch(tmp_path / "pipeline.py")
    touch(tmp_path / ".venv" / "lib" / "site.py")
    touch(tmp_path / ".git" / "hooks" / "hook.py")
    touch(tmp_path / "__pycache__" / "x.py")
    touch(tmp_path / "node_modules" / "pkg" / "x.py")

    assert discover_files([tmp_path]) == [keep]


def test_explicit_file_is_included_even_in_skipped_directory(tmp_path: Path) -> None:
    hidden = touch(tmp_path / ".scratch" / "notebook.py")
    assert discover_files([hidden]) == [hidden]


def test_explicit_unsupported_file_is_ignored(tmp_path: Path) -> None:
    assert discover_files([touch(tmp_path / "notes.txt")]) == []


def test_exclude_globs(tmp_path: Path) -> None:
    keep = touch(tmp_path / "jobs" / "load.py")
    touch(tmp_path / "jobs" / "scratch" / "tmp.py")

    found = discover_files([tmp_path], exclude=["*/scratch/*"])

    assert found == [keep]


def test_duplicates_are_removed(tmp_path: Path) -> None:
    job = touch(tmp_path / "load.py")
    assert discover_files([tmp_path, job]) == [job]


def test_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        discover_files([tmp_path / "missing"])
