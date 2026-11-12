"""High-level entry point: crawl, validate and summarise."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

import httpx

from . import rules as R
from ._version import __version__
from .checks import Index, build_clusters, check_crawl, run_checks
from .crawler import CrawlConfig, Crawler, CrawlResult
from .models import Annotation, Issue, PageInfo, Severity


@dataclass
class AuditConfig:
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    disabled_rules: Set[str] = field(default_factory=set)
    severity_overrides: Dict[str, Severity] = field(default_factory=dict)
    min_severity: Severity = Severity.NOTICE

    def validate(self) -> None:
        unknown = (self.disabled_rules | set(self.severity_overrides)) - set(R.RULES)
        if unknown:
            raise ValueError(f"unknown rule id(s): {', '.join(sorted(unknown))}")


@dataclass
class AuditResult:
    pages: Dict[str, PageInfo]
    annotations: List[Annotation]
    issues: List[Issue]
    clusters: List[List[str]]
    skipped: List[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    seeds: List[str] = field(default_factory=list)
    sitemaps: List[str] = field(default_factory=list)

    @property
    def counts(self) -> Dict[str, int]:
        counter = Counter(i.severity.value for i in self.issues)
        return {s.value: counter.get(s.value, 0) for s in Severity}

    @property
    def rule_counts(self) -> Dict[str, int]:
        return dict(sorted(Counter(i.rule for i in self.issues).items()))

    def stats(self) -> Dict[str, Any]:
        fetched = [p for p in self.pages.values() if p.fetched]
        statuses = Counter(str(p.status) if p.status is not None else "error" for p in fetched)
        return {
            "urls_known": len(self.pages),
            "urls_fetched": len(fetched),
            "urls_blocked_by_robots": sum(1 for p in self.pages.values() if p.blocked_by_robots),
            "urls_skipped": len(self.skipped),
            "pages_with_hreflang": len({a.page_url for a in self.annotations}),
            "annotations": len(self.annotations),
            "annotations_by_source": dict(sorted(Counter(a.source for a in self.annotations).items())),
            "clusters": len(self.clusters),
            "status_codes": dict(sorted(statuses.items())),
            "issues": self.counts,
            "issues_by_rule": self.rule_counts,
        }

    def worst(self) -> Optional[Severity]:
        if not self.issues:
            return None
        return max((i.severity for i in self.issues), key=lambda s: s.rank)

    def has_at_least(self, severity: Severity) -> bool:
        return any(i.severity.rank >= severity.rank for i in self.issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": "hreflang-auditor",
            "version": __version__,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "seeds": self.seeds,
            "sitemaps": self.sitemaps,
            "summary": self.stats(),
            "issues": [i.to_dict() for i in self.issues],
            "pages": [self.pages[u].to_dict() for u in sorted(self.pages)],
            "annotations": [
                {
                    "page_url": a.page_url,
                    "hreflang": a.hreflang,
                    "href": a.href,
                    "raw_href": a.raw_href,
                    "source": a.source,
                    "in_head": a.in_head,
                }
                for a in self.annotations
            ],
            "clusters": self.clusters,
            "skipped": self.skipped,
        }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def evaluate(crawl: CrawlResult, config: Optional[AuditConfig] = None) -> AuditResult:
    """Run every check over ``crawl`` and return a sorted, filtered result."""
    config = config or AuditConfig()
    config.validate()
    index = Index(crawl.pages, crawl.annotations)
    clusters = build_clusters(index)
    raw = run_checks(index, clusters)
    raw.extend(check_crawl(crawl.sitemaps, crawl.sitemap_errors, crawl.robots_notes))

    issues: List[Issue] = []
    seen = set()
    for item in raw:
        if item.rule in config.disabled_rules:
            continue
        if item.rule in config.severity_overrides:
            item.severity = config.severity_overrides[item.rule]
        if item.severity.rank < config.min_severity.rank:
            continue
        key = (item.rule, item.url, item.hreflang, item.target, item.source, item.message)
        if key in seen:
            continue
        seen.add(key)
        issues.append(item)
    issues.sort(key=Issue.sort_key)
    return AuditResult(
        pages=crawl.pages,
        annotations=crawl.annotations,
        issues=issues,
        clusters=clusters,
        skipped=sorted(crawl.skipped),
    )


async def audit(
    urls: Sequence[str] = (),
    sitemaps: Sequence[str] = (),
    sitemap_files: Iterable[str] = (),
    config: Optional[AuditConfig] = None,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> AuditResult:
    """Crawl ``urls`` and ``sitemaps`` and audit their hreflang annotations."""
    config = config or AuditConfig()
    config.validate()
    started = _now()
    crawler = Crawler(config.crawl, transport=transport)
    crawl = await crawler.run(urls, sitemaps, list(sitemap_files))
    result = evaluate(crawl, config)
    result.started_at = started
    result.finished_at = _now()
    result.seeds = list(urls)
    result.sitemaps = list(sitemaps) + [str(p) for p in sitemap_files]
    return result


def audit_sync(*args: Any, **kwargs: Any) -> AuditResult:
    """Blocking wrapper around :func:`audit`."""
    return asyncio.run(audit(*args, **kwargs))
