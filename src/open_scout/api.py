import hmac
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import Settings
from .crawler import Crawler, CrawlError, normalize_url
from .schemas import ContentsRequest, CrawlRequest, SearchRequest, SimilarRequest
from .search import Engine, NeuralUnavailable, result
from .store import Store, now


def create_app(settings=None):
    settings = settings or Settings()
    store = Store(settings.data_dir)
    engine = Engine(store, settings)
    worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scout-crawl")
    busy = Lock()

    @asynccontextmanager
    async def lifespan(app):
        for job in store.jobs():
            if job["status"] in ("queued", "running"):
                job.update(status="interrupted", currentUrl=None)
                store.save_job(job)
        yield
        worker.shutdown(wait=True)

    app = FastAPI(
        title="Open Scout",
        version="0.1.0",
        lifespan=lifespan,
        description="Search your own web index. Independent Exa-inspired API subset.",
    )
    app.state.engine = engine
    app.state.store = store
    if not settings.api_key:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    def authorize(x_api_key: str = Header(default="")):
        if settings.api_key and not hmac.compare_digest(
            x_api_key.encode(), settings.api_key.encode()
        ):
            raise HTTPException(401, "Invalid or missing x-api-key")

    auth = [Depends(authorize)]

    @app.middleware("http")
    async def headers(request, call_next):
        # JSON-only mutations prevent cross-origin HTML forms from driving an unkeyed local API.
        if request.method == "POST":
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Use application/json"}, status_code=415)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse({"detail": "Request exceeds 64 KiB"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
            if request.url.path not in ("/docs", "/redoc")
            else "frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(NeuralUnavailable)
    async def neural_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(CrawlError)
    async def url_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/stats", dependencies=auth)
    def stats():
        return {
            **store.stats(settings.model),
            "neuralEnabled": settings.neural,
            "model": settings.model if settings.neural else None,
        }

    @app.post("/search", dependencies=auth)
    def search(request: SearchRequest):
        return engine.search(request)

    @app.post("/contents", dependencies=auth)
    def contents(request: ContentsRequest):
        results, statuses = [], []
        for url in request.urls:
            url = normalize_url(url)
            doc = store.get(url)
            statuses.append({"url": url, "status": "success" if doc else "not_indexed"})
            if doc:
                results.append(result(doc, options=request))
        return {"requestId": str(uuid4()), "results": results, "statuses": statuses}

    @app.post("/findSimilar", dependencies=auth)
    def similar(request: SimilarRequest):
        url = normalize_url(request.url)
        doc = store.get(url)
        if not doc:
            raise HTTPException(404, "Source URL is not indexed. Crawl it first.")
        query = f"{doc['title']} {doc['text']}"[:2000]
        return engine.search(
            SearchRequest(
                query=query,
                numResults=request.numResults,
                includeDomains=request.includeDomains,
                excludeDomains=request.excludeDomains,
            ),
            exclude_url=url,
        )

    def run_crawl(request, job):
        try:
            Crawler(engine).run(request, job, store.save_job)
        except Exception as exc:
            job.update(status="failed", currentUrl=None)
            job["errors"].append({"url": "", "error": str(exc)[:400]})
        finally:
            job["finishedAt"] = now()
            store.save_job(job)
            busy.release()

    @app.post("/crawl", status_code=202, dependencies=auth)
    def crawl(request: CrawlRequest):
        request.urls = [normalize_url(url) for url in request.urls]
        if not busy.acquire(blocking=False):
            raise HTTPException(409, "A crawl is already running. Wait for it to complete.")
        job = {
            "id": str(uuid4()),
            "status": "queued",
            "urls": request.urls,
            "attempted": 0,
            "indexed": 0,
            "errors": [],
            "createdAt": now(),
            "maxPages": request.maxPages,
            "currentUrl": None,
        }
        try:
            store.save_job(job)
            worker.submit(run_crawl, request, job)
        except Exception:
            busy.release()
            raise
        return job

    @app.get("/crawl", dependencies=auth)
    def jobs():
        return {"jobs": store.jobs()}

    @app.get("/crawl/{job_id}", dependencies=auth)
    def job_status(job_id: str):
        for job in store.jobs():
            if job["id"] == job_id:
                return job
        raise HTTPException(404, "Crawl job not found")

    @app.delete("/documents/{doc_id}", dependencies=auth)
    def delete(doc_id: str):
        if not store.delete(doc_id):
            raise HTTPException(404, "Document not found")
        return {"deleted": doc_id}

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    return app
