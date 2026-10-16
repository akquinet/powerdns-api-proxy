# AGENTS.md

uv is the recommended tool for Python package management in this repo. Run
tools through `uv run` (or the Makefile) so they use the locked environment.

## Commands

    make setup           # uv sync + install the prek Git hook
    make lint            # run all hooks via prek (ruff, mypy, hadolint, ...)
    make fmt             # ruff check --fix + ruff format
    make unit            # uv run pytest tests/unit/ with -vvl --showlocals
    make test            # lint + unit + integration (integration suite currently empty)
    make run             # uv run python -m powerdns_api_proxy --reload; needs PROXY_CONFIG_PATH set
    uv run pytest tests/unit/config_test.py -v   # single test file

## Gotchas

- Config is held by the `config_holder` singleton in `config.py`; consumers
  read it per request and SIGHUP swaps it (invalid files are logged and
  ignored). `proxy.py` loads it at import time, so `PROXY_CONFIG_PATH` must
  point at a valid YAML config before importing `powerdns_api_proxy.proxy`
  (tests set it manually before import, see tests/unit/middleware_test.py;
  `config-example.yml` works). Tests swap configs by patching
  `config_holder._config`.
- The lint gate is `make lint`, which runs [prek](https://prek.j178.dev/) on
  `.pre-commit-config.yaml` (a drop-in, faster pre-commit; ruff, pyupgrade,
  mypy, hadolint, and pre-commit-hooks). The `hadolint-docker` hook needs a
  running Docker daemon. Dependencies live in `pyproject.toml` and are pinned by
  `uv.lock`; there are no requirements.txt files.
- `pdns.py` has a `# type: ignore[call-arg]` on `verify_ssl=`: aiohttp accepts
  the kwarg at runtime but its type stubs don't, so mypy needs the suppression.
- LOG_LEVEL defaults to DEBUG and LOG_FILE defaults to a `log` file; set
  LOG_FILE=false when running local copies to avoid writing log files.

## Conventions

Conventional Commits (`type(scope): description`) are required, feature/config
changes need an approved issue first, and `make test` must pass before a PR.
See CONTRIBUTING.md — it is the source of truth for these rules.
