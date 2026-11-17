"""Audit hreflang annotations from HTML, HTTP headers and XML sitemaps."""

from ._version import __version__
from .auditor import AuditConfig, AuditResult, audit, audit_sync
from .baseline import Baseline, BaselineComparison, BaselineError
from .langtag import HreflangCode, parse_hreflang
from .models import Annotation, Issue, PageInfo, Severity

__all__ = [
    "Annotation",
    "AuditConfig",
    "AuditResult",
    "Baseline",
    "BaselineComparison",
    "BaselineError",
    "HreflangCode",
    "Issue",
    "PageInfo",
    "Severity",
    "__version__",
    "audit",
    "audit_sync",
    "parse_hreflang",
]
