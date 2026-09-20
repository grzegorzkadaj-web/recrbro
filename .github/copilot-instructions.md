# Copilot instructions for `recrbro`

## Project overview

`recrbro` is a small Python application for helping job seekers discover relevant job offers from LinkedIn and other sources. The requirements describe a product that:

- lets users sign in or create an account,
- loads a CV/PDF and extracts skills and languages,
- accepts filtering criteria such as location, work mode, salary, and contract type,
- queues and runs job searches,
- presents results and tracks token cost.

The current codebase is intentionally minimal: it is a Python package under `src/recrbro` with a single entry point at `src/recrbro/__init__.py`.

## Setup and commands

Use `uv` for dependency management and command execution, because the project is configured as a `uv`-managed Python package.

- Install dependencies: `uv sync`
- Run the app: `uv run recrbro`
- Build the package: `uv build`
- Format code: `uv run black .` and `uv run isort .`

### Tests and linting

There is no explicit test suite or lint command configured in this repository right now. The project does not currently define `pytest`, `tox`, `nox`, or an equivalent lint configuration in `pyproject.toml`.

If a test runner is added later, prefer the single-test form:

- `uv run pytest path/to/test_file.py -k "test_name"`

This keeps validation focused while the repo is still small.

## Architecture

The important architectural fact is that this is a single-package Python app, not a multi-service or multi-module system.

- Source code lives under `src/recrbro/`.
- The public console entry point is defined in `pyproject.toml` as `recrbro = "recrbro:main"`.
- The actual implementation currently lives in `src/recrbro/__init__.py` via the `main()` function.
- The project uses a `src/` layout, so keep new code under `src/recrbro` rather than at the repository root.
- A local `.env` file exists in `src/recrbro/.env`; keep secrets and environment-specific values out of the repo and treat them as deployment/runtime configuration rather than app logic.

The repository is still at the prototype stage: requirements are broader than the code, and most of the product is planned rather than implemented. Prefer simple, focused changes that stay compatible with a small package structure.

## Conventions and repository-specific patterns

- Keep the project Python 3.10+ compatible (`requires-python = ">=3.10"`).
- Prefer `uv` commands over raw `python`/`pip` to match the project toolchain.
- Avoid introducing new top-level modules unless the project clearly grows beyond the current package structure.
- Keep environment and secrets handling separate from application logic.
- The repo already includes `black` and `isort` as dependencies, so prefer formatting that matches those tools when adding code.
- Maintain the small-project conventions: minimal dependencies, no unnecessary framework scaffolding, and no broad refactors while the app is still in an early state.

## Working style expectations

When making changes:

- update the Python package under `src/recrbro`, not the repo root,
- keep feature additions aligned with the stated job-search use case,
- do not assume a large web app or multi-service architecture exists yet,
- prefer direct, obvious code that matches the minimal structure of the repository.
