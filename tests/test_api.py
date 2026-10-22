import time

from fastapi.testclient import TestClient

from open_scout.api import create_app
from open_scout.config import Settings
from open_scout.store import Store


def seed(client):
    return client.app.state.engine.index(
        {
            "url": "https://example.com/",
            "domain": "example.com",
            "title": "Example",
            "text": "An example document about "
            "Python programming with useful explanations and examples.",
        }
    )


def test_health_and_static_workspace(client):
    assert client.get("/health").json()["status"] == "ok"
    root = client.get("/")
    assert root.status_code == 200
    assert "Search index" in root.text
    assert "frame-ancestors 'none'" in root.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert "/search" in client.get("/openapi.json").json()["paths"]


def test_contents_filters_and_delete(client):
    doc = seed(client)
    response = client.post("/search", json={"query": "Python"})
    assert response.status_code == 200
    assert response.json()["results"][0]["url"] == doc["url"]
    contents = client.post("/contents", json={"urls": [doc["url"], "https://missing.example/"]})
    assert len(contents.json()["results"]) == 1
    assert contents.json()["statuses"][1]["status"] == "not_indexed"
    assert client.delete(f"/documents/{doc['id']}").status_code == 200
    assert client.get("/stats").json()["documents"] == 0


def test_similar_excludes_source_and_missing_returns_404(client):
    doc = seed(client)
    assert client.post("/findSimilar", json={"url": doc["url"]}).json()["results"] == []
    assert client.post("/findSimilar", json={"url": "https://missing.example"}).status_code == 404


def test_validation_and_neural_errors(client):
    for body in [
        {"query": " "},
        {"query": "test", "numResults": 1000},
        {"query": "test", "madeUpField": True},
    ]:
        assert client.post("/search", json=body).status_code == 422
    assert client.post("/search", json={"query": "test", "type": "neural"}).status_code == 503
    assert client.post("/crawl", json={"urls": ["file:///secret"]}).status_code == 422
    assert (
        client.post("/search", content="{}", headers={"content-type": "text/plain"}).status_code
        == 415
    )
    assert client.post("/search", json={"query": "x" * 70000}).status_code == 413


def test_dns_rebinding_host_blocked(client):
    assert client.get("/stats", headers={"host": "attacker.example"}).status_code == 400


def test_auth_protects_reads_and_writes(tmp_path):
    settings = Settings(data_dir=tmp_path, api_key="test-secret-value-long-enough", _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/stats").status_code == 401
        assert client.post("/search", json={"query": "hello"}).status_code == 401
        assert client.delete("/documents/missing").status_code == 401
        assert client.get("/stats", headers={"x-api-key": settings.api_key}).status_code == 200


def test_interrupted_job_on_restart(settings):
    store = Store(settings.data_dir)
    store.save_job({"id": "unfinished", "status": "running", "currentUrl": "https://example.com"})
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        assert client.get("/crawl/unfinished").json()["status"] == "interrupted"


def test_crawl_job_persists(client, monkeypatch):
    def run(self, request, job, save):
        job.update(status="completed", indexed=1, attempted=1)
        save(job)

    monkeypatch.setattr("open_scout.api.Crawler.run", run)
    response = client.post("/crawl", json={"urls": ["https://example.com/"]})
    assert response.status_code == 202
    for _ in range(100):
        state = client.get(f"/crawl/{response.json()['id']}").json()
        if "finishedAt" in state:
            break
        time.sleep(0.01)
    assert state["status"] == "completed"
    assert state["indexed"] == 1
