# pipeline-lint

Data pipeline linter for SQL, PySpark, Databricks and Airflow. Catches non-idempotent writes,
duplicate data on rerun, and other mistakes AI-generated pipelines make.

> **Status:** early development (v0.1.0.dev0). Full documentation will be added before the first release.
> See [docs/design.md](docs/design.md) for the design specification.

## Quick start (development)

```bash
uv sync
uv run pytest
uv run pipeline-lint check examples/
```
