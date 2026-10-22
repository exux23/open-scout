import asyncio

import httpx
import pytest

from open_scout import mcp_server


def test_tools_and_api_mapping(monkeypatch):
    calls = []

    def mock_call(path, body):
        calls.append((path, body))
        return {"results": []}

    monkeypatch.setattr(mcp_server, "call", mock_call)
    tools = asyncio.run(mcp_server.mcp.list_tools())
    assert {t.name for t in tools} == {"search", "get_contents", "find_similar"}
    mcp_server.search("example", 5, "keyword")
    mcp_server.get_contents(["https://example.com/"])
    mcp_server.find_similar("https://example.com/", 4)
    assert calls == [
        ("/search", {"query": "example", "numResults": 5, "type": "keyword"}),
        ("/contents", {"urls": ["https://example.com/"]}),
        ("/findSimilar", {"url": "https://example.com/", "numResults": 4}),
    ]


def test_transport_auth_and_errors(monkeypatch, settings):
    settings.api_key = "test-token"
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(401, json={"detail": "unauthorized"})

    original = httpx.Client
    monkeypatch.setattr(mcp_server, "Settings", lambda: settings)
    monkeypatch.setattr(
        mcp_server.httpx,
        "Client",
        lambda **kw: original(**kw, transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(httpx.HTTPStatusError):
        mcp_server.call("/search", {"query": "example"})
    assert seen[0].headers["x-api-key"] == "test-token"
