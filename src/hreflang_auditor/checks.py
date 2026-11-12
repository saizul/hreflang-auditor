"""Validation checks that turn crawl data into issues."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Set, Tuple

from . import rules as R
from . import urls as U
from .langtag import HreflangCode, parse_hreflang
from .models import SOURCES, Annotation, Issue, PageInfo, SitemapDocument


def issue(rule: str, url: str, message: str, **kwargs) -> Issue:
    return Issue(rule=rule, severity=R.get(rule).severity, url=url, message=message, **kwargs)


@dataclass
class Index:
    """Lookup structures over the crawl data, shared by all checks."""

    pages: Dict[str, PageInfo]
    annotations: List[Annotation]
    by_page: Dict[str, List[Annotation]] = field(default_factory=dict)
    by_page_source: Dict[Tuple[str, str], List[Annotation]] = field(default_factory=dict)
    codes: Dict[str, HreflangCode] = field(default_factory=dict)

    def __post_init__(self) -> None:
        by_page: Dict[str, List[Annotation]] = defaultdict(list)
        by_source: Dict[Tuple[str, str], List[Annotation]] = defaultdict(list)
        for ann in self.annotations:
            by_page[ann.page_url].append(ann)
            by_source[(ann.page_url, ann.source)].append(ann)
            if ann.hreflang not in self.codes:
                self.codes[ann.hreflang] = parse_hreflang(ann.hreflang)
        self.by_page = dict(by_page)
        self.by_page_source = dict(by_source)

    def code(self, ann: Annotation) -> HreflangCode:
        return self.codes[ann.hreflang]

    def usable(self, page_url: str) -> List[Annotation]:
        """Annotations of a page that can take part in set checks.

        Links outside <head> are ignored by Google, so they are left out here
        (they are reported separately).
        """
        return [a for a in self.by_page.get(page_url, []) if a.in_head]

    def targets(self, page_url: str) -> Set[str]:
        return {a.href for a in self.usable(page_url) if U.classify(a.href) == U.ABSOLUTE}

    def mapping(self, page_url: str) -> Dict[str, Set[str]]:
        out: Dict[str, Set[str]] = defaultdict(set)
        for ann in self.usable(page_url):
            out[self.code(ann).key].add(ann.href)
        return dict(out)

    def known(self, url: str) -> bool:
        """``True`` when we know the full annotation set of ``url``."""
        if url in self.by_page:
            return True
        page = self.pages.get(url)
        return bool(page and page.fetched and page.status == 200)

    def healthy(self, url: str) -> bool:
        """``False`` for URLs known to be broken (non-200, blocked, unreachable)."""
        if U.classify(url) != U.ABSOLUTE:
            return False
        page = self.pages.get(url)
        if page is None:
            return True
        if page.blocked_by_robots:
            return False
        return not page.fetched or page.status == 200

    def pages_with_annotations(self) -> List[str]:
        return sorted(self.by_page)


# -- individual checks ------------------------------------------------------------


def check_codes(index: Index) -> Iterator[Issue]:
    seen: Set[Tuple[str, str, str]] = set()
    for ann in index.annotations:
        key = (ann.page_url, ann.source, ann.hreflang)
        if key in seen:
            continue
        seen.add(key)
        code = index.code(ann)
        for finding in code.findings:
            message = finding.message
            if finding.suggestion:
                message += f" (suggested: {finding.suggestion})"
            yield Issue(
                rule=finding.rule,
                severity=finding.severity,
                url=ann.page_url,
                message=message,
                hreflang=ann.hreflang,
                target=ann.href,
                source=ann.source,
            )


def check_urls(index: Index) -> Iterator[Issue]:
    for ann in index.annotations:
        kind = ann.url_kind
        if kind == U.RELATIVE:
            yield issue(
                "relative-url", ann.page_url,
                f"href {ann.raw_href!r} is relative (resolves to {ann.href})",
                hreflang=ann.hreflang, target=ann.href, source=ann.source,
            )
        elif kind == U.PROTOCOL_RELATIVE:
            yield issue(
                "protocol-relative-url", ann.page_url,
                f"href {ann.raw_href!r} has no protocol",
                hreflang=ann.hreflang, target=ann.href, source=ann.source,
            )
        elif kind == U.INVALID:
            yield issue(
                "invalid-url", ann.page_url,
                f"href {ann.raw_href!r} is not an http(s) URL",
                hreflang=ann.hreflang, target=ann.href, source=ann.source,
            )

    for page_url in index.pages_with_annotations():
        hrefs = {a.href for a in index.usable(page_url) if U.classify(a.href) == U.ABSOLUTE}
        schemes = {U.scheme(h) for h in hrefs}
        if {"http", "https"} <= schemes:
            plain = sorted(h for h in hrefs if U.scheme(h) == "http")
            yield issue(
                "mixed-protocol", page_url,
                f"set mixes http and https URLs; http: {', '.join(plain[:5])}"
                + (" ..." if len(plain) > 5 else ""),
            )


def check_placement(index: Index) -> Iterator[Issue]:
    for ann in index.annotations:
        if ann.source == "html" and not ann.in_head:
            yield issue(
                "link-outside-head", ann.page_url,
                f"hreflang={ann.hreflang!r} link is outside <head> and will be ignored",
                hreflang=ann.hreflang, target=ann.href, source="html",
            )
        if ann.media:
            yield issue(
                "media-attribute", ann.page_url,
                f"hreflang={ann.hreflang!r} link also has media={ann.media!r}",
                hreflang=ann.hreflang, target=ann.href, source=ann.source,
            )


def check_duplicates(index: Index) -> Iterator[Issue]:
    for (page_url, source), anns in sorted(index.by_page_source.items()):
        by_code: Dict[str, List[Annotation]] = defaultdict(list)
        for ann in anns:
            if ann.in_head:
                by_code[index.code(ann).key].append(ann)
        for _key, group in sorted(by_code.items()):
            hrefs = sorted({a.href for a in group})
            if len(hrefs) > 1:
                yield issue(
                    "duplicate-hreflang", page_url,
                    f"{group[0].hreflang!r} is declared for {len(hrefs)} different URLs: "
                    + ", ".join(hrefs),
                    hreflang=group[0].hreflang, source=source,
                )
            elif len(group) > 1:
                yield issue(
                    "duplicate-annotation", page_url,
                    f"{group[0].hreflang!r} -> {hrefs[0]} is declared {len(group)} times",
                    hreflang=group[0].hreflang, target=hrefs[0], source=source,
                )

        by_href: Dict[str, Set[str]] = defaultdict(set)
        for ann in anns:
            code = index.code(ann)
            if ann.in_head and not code.is_x_default and code.language:
                by_href[ann.href].add(code.language)
        for href, langs in sorted(by_href.items()):
            if len(langs) > 1:
                values = sorted(
                    {a.hreflang for a in anns if a.href == href and not index.code(a).is_x_default}
                )
                yield issue(
                    "one-url-many-languages", page_url,
                    f"{href} is declared for different languages: {', '.join(values)}",
                    target=href, source=source,
                )


def check_self_reference(index: Index) -> Iterator[Issue]:
    for (page_url, source), anns in sorted(index.by_page_source.items()):
        usable = [a for a in anns if a.in_head]
        if not usable:
            continue
        if not any(a.href == page_url for a in usable):
            near = [
                (a.href, U.near_match(a.href, page_url))
                for a in usable
                if U.near_match(a.href, page_url)
            ]
            hint = f"; closest: {near[0][0]} ({near[0][1]})" if near else ""
            yield issue(
                "missing-self-reference", page_url,
                f"the {source} set does not include the page itself{hint}",
                source=source,
            )


def check_x_default(index: Index) -> Iterator[Issue]:
    for page_url in index.pages_with_annotations():
        usable = index.usable(page_url)
        if usable and not any(index.code(a).is_x_default for a in usable):
            yield issue("missing-x-default", page_url, "no x-default annotation")


def check_return_links(index: Index) -> Iterator[Issue]:
    for page_url in index.pages_with_annotations():
        for ann in _distinct_targets(index, page_url):
            target = ann.href
            if target == page_url or not index.known(target):
                continue
            info = index.pages.get(target)
            if info and info.fetched and info.status != 200:
                continue  # reported by the target checks
            back = index.targets(target)
            if page_url in back:
                continue
            near = [b for b in back if U.near_match(b, page_url)]
            hint = (
                f"; it links to {near[0]} instead ({U.near_match(near[0], page_url)})"
                if near else ""
            )
            yield issue(
                "missing-return-link", page_url,
                f"{target} ({ann.hreflang}) does not link back to this page{hint}",
                hreflang=ann.hreflang, target=target,
            )


def check_targets(index: Index) -> Iterator[Issue]:
    for page_url in index.pages_with_annotations():
        for ann in _distinct_targets(index, page_url):
            target = ann.href
            if target == page_url:
                continue  # the page's own status is covered by check_pages
            info = index.pages.get(target)
            if info is None or (not info.fetched and not info.blocked_by_robots):
                continue
            kw = {"hreflang": ann.hreflang, "target": target}
            if info.blocked_by_robots:
                yield issue("target-blocked", page_url, f"{target} is disallowed by robots.txt", **kw)
                continue
            if info.status is None:
                yield issue(
                    "target-unreachable", page_url,
                    f"{target} could not be fetched: {info.error or 'unknown error'}", **kw,
                )
                continue
            if info.is_redirect:
                dest = info.location or "(no Location header)"
                yield issue(
                    "target-redirect", page_url,
                    f"{target} redirects ({info.status}) to {dest}", **kw,
                )
                continue
            if info.status != 200:
                yield issue("target-non-200", page_url, f"{target} returns {info.status}", **kw)
                continue
            if info.noindex:
                yield issue("target-noindex", page_url, f"{target} is noindex", **kw)
            if info.canonical and info.canonical != target:
                yield issue(
                    "target-canonical-mismatch", page_url,
                    f"{target} declares canonical {info.canonical}", **kw,
                )


def check_pages(index: Index) -> Iterator[Issue]:
    for page_url in index.pages_with_annotations():
        info = index.pages.get(page_url)
        if not info or not info.fetched or info.status != 200:
            continue
        if info.canonical and info.canonical != page_url:
            yield issue(
                "page-canonical-conflict", page_url,
                f"page declares hreflang but its canonical is {info.canonical}",
            )
        if info.noindex:
            yield issue("page-noindex", page_url, "page declares hreflang but is noindex")


def check_html_lang(index: Index) -> Iterator[Issue]:
    seen: Set[Tuple[str, str]] = set()
    for ann in index.annotations:
        code = index.code(ann)
        if code.is_x_default or not code.language or not ann.in_head:
            continue
        info = index.pages.get(ann.href)
        if not info or not info.html_lang or (ann.href, code.key) in seen:
            continue
        seen.add((ann.href, code.key))
        declared = info.html_lang.replace("_", "-").split("-")[0].lower()
        if declared and declared != code.language:
            yield issue(
                "html-lang-mismatch", ann.page_url,
                f"{ann.href} is annotated as {ann.hreflang!r} but has <html lang="
                f"\"{info.html_lang}\">",
                hreflang=ann.hreflang, target=ann.href,
            )


def check_sources(index: Index) -> Iterator[Issue]:
    for page_url in index.pages_with_annotations():
        sets = {}
        for source in SOURCES:
            anns = [a for a in index.by_page_source.get((page_url, source), []) if a.in_head]
            if anns:
                sets[source] = frozenset((index.code(a).key, a.href) for a in anns)
        if len(sets) > 1 and len(set(sets.values())) > 1:
            names = sorted(sets)
            base = sets[names[0]]
            details = []
            for name in names[1:]:
                only_base = sorted(f"{k}={h}" for k, h in base - sets[name])
                only_other = sorted(f"{k}={h}" for k, h in sets[name] - base)
                if only_base or only_other:
                    details.append(
                        f"{names[0]} only: {', '.join(only_base) or '-'}; "
                        f"{name} only: {', '.join(only_other) or '-'}"
                    )
            yield issue(
                "conflicting-sources", page_url,
                f"{' / '.join(names)} declare different sets ({' | '.join(details)})",
            )


def check_clusters(index: Index, clusters: List[List[str]]) -> Iterator[Issue]:
    for members in clusters:
        known = [m for m in members if m in index.by_page]
        if len(known) < 2:
            continue
        declared: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        for member in known:
            for key, hrefs in index.mapping(member).items():
                for href in hrefs:
                    if index.healthy(href):
                        declared[key][href].add(member)

        for key, hrefs in sorted(declared.items()):
            if len(hrefs) > 1:
                parts = [f"{h} (by {len(by)} page{'s' if len(by) > 1 else ''})"
                         for h, by in sorted(hrefs.items())]
                yield issue(
                    "cluster-code-conflict", sorted(known)[0],
                    f"versions disagree on the URL for {key!r}: " + "; ".join(parts),
                    hreflang=key,
                )

        for member in known:
            own = index.mapping(member)
            missing = []
            for key, hrefs in sorted(declared.items()):
                if key in own or len(hrefs) != 1:
                    continue
                href = next(iter(hrefs))
                if href == member:
                    continue
                # If ``href`` lists ``member`` the gap is already a missing return link.
                if member in index.targets(href):
                    continue
                missing.append(f"{key}={href}")
            if missing:
                yield issue(
                    "inconsistent-set", member,
                    "set is missing versions declared elsewhere in the cluster: "
                    + ", ".join(missing),
                )


def check_crawl(
    sitemaps: Iterable[SitemapDocument],
    sitemap_errors: Iterable[Tuple[str, str]],
    robots_notes: Dict[str, str],
) -> Iterator[Issue]:
    for url, error in sitemap_errors:
        yield issue("sitemap-error", url, error)
    for doc in sitemaps:
        for warning in doc.warnings:
            yield issue("sitemap-warning", doc.url, warning)
    for origin, note in sorted(robots_notes.items()):
        effect = "crawling allowed" if "returned 4" in note else "origin treated as disallowed"
        yield issue("robots-unavailable", f"{origin}/robots.txt", f"{note} ({effect})")


# -- helpers --------------------------------------------------------------------------


def _distinct_targets(index: Index, page_url: str) -> List[Annotation]:
    seen: Set[str] = set()
    out = []
    for ann in index.usable(page_url):
        if ann.href in seen or U.classify(ann.href) != U.ABSOLUTE:
            continue
        seen.add(ann.href)
        out.append(ann)
    return out


def build_clusters(index: Index) -> List[List[str]]:
    """Group URLs connected by hreflang annotations (union-find)."""
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for page_url in index.pages_with_annotations():
        find(page_url)
        for target in index.targets(page_url):
            union(page_url, target)
    groups: Dict[str, List[str]] = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


CHECKS: List[Callable[[Index], Iterable[Issue]]] = [
    check_codes,
    check_urls,
    check_placement,
    check_duplicates,
    check_self_reference,
    check_x_default,
    check_return_links,
    check_targets,
    check_pages,
    check_html_lang,
    check_sources,
]


def run_checks(
    index: Index,
    clusters: Optional[List[List[str]]] = None,
) -> List[Issue]:
    issues: List[Issue] = []
    for check in CHECKS:
        issues.extend(check(index))
    issues.extend(check_clusters(index, clusters if clusters is not None else build_clusters(index)))
    return issues
