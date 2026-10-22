import gzip
import socket
from unittest.mock import Mock

import pytest

from open_scout.crawler import (
    MAX_BYTES,
    Crawler,
    CrawlError,
    Fetcher,
    Response,
    extract,
    normalize_url,
    public_address,
)
from open_scout.schemas import CrawlRequest


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "https://example.com:8000/",
        "http://example.com\\@127.0.0.1/",
        "https://example.com/\nfoo",
        "not-a-url",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(CrawlError):
        normalize_url(url)


def test_normalization():
    assert normalize_url("HTTPS://EXAMPLE.COM:443#fragment") == "https://example.com/"


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "224.0.0.1",
        "0.0.0.0",
        "100.64.0.1",
        "::ffff:127.0.0.1",
    ],
)
def test_private_networks_blocked(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (ip, 443))])
    with pytest.raises(CrawlError, match="blocked"):
        public_address("attacker.example", 443)


def test_mixed_dns_answers_fail_closed(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", (ip, 443)) for ip in ["8.8.8.8", "127.0.0.1"]],
    )
    with pytest.raises(CrawlError):
        public_address("attacker.example", 443)


def test_connection_pins_ip_and_verifies_original_host(monkeypatch):
    monkeypatch.setattr("open_scout.crawler.public_address", lambda *a: "8.8.8.8")
    response = Mock(status=200, headers={"Content-Type": "text/html"})
    response.read.return_value = b"hello"
    pool = Mock()
    pool.urlopen.return_value = response
    factory = Mock(return_value=pool)
    monkeypatch.setattr("open_scout.crawler.urllib3.HTTPSConnectionPool", factory)
    assert Fetcher().fetch("https://example.com/a?q=1").body == b"hello"
    assert factory.call_args.kwargs["host"] == "8.8.8.8"
    assert factory.call_args.kwargs["server_hostname"] == "example.com"
    assert factory.call_args.kwargs["assert_hostname"] == "example.com"
    assert pool.urlopen.call_args.kwargs["redirect"] is False
    assert pool.urlopen.call_args.kwargs["headers"]["Host"] == "example.com"
    response.close.assert_called_once()


def test_redirect_revalidates_destination(monkeypatch):
    addresses = Mock(side_effect=["8.8.8.8", CrawlError("blocked")])
    monkeypatch.setattr("open_scout.crawler.public_address", addresses)
    response = Mock(status=302, headers={"Location": "http://127.0.0.1/secret"})
    pool = Mock()
    pool.urlopen.return_value = response
    monkeypatch.setattr("open_scout.crawler.urllib3.HTTPSConnectionPool", lambda **k: pool)
    with pytest.raises(CrawlError, match="blocked"):
        Fetcher().fetch("https://example.com")
    assert addresses.call_args.args[0] == "127.0.0.1"


def test_response_size_limit(monkeypatch):
    monkeypatch.setattr("open_scout.crawler.public_address", lambda *a: "8.8.8.8")
    response = Mock(status=200, headers={})
    response.read.return_value = b"a" * (MAX_BYTES + 1)
    pool = Mock()
    pool.urlopen.return_value = response
    monkeypatch.setattr("open_scout.crawler.urllib3.HTTPConnectionPool", lambda **k: pool)
    with pytest.raises(CrawlError, match="2 MiB"):
        Fetcher().fetch("http://example.com")


@pytest.mark.parametrize("size", [100, MAX_BYTES + 1])
def test_gzip_and_decompression_bomb_limit(monkeypatch, size):
    monkeypatch.setattr("open_scout.crawler.public_address", lambda *a: "8.8.8.8")
    response = Mock(status=200, headers={"Content-Encoding": "gzip"})
    response.read.return_value = gzip.compress(b"x" * size)
    pool = Mock()
    pool.urlopen.return_value = response
    monkeypatch.setattr("open_scout.crawler.urllib3.HTTPConnectionPool", lambda **k: pool)
    if size > MAX_BYTES:
        with pytest.raises(CrawlError, match="Decompressed"):
            Fetcher().fetch("http://example.com")
    else:
        assert Fetcher().fetch("http://example.com").body == b"x" * size


def test_noindex_recrawl_removes_old_copy(engine):
    engine.index(
        {
            "url": "https://example.com/",
            "domain": "example.com",
            "title": "Old",
            "text": "An old page which is no longer allowed to remain in the search index.",
        }
    )
    fetcher = FixtureFetcher()
    original = fetcher.fetch

    def noindex(url, guard=None):
        response = original(url, guard)
        if not url.endswith("robots.txt"):
            response.headers["x-robots-tag"] = "noindex"
        return response

    fetcher.fetch = noindex
    state = job()
    Crawler(engine, fetcher, sleep=lambda _: None).run(
        CrawlRequest(urls=["https://example.com"]), state, lambda _: None
    )
    assert engine.store.get("https://example.com/") is None
    assert state["indexed"] == 0


def html(body, headers=None):
    return Response(
        "https://example.com/", 200, headers or {"content-type": "text/html"}, body.encode()
    )


def test_extraction_noindex_nofollow():
    with pytest.raises(CrawlError, match="noindex"):
        extract(html('<meta name="robots" content="noindex"><p>Hidden content.</p>'))
    with pytest.raises(CrawlError, match="noindex"):
        extract(html("hello", {"content-type": "text/html", "x-robots-tag": "noindex"}))
    doc, links = extract(
        html(
            '<title>Page</title><meta name="robots" content="nofollow">'
            "<p>This is useful content long enough for indexing and reading.</p>"
            '<a href="/child">Child</a><script>secret script</script>'
        )
    )
    assert doc["title"] == "Page"
    assert "secret script" not in doc["text"]
    assert links == []


class FixtureFetcher:
    def __init__(self, robots="User-agent: *\nDisallow: /private", status=200):
        self.calls = []
        self.robots = robots
        self.status = status

    def fetch(self, url, guard=None):
        if guard:
            guard(url)
        self.calls.append(url)
        if url.endswith("robots.txt"):
            return Response(url, self.status, {}, self.robots.encode())
        return Response(
            url,
            200,
            {"content-type": "text/html"},
            b"<title>Test</title><p>Python programming and useful software development "
            b'guides for learning.</p><a href="/child">Child</a>'
            b'<a href="/private">Private</a><a href="https://elsewhere.test/">Other</a>',
        )


def job():
    return {"id": "test", "attempted": 0, "indexed": 0, "errors": []}


def test_bounded_crawl_respects_robots_and_domain(engine):
    fetcher = FixtureFetcher()
    state = job()
    Crawler(engine, fetcher, sleep=lambda _: None).run(
        CrawlRequest(urls=["https://example.com"], maxPages=5, maxDepth=1), state, lambda _: None
    )
    assert state["indexed"] == 2
    assert state["attempted"] == 3
    assert len(state["errors"]) == 1
    assert "https://example.com/private" not in fetcher.calls
    assert all("elsewhere" not in url for url in fetcher.calls)
    assert state["status"] == "completed"


def test_page_budget_and_depth(engine):
    for request in [
        CrawlRequest(urls=["https://example.com"], maxPages=1),
        CrawlRequest(urls=["https://example.com"], maxDepth=0),
    ]:
        state = job()
        Crawler(engine, FixtureFetcher(), sleep=lambda _: None).run(request, state, lambda _: None)
        assert state["indexed"] == 1


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_robots_errors_fail_closed(engine, status):
    state = job()
    Crawler(engine, FixtureFetcher(status=status)).run(
        CrawlRequest(urls=["https://example.com"]), state, lambda _: None
    )
    assert state["indexed"] == 0
    assert len(state["errors"]) == 1
