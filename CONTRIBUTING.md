# Contributing

Use Python 3.12 or 3.13 and uv. Install with `uv sync --locked --group dev`, then run
`uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .`.

Tests must not crawl public sites or download models. Test crawler behavior with
fixtures and network transports with mocks. Document any opt-in live validation
separately. Never commit crawl databases, model caches, `.env`, API keys, or local logs.

Changes to API behavior should update the README and tests together. Keep unsupported
fields explicit, preserve public-IP pinning and robots checks, and make model/download
requirements visible. Issues and pull requests are welcome.
