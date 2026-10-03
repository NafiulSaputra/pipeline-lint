# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-03

### Added

- `pipeline-lint check` command for SQL files, PySpark code and Databricks source-format
  notebooks, including SQL inside `spark.sql("...")` calls and `%sql` cells.
- Rules:
  - DE001 `non-idempotent-append`: append-only writes that duplicate data on re-run.
  - DE002 `unscoped-overwrite`: overwrites that replace the entire table.
  - DE003 `hardcoded-date`: literal dates in filters of scheduled queries.
  - DE004 `select-star-into-write`: `SELECT *` deciding which columns are written.
  - DE005 `driver-collect`: `collect()` / `toPandas()` on unbounded DataFrames.
  - DE006 `airflow-missing-retries`: Airflow DAGs without retries.
  - DE007 `airflow-unsafe-catchup`: `catchup=True` with a missing or dynamic `start_date`.
- Jinja (`{{ ... }}`, `{% ... %}`) and `${var}` templates in SQL are masked before parsing.
- Text, JSON and SARIF 2.1.0 output; `--output` to write reports to a file.
- Configuration in `[tool.pipeline-lint]` (`select`, `ignore`, `exclude`, `sql-dialect`,
  `fail-on`) and matching CLI options.
- Per-line suppression with `# noqa: DE001` / `-- noqa: DE001`.
- `pipeline-lint rules` command.
- pre-commit hook definition.

[0.1.0]: https://github.com/NafiulSaputra/pipeline-lint/releases/tag/v0.1.0
