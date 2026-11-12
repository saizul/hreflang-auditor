"""Parse XML sitemaps and sitemap indexes, including ``xhtml:link`` alternates."""

from __future__ import annotations

import gzip
import io
import xml.etree.ElementTree as ET
from typing import Optional

from ..models import SitemapDocument, SitemapEntry

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"
MAX_DECOMPRESSED = 60 * 1024 * 1024


class SitemapError(ValueError):
    """Raised when a sitemap cannot be parsed."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _ns(tag: str) -> Optional[str]:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else None


def _decompress(data: bytes) -> bytes:
    if data[:2] != b"\x1f\x8b":
        return data
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as fh:
            out = fh.read(MAX_DECOMPRESSED + 1)
    except (OSError, EOFError) as exc:
        raise SitemapError(f"invalid gzip data: {exc}") from exc
    if len(out) > MAX_DECOMPRESSED:
        raise SitemapError("decompressed sitemap is larger than 60 MB")
    return out


def parse_sitemap(data: bytes, url: str = "") -> SitemapDocument:
    """Parse sitemap bytes (plain or gzip). Raises :class:`SitemapError`."""
    raw = _decompress(data)
    if b"<!ENTITY" in raw[:4096].upper():
        raise SitemapError("sitemaps with entity declarations are not supported")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SitemapError(f"invalid XML: {exc}") from exc

    kind = _local(root.tag)
    doc = SitemapDocument(url=url, kind=kind if kind in ("urlset", "sitemapindex") else "unknown")
    if doc.kind == "unknown":
        doc.warnings.append(f"root element <{kind}> is not urlset or sitemapindex")
        return doc
    if _ns(root.tag) != SITEMAP_NS:
        doc.warnings.append("root element is not in the sitemaps.org 0.9 namespace")

    if doc.kind == "sitemapindex":
        for child in root:
            if _local(child.tag) != "sitemap":
                continue
            for sub in child:
                if _local(sub.tag) == "loc" and sub.text and sub.text.strip():
                    doc.child_sitemaps.append(sub.text.strip())
        return doc

    wrong_ns = 0
    for child in root:
        if _local(child.tag) != "url":
            continue
        loc = None
        alternates = []
        for sub in child:
            name = _local(sub.tag)
            if name == "loc" and sub.text:
                loc = sub.text.strip()
            elif name == "link":
                if _ns(sub.tag) != XHTML_NS:
                    wrong_ns += 1
                    continue
                rel = (sub.get("rel") or "").lower().split()
                hreflang = sub.get("hreflang")
                href = sub.get("href")
                if "alternate" in rel and hreflang is not None and href is not None:
                    alternates.append((hreflang, href))
        if loc:
            doc.entries.append(SitemapEntry(loc=loc, alternates=alternates, sitemap_url=url))
    if wrong_ns:
        doc.warnings.append(
            f"{wrong_ns} <link> element(s) are not in the xhtml namespace "
            f"({XHTML_NS}) and were ignored"
        )
    return doc
