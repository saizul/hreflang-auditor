"""Shared fixtures: an in-memory HTTP transport that serves fixture sites."""

from __future__ import annotations

import asyncio
import gzip
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
import pytest

from hreflang_auditor.auditor import AuditConfig, AuditResult, audit
from hreflang_auditor.crawler import CrawlConfig

FIXTURES = Path(__file__).parent / "fixtures"
SITES = FIXTURES / "sites"


class FixtureSite:
    """Serve ``routes.json`` from a fixture directory through ``httpx.MockTransport``.

    Each route maps an absolute URL to ``{"status", "headers", "file" | "body",
    "gzip", "delay"}``. Unknown URLs return 404. Every request is recorded.
    """

    def __init__(self, routes: Dict[str, dict], root: Optional[Path] = None) -> None:
        self.routes = routes
        self.root = root
        self.requests: List[str] = []
        self.in_flight = 0
        self.max_in_flight = 0

    @classmethod
    def load(cls, name: str) -> "FixtureSite":
        root = SITES / name
        routes = json.loads((root / "routes.json").read_text("utf-8"))
        return cls(routes, root)

    def body(self, route: dict) -> bytes:
        if "file" in route:
            assert self.root is not None
            data = (self.root / route["file"]).read_bytes()
        else:
            data = route.get("body", "").encode("utf-8")
        if route.get("gzip"):
            data = gzip.compress(data)
        return data

    async def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requests.append(url)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            route = self.routes.get(url)
            if route and route.get("delay"):
                await asyncio.sleep(route["delay"])
            if route is None:
                return httpx.Response(404, text="not found", request=request)
            if route.get("raise"):
                raise httpx.ConnectError(route["raise"], request=request)
            headers = route.get("headers", {})
            if isinstance(headers, dict):
                headers = list(headers.items())
            return httpx.Response(
                route.get("status", 200),
                headers=[tuple(h) for h in headers],
                content=self.body(route),
                request=request,
            )
        finally:
            self.in_flight -= 1

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def count(self, url: str) -> int:
        return self.requests.count(url)


def fast_config(**overrides) -> AuditConfig:
    crawl_kwargs = {"retry_backoff": 0, "timeout": 5}
    audit_kwargs = {}
    for key, value in overrides.items():
        if key in AuditConfig.__dataclass_fields__:
            audit_kwargs[key] = value
        else:
            crawl_kwargs[key] = value
    return AuditConfig(crawl=CrawlConfig(**crawl_kwargs), **audit_kwargs)


@pytest.fixture
def site_factory() -> Callable[[str], FixtureSite]:
    return FixtureSite.load


@pytest.fixture
def run_audit() -> Callable[..., AuditResult]:
    def _run(site: FixtureSite, urls=(), sitemaps=(), sitemap_files=(), **overrides) -> AuditResult:
        return asyncio.run(
            audit(
                list(urls),
                list(sitemaps),
                list(sitemap_files),
                config=fast_config(**overrides),
                transport=site.transport(),
            )
        )

    return _run


def rules_for(result: AuditResult, url: Optional[str] = None) -> List[str]:
    return sorted(i.rule for i in result.issues if url is None or i.url == url)


def html_page(alternates, canonical=None, lang=None, robots=None, extra_head="", body="") -> str:
    """Build a small HTML page for inline routes."""
    links = "\n".join(
        f'<link rel="alternate" hreflang="{code}" href="{href}">' for code, href in alternates
    )
    canon = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    meta = f'<meta name="robots" content="{robots}">' if robots else ""
    lang_attr = f' lang="{lang}"' if lang else ""
    return (
        f"<!DOCTYPE html><html{lang_attr}><head><title>t</title>{canon}{meta}{links}"
        f"{extra_head}</head><body>{body}</body></html>"
    )
