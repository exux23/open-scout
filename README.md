# Open Scout

An independent, self-hosted web search engine for people and AI agents.

MIT-licensed. No paid search API. Crawl public websites into your own SQLite index,
search with BM25 or a local neural model, and read clean page text through a browser,
HTTP API, CLI, or MCP tools.

This is a small-corpus search engine, not Exa's global web index or proprietary models.
Its API implements a documented Exa-inspired subset, not full SDK compatibility.

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone https://github.com/exux23/open-scout.git
cd open-scout
uv sync --locked
uv run scout serve
```

Open <http://127.0.0.1:8000>. Add seed URLs in **Crawl**, then search the indexed pages.
The index starts empty. You can also crawl from the command line:

```sh
uv run scout crawl https://www.python.org/ --max-pages 10 --depth 1
uv run scout search "programming language"
```

## Local neural search

```sh
uv sync --locked --extra neural
uv run scout reindex
```

Copy `.env.example` to `.env` and set `SCOUT_NEURAL=true`, then restart the server.
First use downloads the open BAAI/bge-small-en-v1.5 ONNX embedding model into `data/models`.
Inference runs locally on CPU. No model API key is needed. New crawls embed automatically
when neural mode is enabled. Run reindex with the server stopped after enabling/changing models.
The default model is English-focused and independently licensed by its publisher.

## API

Interactive OpenAPI documentation: <http://127.0.0.1:8000/docs>.

```sh
curl http://127.0.0.1:8000/search -H "Content-Type: application/json" \
  -d '{"query":"programming language","type":"auto","numResults":5}'
curl http://127.0.0.1:8000/contents -H "Content-Type: application/json" \
  -d '{"urls":["https://www.python.org/"]}'
```

| Endpoint | Behavior |
| --- | --- |
| `POST /search` | `query`, `type` (auto/keyword/neural/hybrid), `numResults`, domain filters, contents options |
| `POST /contents` | Read already-indexed `urls`; per-URL status for missing pages |
| `POST /findSimilar` | Related pages for an indexed `url`, excluding the source |
| `POST /crawl` | Start a bounded crawl (`urls`, `maxPages`, `maxDepth`); returns a job ID |
| `GET /crawl`, `GET /crawl/{id}` | Persistent crawl progress and per-page errors |
| `GET /stats` | Page counts, domains, embedding coverage |
| `DELETE /documents/{id}` | Remove a page and its search/vector entries |
| `GET /health` | Public liveness endpoint |

Responses include source URLs, crawl timestamps, and plain-text highlights.
Scores are reciprocal-rank-fusion values, not calibrated relevance probabilities.
`auto` uses keyword retrieval unless neural mode is enabled. Explicit neural/hybrid
requests return 503 if disabled or incomplete; they never silently pretend to be neural.
Unknown request fields are rejected. Publication-date filtering, generated summaries,
live global search, reranking, and Exa's agent/webset APIs are not implemented.

## MCP for agents

Start the API, then configure an MCP client with:

```json
{
  "mcpServers": {
    "open-scout": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/open-scout", "run", "scout-mcp"],
      "env": {"SCOUT_API_URL": "http://127.0.0.1:8000"}
    }
  }
}
```

Tools: `search`, `get_contents`, `find_similar`. On Windows use an absolute Windows path
with JSON-escaped backslashes. Set `SCOUT_API_KEY` in the client environment if enabled.
Retrieved text is untrusted web content, not instructions for an agent.

## Deployment and data

The CLI binds to loopback by default. For network access, set a random `SCOUT_API_KEY`
of at least 24 characters and supply `--host 0.0.0.0`. Send the key in `x-api-key` or
enter it in the browser's connection settings. The browser keeps it only in memory.
Use HTTPS at a reverse proxy for remote access. This release is a single-user,
single-process service: run one API worker. Stop the API before CLI crawls/reindexing.
Do not expose an unkeyed server through direct `uvicorn` calls or port forwarding.

Docker (keyword mode):

```sh
docker compose up --build
```

Copy `.env.example` to `.env` and provide a strong `SCOUT_API_KEY` first.
Compose publishes only on host loopback; data persists in the `scout-data` volume.
For neural Docker builds set build arg `SCOUT_EXTRAS=neural` and `SCOUT_NEURAL=true`.

SQLite, crawled content, and models live under `SCOUT_DATA_DIR` (default `data/`) and
are gitignored. Back up the data directory with the service stopped. Crawled pages
retain their original authors' rights and are not part of this project's MIT license.

## Crawl policy and limits

- Respects robots.txt, crawl delays, noindex and nofollow. Unknown robots failures fail closed.
- Same seed hostnames only, including redirects. Add both apex and `www` URLs when needed.
- Public HTTP(S), ports 80/443 only. DNS answers are validated and connections pinned
  to a public IP, including redirects; no localhost, private networks, credentials, or proxies.
- One crawl at a time; at most 200 attempted pages, depth 3, 2 MiB per response,
  100,000 extracted characters/page, 2,000 pending links, and a 20-minute loop budget.
- HTML/plain text only. No JavaScript execution, login, paywall bypass, PDF parsing,
  sitemap ingestion, or automatic recrawl. Re-crawling a URL replaces its stored content.
- Jobs persist; a restart marks unfinished jobs interrupted, rather than claiming completion.

Neural retrieval scans stored chunk vectors with NumPy and uses the best chunk per page.
Keyword retrieval uses SQLite FTS5 BM25; hybrid retrieval fuses the two rankings.
This design is intended for thousands of pages. It has no ANN index, multi-tenant quotas,
distributed crawler, or production throughput benchmark.

## Development

```sh
uv sync --locked --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

See [the REA investigation](docs/rea-investigation.md), [architecture](docs/architecture.md),
and [verification](docs/verification.md) for evidence, implementation choices, and test scope.
