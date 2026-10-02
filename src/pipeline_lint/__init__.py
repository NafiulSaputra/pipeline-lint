"""pipeline-lint: catch rerun-safety and data-correctness issues in data pipeline code."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pipeline-lint")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
