"""URL classification and normalisation helpers."""

from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

ABSOLUTE = "absolute"
RELATIVE = "relative"
PROTOCOL_RELATIVE = "protocol-relative"
INVALID = "invalid"

_DEFAULT_PORTS = {"http": 80, "https": 443}


def classify(raw: str) -> str:
    """Classify an href as written in the source document."""
    value = (raw or "").strip()
    if not value:
        return INVALID
    if value.startswith("//"):
        return PROTOCOL_RELATIVE
    parts = urlsplit(value)
    if parts.scheme:
        if parts.scheme.lower() in _DEFAULT_PORTS and parts.netloc:
            return ABSOLUTE
        return INVALID
    return RELATIVE


def resolve(raw: str, base: str) -> Tuple[Optional[str], str]:
    """Return ``(absolute_url, kind)``. The URL is ``None`` when it cannot be resolved."""
    kind = classify(raw)
    value = (raw or "").strip()
    if kind == INVALID:
        return None, kind
    if kind == ABSOLUTE:
        return normalize(value), kind
    try:
        joined = urljoin(base, value)
    except ValueError:
        return None, INVALID
    if classify(joined) != ABSOLUTE:
        return None, kind
    return normalize(joined), kind


def normalize(url: str) -> str:
    """Normalise a URL for comparison.

    Lower-cases the scheme and host, drops default ports and the fragment, and
    turns an empty path into ``/``. Path, query and trailing slashes are kept
    because they make different URLs.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if parts.port and _DEFAULT_PORTS.get(scheme) != parts.port:
        host = f"{host}:{parts.port}"
    userinfo = ""
    if parts.username:
        userinfo = parts.username + (f":{parts.password}" if parts.password else "") + "@"
    path = parts.path or "/"
    return urlunsplit((scheme, userinfo + host, path, parts.query, ""))


def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def scheme(url: str) -> str:
    return urlsplit(url).scheme.lower()


def host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def without_scheme(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(("", parts.netloc, parts.path, parts.query, ""))


def near_match(a: str, b: str) -> Optional[str]:
    """Describe how two URLs nearly match, or ``None`` if they are unrelated."""
    if a == b:
        return None
    if without_scheme(a) == without_scheme(b):
        return "differs only in http/https"
    if a.rstrip("/") == b.rstrip("/"):
        return "differs only by a trailing slash"
    pa, pb = urlsplit(a), urlsplit(b)
    host_a = (pa.hostname or "").removeprefix("www.")
    host_b = (pb.hostname or "").removeprefix("www.")
    if host_a == host_b and pa.path == pb.path and pa.query == pb.query:
        return "differs only by the www. prefix"
    if pa.netloc == pb.netloc and pa.path == pb.path and pa.query != pb.query:
        return "differs only in the query string"
    return None
