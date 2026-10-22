import ipaddress
import socket
import time
import zlib
from collections import deque
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import trafilatura
import urllib3
from bs4 import BeautifulSoup

USER_AGENT = "OpenScoutBot/0.1"
MAX_BYTES = 2 * 1024 * 1024


class CrawlError(ValueError):
    pass


class IndexingDenied(CrawlError):
    pass


def normalize_url(value):
    if len(value) > 2048 or any(ord(c) < 33 for c in value) or "\\" in value:
        raise CrawlError("URL contains forbidden characters or exceeds 2048 characters")
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise CrawlError("Only absolute http and https URLs are supported")
        if parts.username is not None or parts.password is not None:
            raise CrawlError("URL credentials are forbidden")
        port = parts.port
        if port not in (None, 80, 443):
            raise CrawlError("Only ports 80 and 443 are allowed")
        host = parts.hostname.encode("idna").decode().lower().rstrip(".")
        authority = f"[{host}]" if ":" in host else host
        if port and port != (443 if parts.scheme == "https" else 80):
            authority += f":{port}"
        return urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))
    except (ValueError, UnicodeError) as exc:
        raise CrawlError(str(exc)) from exc


def public_address(host, port):
    try:
        addresses = list(
            dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM))
        )
    except OSError as exc:
        raise CrawlError("DNS resolution failed") from exc
    if not addresses:
        raise CrawlError("DNS returned no addresses")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise CrawlError("Private, local, reserved, or multicast network targets are blocked")
    return addresses[0]


@dataclass
class Response:
    url: str
    status: int
    headers: dict
    body: bytes


class Fetcher:
    """Pin each connection to a validated public IP, retaining TLS SNI/hostname checks."""

    def fetch(self, url, guard=None):
        for _ in range(6):
            url = normalize_url(url)
            if guard:
                guard(url)
            parts = urlsplit(url)
            host = parts.hostname
            port = parts.port or (443 if parts.scheme == "https" else 80)
            address = public_address(host, port)
            options = {
                "host": address,
                "port": port,
                "timeout": urllib3.Timeout(connect=5, read=10, total=20),
                "maxsize": 1,
            }
            if parts.scheme == "https":
                pool = urllib3.HTTPSConnectionPool(
                    **options, server_hostname=host, assert_hostname=host, cert_reqs="CERT_REQUIRED"
                )
            else:
                pool = urllib3.HTTPConnectionPool(**options)
            response = None
            try:
                response = pool.urlopen(
                    "GET",
                    urlunsplit(("", "", parts.path or "/", parts.query, "")),
                    headers={
                        "Host": parts.netloc,
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,text/plain;q=0.9",
                        "Accept-Encoding": "identity",
                    },
                    redirect=False,
                    retries=False,
                    preload_content=False,
                )
                headers = {k.lower(): v for k, v in response.headers.items()}
                if response.status in (301, 302, 303, 307, 308):
                    if "location" not in headers:
                        raise CrawlError("Redirect has no destination")
                    url = urljoin(url, headers["location"])
                    continue
                body = response.read(MAX_BYTES + 1, decode_content=False)
                if len(body) > MAX_BYTES:
                    raise CrawlError("Response exceeds 2 MiB")
                encoding = headers.get("content-encoding", "identity").lower()
                if encoding in ("gzip", "deflate"):
                    try:
                        decoder = zlib.decompressobj(31 if encoding == "gzip" else 15)
                        body = decoder.decompress(body, MAX_BYTES + 1)
                        if len(body) > MAX_BYTES or decoder.unconsumed_tail:
                            raise CrawlError("Decompressed response exceeds 2 MiB")
                        if not decoder.eof:
                            raise CrawlError("Incomplete compressed response")
                    except zlib.error as exc:
                        raise CrawlError("Invalid compressed response") from exc
                elif encoding != "identity":
                    raise CrawlError(f"Unsupported response encoding: {encoding}")
                return Response(url, response.status, headers, body)
            except urllib3.exceptions.HTTPError as exc:
                raise CrawlError(f"Network request failed: {type(exc).__name__}") from exc
            finally:
                if response:
                    response.close()
                pool.close()
        raise CrawlError("Too many redirects")


def extract(response):
    content_type = response.headers.get("content-type", "").lower()
    if response.status != 200:
        raise CrawlError(f"HTTP {response.status}")
    if "text/html" not in content_type and "text/plain" not in content_type:
        raise CrawlError("Only HTML and plain text are indexed")
    soup = BeautifulSoup(response.body, "html.parser")
    robots = response.headers.get("x-robots-tag", "").lower()
    for meta in soup.find_all("meta"):
        if str(meta.get("name", "")).lower() in ("robots", "openscoutbot"):
            robots += " " + str(meta.get("content", "")).lower()
    directives = set(robots.replace(",", " ").split())
    if "noindex" in directives or "none" in directives:
        raise IndexingDenied("Page requests noindex")
    if "text/plain" in content_type:
        text = response.body.decode("utf-8", errors="replace").strip()
        title = urlsplit(response.url).hostname
        links = []
    else:
        title = soup.title.get_text(" ", strip=True) if soup.title else response.url
        text = trafilatura.extract(
            response.body, include_comments=False, include_tables=True, favor_precision=True
        )
        if not text:
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)
        links = (
            []
            if directives.intersection({"nofollow", "none"})
            else [
                urljoin(response.url, a["href"])
                for a in soup.find_all("a", href=True)
                if "nofollow" not in a.get("rel", [])
            ]
        )
    if len(text.strip()) < 40:
        raise CrawlError("Page has too little readable text")
    return {
        "url": response.url,
        "title": title[:500],
        "text": text[:100000],
        "domain": urlsplit(response.url).hostname,
    }, links


class Crawler:
    def __init__(self, engine, fetcher=None, sleep=time.sleep):
        self.engine = engine
        self.fetcher = fetcher or Fetcher()
        self.sleep = sleep
        self.robots = {}
        self.last_request = {}

    def polite(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            response = self.fetcher.fetch(origin + "/robots.txt")
            parser = RobotFileParser()
            if response.status in (404, 410):
                parser.parse([])
            elif response.status == 200:
                parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
            else:
                raise CrawlError(f"robots.txt unavailable (HTTP {response.status}); crawl skipped")
            self.robots[origin] = parser
            self.last_request[origin] = time.monotonic()
        parser = self.robots[origin]
        if not parser.can_fetch(USER_AGENT, url):
            raise CrawlError("Disallowed by robots.txt")
        delay = max(1.0, parser.crawl_delay(USER_AGENT) or 0)
        rate = parser.request_rate(USER_AGENT)
        if rate and rate.requests:
            delay = max(delay, rate.seconds / rate.requests)
        if delay > 60:
            raise CrawlError("Requested crawl delay exceeds this crawler's 60-second budget")
        remaining = delay - (time.monotonic() - self.last_request.get(origin, 0))
        if remaining > 0:
            self.sleep(remaining)
        self.last_request[origin] = time.monotonic()

    def run(self, request, job, save):
        seeds = [normalize_url(url) for url in request.urls]
        hosts = {urlsplit(url).hostname for url in seeds}
        queue = deque((url, 0) for url in seeds)
        seen = set()
        deadline = time.monotonic() + 1200

        def guard(url):
            if urlsplit(url).hostname not in hosts:
                raise CrawlError("Redirect leaves the seed domains; add the destination as a seed")
            self.polite(url)

        job.update(status="running")
        save(job)
        while queue and job["attempted"] < request.maxPages:
            if time.monotonic() >= deadline:
                job["errors"].append({"url": "", "error": "20-minute crawl budget reached"})
                break
            url, depth = queue.popleft()
            if url in seen:
                continue
            seen.add(url)
            job["attempted"] += 1
            job["currentUrl"] = url
            save(job)
            try:
                response = self.fetcher.fetch(url, guard=guard)
                doc, links = extract(response)
                if response.url not in seen or response.url == url:
                    self.engine.index(doc)
                    job["indexed"] += 1
                seen.add(response.url)
                if depth < request.maxDepth:
                    for link in links[:1000]:
                        try:
                            link = normalize_url(link)
                        except CrawlError:
                            continue
                        if (
                            urlsplit(link).hostname in hosts
                            and link not in seen
                            and len(queue) < 2000
                        ):
                            queue.append((link, depth + 1))
            except IndexingDenied as exc:
                previous = self.engine.store.get(response.url)
                if previous:
                    self.engine.store.delete(previous["id"])
                job["errors"].append({"url": url, "error": str(exc)})
            except Exception as exc:
                job["errors"].append({"url": url, "error": str(exc)[:400]})
            save(job)
        job.update(status="completed", currentUrl=None)
        save(job)
