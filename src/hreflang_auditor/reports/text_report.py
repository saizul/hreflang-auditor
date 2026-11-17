from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from ..auditor import AuditResult
from ..models import Issue

_ICON = {"error": "E", "warning": "W", "notice": "N"}


def render_text(result: AuditResult) -> str:
    stats = result.stats()
    counts = stats["issues"]
    lines: List[str] = []
    lines.append("hreflang audit")
    lines.append("=" * 60)
    lines.append(
        f"URLs fetched: {stats['urls_fetched']}  pages with hreflang: "
        f"{stats['pages_with_hreflang']}  annotations: {stats['annotations']}  "
        f"clusters: {stats['clusters']}"
    )
    by_source = ", ".join(f"{k}={v}" for k, v in stats["annotations_by_source"].items()) or "none"
    lines.append(f"Annotations by source: {by_source}")
    if stats["urls_blocked_by_robots"] or stats["urls_skipped"]:
        lines.append(
            f"Blocked by robots.txt: {stats['urls_blocked_by_robots']}  "
            f"not crawled (limit): {stats['urls_skipped']}"
        )
    lines.append(
        f"Issues: {counts['error']} error(s), {counts['warning']} warning(s), "
        f"{counts['notice']} notice(s)"
    )
    if result.baseline is not None:
        lines.append(_baseline_line(result))
    if not result.issues:
        lines.append("")
        lines.append("No new issues found." if result.baseline is not None else "No issues found.")
        return "\n".join(lines) + "\n"

    grouped: Dict[str, List[Issue]] = defaultdict(list)
    for item in result.issues:
        grouped[item.url].append(item)

    for url in sorted(grouped, key=lambda u: (-max(i.severity.rank for i in grouped[u]), u)):
        lines.append("")
        lines.append(url)
        for item in grouped[url]:
            where = f" [{item.source}]" if item.source else ""
            lines.append(f"  {_ICON[item.severity.value]} {item.rule}{where}: {item.message}")

    lines.append("")
    lines.append("Issues by rule")
    lines.append("-" * 60)
    width = max(len(r) for r in stats["issues_by_rule"])
    for rule, count in sorted(stats["issues_by_rule"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {rule.ljust(width)}  {count}")
    return "\n".join(lines) + "\n"


def _baseline_line(result: AuditResult) -> str:
    comparison = result.baseline
    assert comparison is not None
    return (
        f"Baseline: {len(comparison.new)} new, {len(comparison.known)} known (hidden), "
        f"{len(comparison.fixed)} fixed since the baseline"
    )
