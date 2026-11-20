"""Generate hreflang annotations (sitemap, HTML or Link headers) from a URL mapping.

The mapping is a CSV file in one of two layouts:

* **long**: one row per page with ``group``, ``hreflang`` and ``url`` columns;
* **wide**: one row per cluster with one column per hreflang value
  (``en-GB,de-DE,x-default``) and the URLs in the cells.

Every value and URL is validated before anything is generated, so the output
cannot contain the mistakes the auditor reports (invalid codes, relative URLs,
two URLs for one value, a page in two clusters).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape, quoteattr

from .langtag import parse_hreflang
from .urls import ABSOLUTE, classify

FORMATS = ("sitemap", "html", "headers", "json")
SITEMAP_LIMIT = 50_000

_GROUP_COLUMNS = ("group", "cluster", "page", "name", "id", "key")
_CODE_COLUMNS = ("hreflang", "lang", "language", "code")
_URL_COLUMNS = ("url", "href", "loc")


class MappingError(ValueError):
    """The mapping file cannot be read at all."""


@dataclass
class Problem:
    line: int
    severity: str  # "error" or "warning"
    message: str

    def __str__(self) -> str:
        prefix = f"line {self.line}: " if self.line else ""
        return f"{prefix}{self.severity}: {self.message}"


@dataclass
class Cluster:
    name: str
    #: (hreflang, url) in input order; the hreflang value is in conventional case.
    entries: List[Tuple[str, str]] = field(default_factory=list)

    def urls(self) -> List[str]:
        seen: Dict[str, None] = {}
        for _, url in self.entries:
            seen.setdefault(url, None)
        return list(seen)


@dataclass
class Mapping:
    clusters: List[Cluster] = field(default_factory=list)
    problems: List[Problem] = field(default_factory=list)

    @property
    def errors(self) -> List[Problem]:
        return [p for p in self.problems if p.severity == "error"]

    @property
    def warnings(self) -> List[Problem]:
        return [p for p in self.problems if p.severity == "warning"]

    def alternates(self) -> Dict[str, List[Tuple[str, str]]]:
        """Every URL with the full set of (hreflang, url) alternates of its cluster, itself included."""
        out: Dict[str, List[Tuple[str, str]]] = {}
        for cluster in self.clusters:
            for url in cluster.urls():
                out[url] = list(cluster.entries)
        return out


def _find(header: List[str], names: Tuple[str, ...]) -> Optional[int]:
    lowered = [h.strip().lower() for h in header]
    for name in names:
        if name in lowered:
            return lowered.index(name)
    return None


def _rows(text: str) -> Tuple[List[str], List[Tuple[int, List[str]]]]:
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [(reader.line_num, row) for row in reader]
    rows = [(n, r) for n, r in rows if any(c.strip() for c in r) and not r[0].lstrip().startswith("#")]
    if not rows:
        raise MappingError("the mapping file is empty")
    return rows[0][1], rows[1:]


def _cell(row: List[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def parse_mapping(text: str, x_default: Optional[str] = None) -> Mapping:
    """Read and validate a mapping. ``x_default`` adds an x-default entry pointing at that value's URL."""
    header, rows = _rows(text)
    group_col = _find(header, _GROUP_COLUMNS)
    code_col = _find(header, _CODE_COLUMNS)
    url_col = _find(header, _URL_COLUMNS)
    raw: List[Tuple[int, str, str, str]] = []  # (line, group, code, url)
    if code_col is not None and url_col is not None:
        if group_col is None:
            raise MappingError("the long layout needs a 'group' column next to 'hreflang' and 'url'")
        for line, row in rows:
            raw.append((line, _cell(row, group_col), _cell(row, code_col), _cell(row, url_col)))
    else:
        code_columns = [(i, h.strip()) for i, h in enumerate(header) if i != group_col and h.strip()]
        if not code_columns:
            raise MappingError("no hreflang columns: use group,hreflang,url or one column per hreflang value")
        for line, row in rows:
            name = _cell(row, group_col) if group_col is not None else f"row {line}"
            for i, code in code_columns:
                url = _cell(row, i)
                if url:
                    raw.append((line, name, code, url))
    return _build(raw, x_default)


def _build(raw: List[Tuple[int, str, str, str]], x_default: Optional[str]) -> Mapping:
    mapping = Mapping()
    clusters: Dict[str, Cluster] = {}
    codes_seen: Dict[Tuple[str, str], Tuple[str, int]] = {}  # (group, code key) -> (url, line)
    owner: Dict[str, Tuple[str, int]] = {}  # url -> (group, line)
    for line, group, value, url in raw:
        if not group:
            mapping.problems.append(Problem(line, "error", "missing group"))
            continue
        code = parse_hreflang(value)
        if not code.valid:
            error = next(f for f in code.findings if f.severity.value == "error")
            mapping.problems.append(Problem(line, "error", f"{value!r}: {error.message}"))
            continue
        kind = classify(url)
        if kind != ABSOLUTE:
            message = f"{url!r} is not an absolute http(s) URL ({kind})"
            mapping.problems.append(Problem(line, "error", message))
            continue
        key = (group, code.key)
        if key in codes_seen:
            other_url, other_line = codes_seen[key]
            if other_url != url:
                message = (
                    f"{code.canonical} in group {group!r} already points to {other_url} (line {other_line})"
                )
                mapping.problems.append(Problem(line, "error", message))
            continue
        if url in owner and owner[url][0] != group:
            other_group, other_line = owner[url]
            message = (
                f"{url} is already in group {other_group!r} (line {other_line}); "
                "a page can only belong to one set of alternates"
            )
            mapping.problems.append(Problem(line, "error", message))
            continue
        codes_seen[key] = (url, line)
        owner.setdefault(url, (group, line))
        clusters.setdefault(group, Cluster(group)).entries.append((code.canonical, url))

    fallback = parse_hreflang(x_default) if x_default else None
    for cluster in clusters.values():
        keys = {c.lower() for c, _ in cluster.entries}
        if fallback is not None and fallback.valid and "x-default" not in keys:
            target = next((u for c, u in cluster.entries if c.lower() == fallback.key), None)
            if target is not None:
                cluster.entries.append(("x-default", target))
            else:
                message = f"group {cluster.name!r} has no {fallback.canonical} URL for x-default"
                mapping.problems.append(Problem(0, "warning", message))
        if len(cluster.urls()) < 2:
            mapping.problems.append(
                Problem(0, "warning", f"group {cluster.name!r} has only one URL, so it has no alternates")
            )
    if fallback is not None and not fallback.valid:
        message = f"--x-default {x_default!r} is not a valid hreflang value"
        mapping.problems.append(Problem(0, "error", message))
    mapping.clusters = list(clusters.values())
    total = sum(len(c.urls()) for c in mapping.clusters)
    if total > SITEMAP_LIMIT:
        mapping.problems.append(
            Problem(0, "warning", f"{total} URLs: a single sitemap file holds at most {SITEMAP_LIMIT}")
        )
    return mapping


def render_sitemap(mapping: Mapping) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"',
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">',
    ]
    for url, alternates in mapping.alternates().items():
        lines.append("  <url>")
        lines.append(f"    <loc>{escape(url)}</loc>")
        for code, href in alternates:
            lines.append(
                f'    <xhtml:link rel="alternate" hreflang={quoteattr(code)} href={quoteattr(href)}/>'
            )
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def render_html(mapping: Mapping) -> str:
    blocks = []
    for url, alternates in mapping.alternates().items():
        tags = [
            f'<link rel="alternate" hreflang={quoteattr(code)} href={quoteattr(href)}>'
            for code, href in alternates
        ]
        safe = url.replace("--", "%2D%2D")
        blocks.append("\n".join([f"<!-- {safe} -->", *tags]))
    return "\n\n".join(blocks) + "\n"


def render_headers(mapping: Mapping) -> str:
    lines = []
    for url, alternates in mapping.alternates().items():
        value = ", ".join(f'<{href}>; rel="alternate"; hreflang="{code}"' for code, href in alternates)
        lines.append(f"{url}\n  Link: {value}")
    return "\n\n".join(lines) + "\n"


def render_json(mapping: Mapping) -> str:
    data = {
        url: [{"hreflang": code, "href": href} for code, href in alternates]
        for url, alternates in mapping.alternates().items()
    }
    return json.dumps(data, indent=2) + "\n"


RENDERERS = {"sitemap": render_sitemap, "html": render_html, "headers": render_headers, "json": render_json}
