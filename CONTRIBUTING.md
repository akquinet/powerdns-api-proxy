# Contributing

Thanks for your interest in improving PowerDNS-API-Proxy.

## Before you start

The most important rule: **discuss large changes in an issue before writing code.**

We want decisions and architecture to be agreed on first, so reviewers are not
faced with a huge pull request that needs to be reworked. A pull request is a
place to review a finished, agreed-upon change, not the place to design it.

## Small vs. large changes

### Small change: open a pull request directly

These do **not** need a prior issue:

- A bug fix (including an isolated fix of a few lines)
- Typo and documentation fixes
- Test additions or fixes
- Dependency bumps (usually automated via Renovate)
- Small, isolated changes that do not alter public behavior

A small change should not introduce new behavior, new API endpoints, new
configuration options, or new dependencies.

### Large change: open an issue first

Open an issue and wait for a maintainer to agree on the approach **before**
opening a pull request:

- New features
- Refactorings
- Changes to public API or behavior
- New configuration options
- New dependencies
- Breaking changes
- Security-sensitive changes
- Changes that span multiple modules
- Anything where the "right" approach is unclear

In the issue, describe the problem, the proposed approach, alternatives you
considered, and the intended scope. Once the approach is agreed upon, a
maintainer will tell you to go ahead and a pull request is welcome.

If in doubt, open an issue. It costs a little time and saves a lot of review.

## Development setup

```bash
virtualenv .venv && source .venv/bin/activate
make setup
```

## Running tests

```bash
make unit            # unit tests
make test            # unit + pre-commit + integration
```

Please make sure `make test` passes before opening a pull request.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): description`.

Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`,
`ci`, `chore`.

Example: `fix(parser): handle empty input`.

## Pull request checklist

- [ ] The change is either a small change, or it links an approved issue.
- [ ] `make test` passes.
- [ ] Tests were added or updated where it makes sense.
- [ ] Documentation (`README.md`, config examples) was updated where needed.
