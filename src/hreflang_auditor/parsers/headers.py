"""Parsers for the HTTP ``Link`` (RFC 8288) and ``X-Robots-Tag`` headers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


@dataclass
class LinkValue:
    uri: str
    params: Dict[str, str] = field(default_factory=dict)

    @property
    def rels(self) -> List[str]:
        return [r.lower() for r in self.params.get("rel", "").split()]

    @property
    def hreflang(self) -> Optional[str]:
        return self.params.get("hreflang")


def _split_top_level(value: str, sep: str) -> List[str]:
    """Split on ``sep`` outside of ``<...>`` and double quotes."""
    out: List[str] = []
    buf: List[str] = []
    in_quotes = in_angle = False
    escape = False
    for ch in value:
        if escape:
            buf.append(ch)
            escape = False
            continue
        if ch == "\\" and in_quotes:
            buf.append(ch)
            escape = True
            continue
        if ch == '"' and not in_angle:
            in_quotes = not in_quotes
        elif ch == "<" and not in_quotes:
            in_angle = True
        elif ch == ">" and not in_quotes:
            in_angle = False
        if ch == sep and not in_quotes and not in_angle:
            out.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    out.append("".join(buf))
    return out


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse_link_header(values: Iterable[str]) -> List[LinkValue]:
    """Parse one or more ``Link`` header values into link-values.

    Malformed entries (no ``<uri>``) are skipped.
    """
    links: List[LinkValue] = []
    for header in values:
        for chunk in _split_top_level(header, ","):
            chunk = chunk.strip()
            if not chunk.startswith("<") or ">" not in chunk:
                continue
            uri, _, rest = chunk[1:].partition(">")
            params: Dict[str, str] = {}
            for param in _split_top_level(rest, ";"):
                param = param.strip()
                if not param:
                    continue
                name, eq, val = param.partition("=")
                name = name.strip().lower().rstrip("*")
                if name and name not in params:
                    params[name] = _unquote(val) if eq else ""
            links.append(LinkValue(uri=uri.strip(), params=params))
    return links


def parse_x_robots_tag(values: Iterable[str], user_agent: str = "googlebot") -> bool:
    """Return ``True`` when an ``X-Robots-Tag`` header applies ``noindex`` (or ``none``).

    Directives scoped to another crawler (``otherbot: noindex``) are ignored.
    """
    ua = user_agent.lower()
    for header in values:
        scope: Optional[str] = None
        for token in header.split(","):
            token = token.strip().lower()
            if not token:
                continue
            if ":" in token:
                maybe_scope, _, directive = token.partition(":")
                maybe_scope = maybe_scope.strip()
                if maybe_scope not in ("unavailable_after", "max-snippet", "max-image-preview",
                                       "max-video-preview"):
                    scope = maybe_scope
                    token = directive.strip()
            if scope not in (None, ua, "*"):
                continue
            for directive in token.split():
                if directive in ("noindex", "none"):
                    return True
    return False
