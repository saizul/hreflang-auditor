from __future__ import annotations

import csv
import io

from ..auditor import AuditResult

ISSUE_COLUMNS = ["severity", "rule", "url", "hreflang", "target", "source", "message"]
ANNOTATION_COLUMNS = ["page_url", "hreflang", "href", "raw_href", "source", "in_head", "url_kind"]

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: object) -> str:
    """Neutralise spreadsheet formula injection in untrusted cell values."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def render_csv(result: AuditResult) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(ISSUE_COLUMNS)
    for item in result.issues:
        row = item.to_dict()
        writer.writerow([_safe(row[c]) for c in ISSUE_COLUMNS])
    return out.getvalue()


def render_annotations_csv(result: AuditResult) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(ANNOTATION_COLUMNS)
    for ann in result.annotations:
        writer.writerow([_safe(getattr(ann, c)) for c in ANNOTATION_COLUMNS])
    return out.getvalue()
