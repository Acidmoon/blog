# Repository Guidelines

## Project Structure & Module Organization

This is a Flask blog app. `app.py` creates the application, registers blueprints, and applies global request guards. Route handlers live in `routes/`, while reusable business logic lives in `services/`. Database setup and connection helpers are in `models.py`. Pluggable home/admin modules live under `modules/*/manifest.py`. Templates are in `templates/`, grouped by page area; static assets are in `static/`, with CSS split into `static/css/components/` and imported by `static/css/style.css`. Tests are in `tests/`. Runtime content and uploads live under `data/` and are intentionally ignored.

## Build, Test, and Development Commands

- `docker compose up -d --build` builds and starts the blog container on port `8082`.
- `docker compose logs -f blog` tails the running app logs.
- `docker compose restart blog` restarts Gunicorn after environment/config-level changes.
- `pytest -q` runs the test suite from the host development environment.
- `pytest -q tests/test_smoke.py::test_name` runs a focused smoke test.
- `codegraph status /root/blog` verifies the local CodeGraph index.

The project normally runs in Docker; do not start a separate local Flask server unless explicitly requested.

## Coding Style & Naming Conventions

Use 4-space indentation for Python. Keep route handlers thin and put shared behavior in `services/`. Use `snake_case` for Python functions and modules, clear blueprint names, and descriptive service helpers such as `list_drafts()` or `save_access_settings()`. Keep templates readable with semantic class names. Add CSS in the relevant component file rather than growing `style.css` directly. Keep user-facing Chinese copy concise and consistent with the existing tone.

## Testing Guidelines

Tests use `pytest` and Flask’s test client from `tests/conftest.py`. Name tests `test_*` and prefer focused smoke tests for routes, settings, auth, rendering, and service behavior. When changing persistence, verify both database state and rendered/API output. Run `pytest -q` before handing off; if only a narrow area changed, include the focused test command as well.

## Commit & Pull Request Guidelines

Recent history uses lightweight Conventional Commits, for example `feat(editor): ...`, `fix: ...`, `perf: ...`, and `chore: ...`. Keep commits scoped and behavior-focused. PRs should include a short summary, test results, screenshots for UI changes, and notes about any Docker, data, or configuration impact.

## Agent-Specific Notes

This repo has a local `.codegraph/` index. When exploring code, prefer `codegraph explore "<question>"` or `codegraph node <symbol-or-file>` before broad grep/read scans. Do not commit `.codegraph/`, `data/`, `.env`, caches, or uploaded assets.
