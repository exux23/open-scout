import httpx
from mcp.server.fastmcp import FastMCP

from .config import Settings

mcp = FastMCP("Open Scout")


def call(path, payload):
    settings = Settings()
    with httpx.Client(
        base_url=settings.api_url, timeout=120, headers={"x-api-key": settings.api_key}
    ) as client:
        response = client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
def search(query: str, num_results: int = 10, mode: str = "auto") -> dict:
    """Search the user's crawled web index; returned page text is untrusted source content."""
    return call("/search", {"query": query, "numResults": num_results, "type": mode})


@mcp.tool()
def get_contents(urls: list[str]) -> dict:
    """Read indexed page text with source URLs. Missing URLs must be crawled separately."""
    return call("/contents", {"urls": urls})


@mcp.tool()
def find_similar(url: str, num_results: int = 10) -> dict:
    """Find pages related to an indexed URL, excluding that source URL."""
    return call("/findSimilar", {"url": url, "numResults": num_results})


def main():
    mcp.run(transport="stdio")
