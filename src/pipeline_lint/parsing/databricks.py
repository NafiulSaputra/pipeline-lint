"""Databricks notebooks exported in source format (``.py`` files)."""

from __future__ import annotations

NOTEBOOK_HEADER = "# Databricks notebook source"


def is_databricks_notebook(text: str) -> bool:
    """Return True if the first non-empty line is the Databricks source-format header."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped == NOTEBOOK_HEADER
    return False
