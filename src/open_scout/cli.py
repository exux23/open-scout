import argparse
import json
import sys
from uuid import uuid4

from .config import Settings
from .crawler import Crawler
from .schemas import CrawlRequest, SearchRequest
from .search import Engine
from .store import Store, now


def main():
    parser = argparse.ArgumentParser(description="Open Scout — your own web search index")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Start the API and browser workspace")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    crawl = sub.add_parser("crawl", help="Crawl public seed URLs")
    crawl.add_argument("urls", nargs="+")
    crawl.add_argument("--max-pages", type=int, default=20)
    crawl.add_argument("--depth", type=int, default=1)
    search = sub.add_parser("search", help="Search the local index")
    search.add_argument("query")
    search.add_argument("--type", choices=["auto", "keyword", "neural", "hybrid"], default="auto")
    sub.add_parser("reindex", help="Download the neural model and embed all stored documents")
    sub.add_parser("stats", help="Show index statistics")
    args = parser.parse_args()
    settings = Settings()
    if args.command == "serve":
        if args.host not in ("127.0.0.1", "::1", "localhost") and len(settings.api_key) < 24:
            parser.error(
                "Set SCOUT_API_KEY to at least 24 characters before binding beyond loopback"
            )
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port)
        return
    if args.command == "reindex":
        settings.neural = True
    store = Store(settings.data_dir)
    engine = Engine(store, settings)
    if args.command == "crawl":
        job = {
            "id": str(uuid4()),
            "status": "queued",
            "createdAt": now(),
            "attempted": 0,
            "indexed": 0,
            "errors": [],
            "urls": args.urls,
            "maxPages": args.max_pages,
            "currentUrl": None,
        }
        Crawler(engine).run(
            CrawlRequest(urls=args.urls, maxPages=args.max_pages, maxDepth=args.depth),
            job,
            store.save_job,
        )
        print(json.dumps(job, indent=2))
        if not job["indexed"]:
            sys.exit(1)
    elif args.command == "search":
        print(json.dumps(engine.search(SearchRequest(query=args.query, type=args.type)), indent=2))
    elif args.command == "reindex":
        documents = store.documents()
        for i, doc in enumerate(documents, 1):
            engine.index(doc)
            print(f"[{i}/{len(documents)}] {doc['url']}", file=sys.stderr)
        if not documents:
            with engine.embedder.lock:
                engine.embedder.load()
        print(json.dumps(store.stats(settings.model)))
    elif args.command == "stats":
        print(json.dumps(store.stats(settings.model), indent=2))
