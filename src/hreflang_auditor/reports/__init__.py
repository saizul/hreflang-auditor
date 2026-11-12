"""Report renderers."""

from __future__ import annotations

from typing import Callable, Dict

from ..auditor import AuditResult
from .csv_report import render_annotations_csv, render_csv
from .html_report import render_html
from .json_report import render_json
from .matrix import ClusterMatrix, build_matrices
from .text_report import render_text

RENDERERS: Dict[str, Callable[[AuditResult], str]] = {
    "text": render_text,
    "json": render_json,
    "csv": render_csv,
    "html": render_html,
}


def render(result: AuditResult, fmt: str) -> str:
    try:
        renderer = RENDERERS[fmt]
    except KeyError:
        raise ValueError(f"unknown format {fmt!r}; choose from {', '.join(RENDERERS)}") from None
    return renderer(result)


__all__ = [
    "RENDERERS",
    "ClusterMatrix",
    "build_matrices",
    "render",
    "render_annotations_csv",
    "render_csv",
    "render_html",
    "render_json",
    "render_text",
]
