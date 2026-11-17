"""Self-contained HTML report with a URL x language matrix per cluster."""

from __future__ import annotations

from html import escape
from typing import List

from .. import codes
from .._version import __version__
from ..auditor import AuditResult
from .matrix import (
    ABSENT,
    CONFLICT,
    MISSING,
    NO_RETURN,
    OK,
    SELF,
    TARGET_PROBLEM,
    UNVERIFIED,
    Cell,
    build_matrices,
)

_SYMBOL = {
    SELF: "self",
    OK: "ok",
    UNVERIFIED: "?",
    NO_RETURN: "no return",
    TARGET_PROBLEM: "target",
    CONFLICT: "conflict",
    MISSING: "missing",
    ABSENT: "",
}

_CSS = """
:root{--bg:#fff;--fg:#1d2330;--muted:#5f6b7a;--line:#e3e7ee;--ok:#e3f5e8;--okfg:#17643a;
--warn:#fff3d6;--warnfg:#7a5300;--err:#fde4e4;--errfg:#9b1c1c;--self:#e8eefc;--selffg:#23408e}
@media (prefers-color-scheme:dark){:root{--bg:#12151b;--fg:#e6e9ef;--muted:#9aa4b2;--line:#2a303b;
--ok:#16331f;--okfg:#8fe0a9;--warn:#3a2f12;--warnfg:#ffd27a;--err:#3d1717;--errfg:#ff9c9c;
--self:#1b2747;--selffg:#a9bdff}}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--fg)}main{max-width:1280px;margin:0 auto;padding:24px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 8px}.muted{color:var(--muted)}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}.card{border:1px solid var(--line);
border-radius:8px;padding:10px 14px;min-width:130px}.card b{display:block;font-size:20px}
table{border-collapse:collapse;width:100%;margin:8px 0 16px}th,td{border:1px solid var(--line);
padding:4px 8px;text-align:left;vertical-align:top}th{position:sticky;top:0;background:var(--bg)}
.matrix td.c{text-align:center;white-space:nowrap;font-size:12px}.wrap{overflow-x:auto}
.self{background:var(--self);color:var(--selffg)}.ok{background:var(--ok);color:var(--okfg)}
.unverified{color:var(--muted)}.no-return,.missing,.conflict{background:var(--warn);color:var(--warnfg)}
.target-problem,.sev-error{background:var(--err);color:var(--errfg)}.sev-warning{background:var(--warn);
color:var(--warnfg)}.sev-notice{color:var(--muted)}td.url{word-break:break-all;max-width:460px}
.legend span{display:inline-block;padding:1px 8px;margin:0 6px 4px 0;border-radius:4px;font-size:12px}
input[type=search]{width:100%;max-width:420px;padding:6px 8px;border:1px solid var(--line);
border-radius:6px;background:var(--bg);color:var(--fg)}code{font-size:12px}
"""

_JS = """
document.getElementById('filter').addEventListener('input',function(e){
var q=e.target.value.toLowerCase();document.querySelectorAll('#issues tbody tr').forEach(function(r){
r.style.display=r.textContent.toLowerCase().indexOf(q)>-1?'':'none';});});
"""


def _cell(cell: Cell) -> str:
    title = "\n".join(cell.hrefs + cell.notes)
    label = _SYMBOL[cell.state]
    return (
        f'<td class="c {cell.state}" title="{escape(title)}">{escape(label)}</td>'
    )


def render_html(result: AuditResult) -> str:
    stats = result.stats()
    counts = stats["issues"]
    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>hreflang audit report</title>",
        f"<style>{_CSS}</style></head><body><main>",
        "<h1>hreflang audit report</h1>",
        f'<p class="muted">hreflang-auditor {escape(__version__)}'
        + (f" &middot; {escape(result.finished_at)}" if result.finished_at else "")
        + "</p>",
        '<div class="cards">',
    ]
    for label, value in (
        ("URLs fetched", stats["urls_fetched"]),
        ("Pages with hreflang", stats["pages_with_hreflang"]),
        ("Annotations", stats["annotations"]),
        ("Clusters", stats["clusters"]),
        ("Errors", counts["error"]),
        ("Warnings", counts["warning"]),
        ("Notices", counts["notice"]),
        *(
            (
                ("Known (baseline)", len(result.baseline.known)),
                ("Fixed since baseline", len(result.baseline.fixed)),
            )
            if result.baseline is not None
            else ()
        ),
    ):
        parts.append(f'<div class="card"><span class="muted">{label}</span><b>{value}</b></div>')
    parts.append("</div>")

    parts.append("<h2>Language matrix</h2>")
    parts.append(
        '<p class="legend"><span class="self">self</span><span class="ok">ok: reciprocal</span>'
        '<span class="no-return">no return link</span><span class="target-problem">target '
        'problem</span><span class="missing">missing in this set</span><span class="conflict">'
        'conflicting URLs</span><span class="unverified">? not crawled</span></p>'
    )
    matrices = build_matrices(result)
    if not matrices:
        parts.append('<p class="muted">No hreflang annotations were found.</p>')
    for number, matrix in enumerate(matrices, 1):
        parts.append(
            f'<h3>Cluster {number} <span class="muted">({matrix.size} URLs, '
            f"{len(matrix.columns)} codes)</span></h3>"
        )
        parts.append('<div class="wrap"><table class="matrix"><thead><tr><th>URL</th><th>Status</th>')
        for column in matrix.columns:
            parts.append(f'<th title="{escape(codes.describe(column))}">{escape(column)}</th>')
        parts.append("</tr></thead><tbody>")
        for row in matrix.rows:
            status = "" if row.status is None else str(row.status)
            parts.append(f'<tr><td class="url">{escape(row.url)}</td><td>{escape(status)}</td>')
            parts.extend(_cell(row.cells[k]) for k in row.cells)
            parts.append("</tr>")
        parts.append("</tbody></table></div>")

    parts.append("<h2>Issues</h2>")
    if result.baseline is not None:
        parts.append(
            f'<p class="muted">{len(result.baseline.known)} issue(s) already recorded in the '
            "baseline are hidden; the matrix still shows them.</p>"
        )
    if not result.issues:
        empty = "No new issues found." if result.baseline is not None else "No issues found."
        parts.append(f"<p>{empty}</p>")
    else:
        parts.append('<input id="filter" type="search" placeholder="Filter issues">')
        parts.append(
            '<div class="wrap"><table id="issues"><thead><tr><th>Severity</th><th>Rule</th>'
            "<th>URL</th><th>hreflang</th><th>Source</th><th>Message</th></tr></thead><tbody>"
        )
        for item in result.issues:
            parts.append(
                f'<tr><td class="sev-{item.severity.value}">{item.severity.value}</td>'
                f"<td><code>{escape(item.rule)}</code></td>"
                f'<td class="url">{escape(item.url)}</td>'
                f"<td>{escape(item.hreflang or '')}</td>"
                f"<td>{escape(item.source or '')}</td>"
                f"<td>{escape(item.message)}</td></tr>"
            )
        parts.append("</tbody></table></div>")
        parts.append(f"<script>{_JS}</script>")

    if result.skipped:
        parts.append(
            f'<p class="muted">{len(result.skipped)} URL(s) were not crawled because the URL '
            "limit was reached.</p>"
        )
    parts.append("</main></body></html>")
    return "\n".join(parts) + "\n"
