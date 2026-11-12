"""Asynchronous crawler that collects hreflang annotations.

The crawler never follows ordinary links. It fetches the seed URLs, every URL
listed in the given sitemaps, and (optionally) every URL referenced by an
hreflang annotation, up to ``max_depth`` hops away from a seed. Redirects are
not followed transparently: a redirecting URL is recorded as such and its
``Location`` is queued as a separate URL, so redirecting hreflang targets can
be reported precisely.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import httpx

from . import urls as U
from ._version import __version__
from .models import Annotation, PageInfo, SitemapDocument
from .parsers import SitemapError, parse_html, parse_link_header, parse_sitemap, parse_x_robots_tag
from .robots import RobotsCache

DEFAULT_USER_AGENT = (
    f"hreflang-auditor/{__version__} (+https://github.com/saizul/hreflang-auditor)"
)
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
HTML_TYPES = ("text/html", "application/xhtml+xml")


@dataclass
class CrawlConfig:
    concurrency: int = 5
    timeout: float = 15.0
    max_urls: int = 500
    max_depth: int = 3
    max_sitemaps: int = 50
    max_bytes: int = 5 * 1024 * 1024
    user_agent: str = DEFAULT_USER_AGENT
    robots_agent: Optional[str] = None
    respect_robots: bool = True
    follow_alternates: bool = True
    retries: int = 1
    retry_backoff: float = 0.5
    delay: float = 0.0
    allowed_hosts: Optional[Set[str]] = None
    verify_tls: bool = True

    def agent_token(self) -> str:
        if self.robots_agent:
            return self.robots_agent
        return self.user_agent.split("/", 1)[0].split()[0]


@dataclass
class Response:
    url: str
    status: Optional[int]
    headers: httpx.Headers = field(default_factory=httpx.Headers)
    body: bytes = b""
    text: str = ""
    error: Optional[str] = None
    elapsed_ms: float = 0.0
    truncated: bool = False


@dataclass
class CrawlResult:
    pages: Dict[str, PageInfo] = field(default_factory=dict)
    annotations: List[Annotation] = field(default_factory=list)
    sitemaps: List[SitemapDocument] = field(default_factory=list)
    sitemap_errors: List[Tuple[str, str]] = field(default_factory=list)
    skipped: Set[str] = field(default_factory=set)
    robots_notes: Dict[str, str] = field(default_factory=dict)


def make_annotation(
    page_url: str,
    hreflang: str,
    raw_href: str,
    base: str,
    source: str,
    in_head: bool = True,
    media: Optional[str] = None,
) -> Annotation:
    resolved, kind = U.resolve(raw_href, base)
    return Annotation(
        page_url=page_url,
        hreflang=hreflang,
        href=resolved if resolved else raw_href.strip(),
        raw_href=raw_href,
        source=source,
        in_head=in_head,
        media=media,
        url_kind=kind,
    )


def extract_from_response(
    url: str, response: Response, page: PageInfo, agent_token: str = "googlebot"
) -> List[Annotation]:
    """Fill ``page`` from a 200 response and return the annotations it declares."""
    annotations: List[Annotation] = []
    headers = response.headers
    for link in parse_link_header(headers.get_list("link")):
        rels = link.rels
        if "alternate" in rels and link.hreflang is not None:
            annotations.append(make_annotation(url, link.hreflang, link.uri, url, "header"))
        if "canonical" in rels and page.canonical is None:
            resolved, _ = U.resolve(link.uri, url)
            page.canonical = resolved
    if parse_x_robots_tag(headers.get_list("x-robots-tag"), agent_token.lower()):
        page.noindex = True

    ctype = (headers.get("content-type") or "").split(";")[0].strip().lower()
    looks_html = ctype in HTML_TYPES or (not ctype and response.text.lstrip()[:1] == "<")
    if looks_html and response.text:
        doc = parse_html(response.text, agent_token.lower())
        base = url
        if doc.base_href:
            resolved_base, _ = U.resolve(doc.base_href, url)
            if resolved_base:
                base = resolved_base
        for link in doc.alternates:
            annotations.append(
                make_annotation(url, link.hreflang, link.href, base, "html", link.in_head, link.media)
            )
        if doc.canonical:
            resolved, _ = U.resolve(doc.canonical, base)
            if resolved:
                page.canonical = resolved
        page.noindex = page.noindex or doc.noindex
        page.html_lang = doc.html_lang
    return annotations


class Crawler:
    def __init__(
        self,
        config: Optional[CrawlConfig] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.config = config or CrawlConfig()
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        # Created inside run() so they bind to the running event loop (Python 3.9).
        self._sem: Optional[asyncio.Semaphore] = None
        self._queue: "Optional[asyncio.Queue[Tuple[str, int]]]" = None
        self._seen: Set[str] = set()
        self.result = CrawlResult()
        self._robots = RobotsCache(self._fetch_robots, self.config.agent_token())

    # -- HTTP ---------------------------------------------------------------
    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport,
            timeout=self.config.timeout,
            headers={"User-Agent": self.config.user_agent, "Accept": "text/html,*/*;q=0.8"},
            follow_redirects=False,
            verify=self.config.verify_tls,
        )

    async def _request(self, url: str, follow_redirects: bool = False) -> Response:
        assert self._client is not None and self._sem is not None
        attempt = 0
        while True:
            async with self._sem:
                if self.config.delay:
                    await asyncio.sleep(self.config.delay)
                started = time.perf_counter()
                try:
                    response = await self._read(url, follow_redirects)
                except httpx.HTTPError as exc:
                    response = Response(url=url, status=None, error=f"{type(exc).__name__}: {exc}")
                response.elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            retryable = response.status is None or response.status in RETRY_STATUSES
            if not retryable or attempt >= self.config.retries:
                return response
            await asyncio.sleep(self.config.retry_backoff * (2**attempt))
            attempt += 1

    async def _read(self, url: str, follow_redirects: bool) -> Response:
        assert self._client is not None
        request = self._client.build_request("GET", url)
        resp = await self._client.send(request, stream=True, follow_redirects=follow_redirects)
        try:
            chunks: List[bytes] = []
            size = 0
            truncated = False
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                size += len(chunk)
                if size > self.config.max_bytes:
                    truncated = True
                    break
            body = b"".join(chunks)[: self.config.max_bytes]
        finally:
            await resp.aclose()
        encoding = resp.charset_encoding or "utf-8"
        try:
            text = body.decode(encoding, errors="replace")
        except LookupError:
            text = body.decode("utf-8", errors="replace")
        return Response(
            url=str(resp.url),
            status=resp.status_code,
            headers=resp.headers,
            body=body,
            text=text,
            truncated=truncated,
        )

    async def _fetch_robots(self, url: str) -> Tuple[Optional[int], str]:
        response = await self._request(url, follow_redirects=True)
        return response.status, response.text

    # -- queue --------------------------------------------------------------
    def _in_scope(self, url: str) -> bool:
        if U.scheme(url) not in ("http", "https"):
            return False
        allowed = self.config.allowed_hosts
        return not allowed or U.host(url) in allowed

    def _enqueue(self, url: str, depth: int) -> None:
        url = U.normalize(url)
        if url in self._seen or not self._in_scope(url):
            return
        if len(self._seen) >= self.config.max_urls:
            self.result.skipped.add(url)
            return
        self._seen.add(url)
        assert self._queue is not None
        self._queue.put_nowait((url, depth))

    # -- sitemaps -----------------------------------------------------------
    async def _load_sitemaps(self, sitemap_urls: Iterable[str], sitemap_files: Iterable[str]) -> None:
        docs: List[SitemapDocument] = []
        for path in sitemap_files:
            try:
                data = Path(path).read_bytes()
                docs.append(parse_sitemap(data, url=str(path)))
            except (OSError, SitemapError) as exc:
                self.result.sitemap_errors.append((str(path), str(exc)))

        pending = [U.normalize(u) for u in sitemap_urls]
        for doc in docs:
            pending.extend(doc.child_sitemaps)
        seen: Set[str] = set()
        while pending and len(seen) < self.config.max_sitemaps:
            batch = []
            while pending and len(seen) + len(batch) < self.config.max_sitemaps:
                url = pending.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                batch.append(url)
            responses = await asyncio.gather(*(self._request(u, True) for u in batch))
            for url, response in zip(batch, responses):
                if response.status != 200:
                    reason = response.error or f"HTTP {response.status}"
                    self.result.sitemap_errors.append((url, reason))
                    continue
                try:
                    doc = parse_sitemap(response.body, url=url)
                except SitemapError as exc:
                    self.result.sitemap_errors.append((url, str(exc)))
                    continue
                docs.append(doc)
                pending.extend(doc.child_sitemaps)
        if pending:
            self.result.sitemap_errors.append(
                (pending[0], f"sitemap limit of {self.config.max_sitemaps} reached; "
                             f"{len(pending)} sitemap(s) not fetched")
            )

        for doc in docs:
            self.result.sitemaps.append(doc)
            for entry in doc.entries:
                loc, kind = U.resolve(entry.loc, entry.loc)
                if not loc or kind != U.ABSOLUTE:
                    self.result.sitemap_errors.append((doc.url, f"invalid <loc> {entry.loc!r}"))
                    continue
                for hreflang, href in entry.alternates:
                    ann = make_annotation(loc, hreflang, href, loc, "sitemap")
                    self.result.annotations.append(ann)
                self._enqueue(loc, 0)
                page = self.result.pages.setdefault(loc, PageInfo(url=loc))
                page.in_sitemap = True

    # -- pages --------------------------------------------------------------
    async def _process(self, url: str, depth: int) -> None:
        page = self.result.pages.get(url) or PageInfo(url=url)
        page.depth = depth
        self.result.pages[url] = page

        if self.config.respect_robots:
            policy = await self._robots.policy(url)
            if policy.reason:
                self.result.robots_notes[U.origin(url)] = policy.reason
            if not policy.can_fetch(self.config.agent_token(), url):
                page.blocked_by_robots = True
                return

        response = await self._request(url)
        page.fetched = True
        page.status = response.status
        page.error = response.error
        page.elapsed_ms = response.elapsed_ms
        page.content_type = response.headers.get("content-type")

        if page.is_redirect:
            location = response.headers.get("location")
            if location:
                resolved, _ = U.resolve(location, url)
                page.location = resolved or location
                if resolved and self.config.follow_alternates:
                    self._enqueue(resolved, depth)
            return
        if page.status != 200:
            return

        annotations = extract_from_response(url, response, page, self.config.agent_token())
        self.result.annotations.extend(annotations)
        if self.config.follow_alternates and depth < self.config.max_depth:
            for ann in annotations:
                if ann.url_kind != U.INVALID and U.classify(ann.href) == U.ABSOLUTE:
                    self._enqueue(ann.href, depth + 1)

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            url, depth = await self._queue.get()
            try:
                await self._process(url, depth)
            except Exception as exc:  # keep the crawl alive; record the failure
                page = self.result.pages.setdefault(url, PageInfo(url=url))
                page.error = f"{type(exc).__name__}: {exc}"
            finally:
                self._queue.task_done()

    async def run(
        self,
        urls: Iterable[str] = (),
        sitemap_urls: Iterable[str] = (),
        sitemap_files: Iterable[str] = (),
    ) -> CrawlResult:
        self._sem = asyncio.Semaphore(max(1, self.config.concurrency))
        self._queue = asyncio.Queue()
        async with self._make_client() as client:
            self._client = client
            for url in urls:
                self._enqueue(url, 0)
            await self._load_sitemaps(sitemap_urls, sitemap_files)
            if self.config.follow_alternates:
                for ann in list(self.result.annotations):
                    if U.classify(ann.href) == U.ABSOLUTE:
                        self._enqueue(ann.href, 1)
            workers = [
                asyncio.ensure_future(self._worker()) for _ in range(max(1, self.config.concurrency))
            ]
            try:
                await self._queue.join()
            finally:
                for worker in workers:
                    worker.cancel()
                await asyncio.gather(*workers, return_exceptions=True)
            self._client = None
        return self.result
