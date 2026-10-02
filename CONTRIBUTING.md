# Contributing to pipeline-lint

Thanks for your interest in improving pipeline-lint. Bug reports, false-positive reports and
new rule ideas are all welcome as [issues](https://github.com/NafiulSaputra/pipeline-lint/issues).

## Development setup

You need [uv](https://docs.astral.sh/uv/) and Git.

```bash
git clone https://github.com/NafiulSaputra/pipeline-lint
cd pipeline-lint
uv sync                    # creates .venv with all dependencies
uv run pre-commit install  # runs ruff and pipeline-lint before every commit
```

Common commands:

```bash
uv run pytest                          # run the test suite
uv run pytest --cov                    # with coverage
uv run ruff format . && uv run ruff check .
uv run pipeline-lint check examples/   # try the CLI
```

CI runs the same checks on Python 3.11-3.13, on Linux and Windows.

## Reporting a false positive

A rule that reports correct code is a bug, even if the rule is "technically right". Please
include the smallest code snippet that triggers it and explain why the code is safe. False
positives are fixed before new rules are added.

## Adding a rule

Each rule is one module, one set of fixture files and one documentation page.

1. **Discuss first.** Open an issue describing the mistake, why it breaks pipelines, and how it
   can be detected *without* guessing. Rules must have a low false-positive rate.

2. **Write the rule** in `src/pipeline_lint/rules/deNNN_<name>.py`:

   ```python
   @register
   class MyRule(Rule):
       id = "DE008"
       name = "my-rule"
       severity = Severity.WARNING
       summary = "One line describing the problem"
       rationale = "Why this breaks pipelines in production."
       bad_example = "..."
       good_example = "..."

       def check_sql(self, source: SourceFile) -> Iterator[Violation]: ...
       def check_python(self, source: SourceFile) -> Iterator[Violation]: ...
   ```

   Implement only the methods that apply. Shared helpers live in `src/pipeline_lint/parsing/`.
   Import the module in `src/pipeline_lint/rules/__init__.py` to register it.

3. **Add fixtures** in `tests/fixtures/DE008/`. Files starting with `bad_` mark every offending
   line with an annotation; files starting with `good_` must produce no violations:

   ```sql
   INSERT INTO analytics.orders SELECT * FROM staging.orders;  -- expect: DE008
   ```

   ```python
   rows = df.collect()  # expect: DE008
   ```

   `tests/rules/test_fixtures.py` picks them up automatically. Make the examples realistic:
   the kind of code a person or an assistant would actually write.

4. **Add unit tests** in `tests/rules/test_de008.py` for edge cases that are clearer inline.

5. **Document it** in `docs/rules/DE008.md` (same structure as the existing pages), add a row to
   the rules table in `README.md`, and an entry under "Unreleased" in `CHANGELOG.md`.

## Pull requests

- Keep each pull request focused on one change.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages, e.g.
  `feat: add DE008 merge-without-key rule`, `fix: DE003 false positive on ...`, `docs: ...`.
- Make sure `uv run pytest` and `uv run ruff check .` pass. CI must be green before merging.

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
