# AGENTS.md

## Commands

    make setup           # deps install; create a venv first: virtualenv .venv
    make unit            # pytest tests/unit/ with -vvl --showlocals
    make test            # unit + pre-commit-all + integration (integration suite currently empty)
    make run             # python -m powerdns_api_proxy --reload; needs PROXY_CONFIG_PATH set
    .venv/bin/python -m pytest tests/unit/config_test.py -v   # single test file

## Gotchas

- Config is loaded at import time (`proxy.py`, `middleware.py`, `metrics.py`
  call `load_config()` at module level). `PROXY_CONFIG_PATH` must point at a
  valid YAML config before importing `powerdns_api_proxy.proxy` (tests set it
  manually before import, see tests/unit/middleware_test.py;
  `config-example.yml` works).
- The lint gate is `.pre-commit-config.yaml` (ruff, ruff-format, mypy with
  --ignore-missing-imports, pyupgrade, hadolint).
- Pre-existing, don't chase: mypy flags `verify_ssl=` in
  `pdns.py session.request()` — it exists on main; pre-commit still passes.
- `no-commit-to-branch` hook blocks direct commits to main — work on a branch.
- LOG_LEVEL defaults to DEBUG and LOG_FILE defaults to a `log` file; set
  LOG_FILE=false when running local copies to avoid writing log files.

## Conventions

Conventional Commits (`type(scope): description`) are required, feature/config
changes need an approved issue first, and `make test` must pass before a PR.
See CONTRIBUTING.md — it is the source of truth for these rules.
