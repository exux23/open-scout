FROM python:3.12-slim
ARG SCOUT_EXTRAS=""
ENV PYTHONUNBUFFERED=1 SCOUT_DATA_DIR=/data
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN if [ -n "$SCOUT_EXTRAS" ]; then uv sync --locked --no-dev --extra "$SCOUT_EXTRAS"; else uv sync --locked --no-dev; fi
RUN useradd --create-home --uid 10001 scout && mkdir /data && chown scout:scout /data
USER scout
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD /app/.venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["/app/.venv/bin/scout", "serve", "--host", "0.0.0.0"]
