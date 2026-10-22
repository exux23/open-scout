# Verification

Performed on October 22, 2026 on Windows with Python 3.12.14. Live checks used
public documentation websites and a local API; no Exa API key or paid API was used.

## Automated checks

- 51 pytest tests passed; total measured Python coverage: 81%.
- Ruff lint and formatting checks passed.
- Source distribution and wheel built successfully with `uv build`.
- Tests cover persisted/upserted/deleted documents, BM25 results, domain filtering
  before result limits, hostile FTS input, vector ranking/fusion, incomplete neural
  index errors, contents and similar-page behavior, API validation/authentication,
  DNS rebinding Host rejection, crawl jobs and restart recovery, MCP tool mapping,
  private/mixed DNS rejection, pinned TLS host verification, redirect validation,
  robots rules/error responses, crawl limits, extraction, noindex recrawl removal,
  response size limits, and bounded gzip decompression.
- Unit neural ranking tests use deterministic fixture vectors. The actual model
  was checked separately below; fixture tests are not claimed as model evaluation.
- A non-failing dependency warning reports Starlette's planned move from httpx to
  httpx2 in its test client. Runtime API requests were also tested independently.

## Live model and crawl checks

1. A bounded crawl indexed 11 public pages from FastAPI and SQLite. The first pass
   exposed a gzip response despite `Accept-Encoding: identity`; bounded gzip/deflate
   support and regression tests were added. The Python homepage was successfully
   crawled again afterward, along with Python's asyncio documentation.
2. `scout reindex` downloaded the real BGE-small ONNX model and created embeddings
   for all 11 initial documents. Subsequent API crawls embedded new pages automatically.
3. An explicit neural query, "embedded SQL database that runs without a separate
   server", ranked `https://www.sqlite.org/index.html` first.
4. A real MCP stdio client initialized the server, enumerated all three tools, called
   `search` with neural mode, and received the same SQLite page as its top result.

These checks establish functioning local inference and end-to-end data flow. They
are not a relevance benchmark or evidence of parity with Exa's ranking or coverage.

## Browser and packaging

The browser workspace was exercised in the Codex browser at a narrow viewport:
search submission, loading state, ranked results, full-text source inspector with
source URL and crawl time, crawl form submission, and persistent job history.

`docker build -t open-scout:local .` completed on Docker Desktop's Linux engine.
A temporary container ran as the image's non-root user and passed checks for health,
packaged UI, unauthorized rejection, and authenticated stats/search. The temporary
container was stopped after verification. The neural-extra container variant was
not separately built; neural inference was exercised in the Windows installation.

The repository CI runs lint, formatting, tests, and package builds on Windows and
Ubuntu with Python 3.12 and 3.13. Refer to the GitHub Actions run for remote results.
Neither load testing nor an independent security audit has been performed.
