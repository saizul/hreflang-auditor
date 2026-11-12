"""Plain data structures shared by the crawler, the checks and the reporters."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

SOURCES = ("html", "header", "sitemap")


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"

    @property
    def rank(self) -> int:
        return {"error": 3, "warning": 2, "notice": 1}[self.value]

    @classmethod
    def parse(cls, value: str) -> "Severity":
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(f"unknown severity {value!r}") from None


@dataclass(frozen=True)
class Annotation:
    """One ``hreflang`` alternate declared for ``page_url``."""

    page_url: str
    hreflang: str
    href: str
    raw_href: str
    source: str
    in_head: bool = True
    media: Optional[str] = None
    url_kind: str = "absolute"

    @property
    def key(self) -> str:
        return self.hreflang.strip().lower()


@dataclass
class PageInfo:
    """What the crawler learned about one URL."""

    url: str
    status: Optional[int] = None
    location: Optional[str] = None
    content_type: Optional[str] = None
    canonical: Optional[str] = None
    noindex: bool = False
    html_lang: Optional[str] = None
    error: Optional[str] = None
    blocked_by_robots: bool = False
    fetched: bool = False
    depth: int = 0
    in_sitemap: bool = False
    elapsed_ms: Optional[float] = None

    @property
    def ok(self) -> bool:
        return self.status == 200

    @property
    def is_redirect(self) -> bool:
        return self.status is not None and 300 <= self.status < 400

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    rule: str
    severity: Severity
    url: str
    message: str
    hreflang: Optional[str] = None
    target: Optional[str] = None
    source: Optional[str] = None

    def sort_key(self) -> Tuple[int, str, str, str]:
        return (-self.severity.rank, self.url, self.rule, self.hreflang or "")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass
class SitemapEntry:
    loc: str
    alternates: List[Tuple[str, str]] = field(default_factory=list)
    sitemap_url: str = ""


@dataclass
class SitemapDocument:
    url: str
    kind: str  # "urlset", "sitemapindex" or "unknown"
    entries: List[SitemapEntry] = field(default_factory=list)
    child_sitemaps: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
