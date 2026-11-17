"""Baselines: accept the issues a site already has and only report new ones.

A baseline is a JSON file listing issue fingerprints. Running an audit with a
baseline splits the current issues into *new* ones (reported and counted for
``--fail-on``) and *known* ones (already in the baseline, hidden). Baseline
entries that no longer occur are reported as *fixed*.

A fingerprint is built from the rule id, the page URL, the hreflang value, the
target URL and the source. The human-readable message is deliberately left
out, so rewording a message in a later release does not invalidate baselines.
A full ``--format json`` report can be used as a baseline as well.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from ._version import __version__
from .models import Issue

BASELINE_KIND = "hreflang-auditor-baseline"
BASELINE_FORMAT = 1


class BaselineError(ValueError):
    """The baseline file is missing, unreadable or has an unexpected shape."""


def _norm(value: Optional[str]) -> str:
    return "" if value is None else str(value).strip()


def fingerprint_fields(
    rule: str,
    url: str,
    hreflang: Optional[str] = None,
    target: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    """Return the stable fingerprint for an issue described by its fields."""
    parts = [
        _norm(rule),
        _norm(url),
        _norm(hreflang).lower(),
        _norm(target),
        _norm(source).lower(),
    ]
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:20]


def fingerprint(issue: Issue) -> str:
    """Return the stable fingerprint of ``issue``."""
    return fingerprint_fields(issue.rule, issue.url, issue.hreflang, issue.target, issue.source)


@dataclass
class BaselineEntry:
    fingerprint: str
    rule: str
    url: str
    severity: str = ""
    hreflang: Optional[str] = None
    target: Optional[str] = None
    source: Optional[str] = None
    message: str = ""

    @classmethod
    def from_issue(cls, issue: Issue) -> "BaselineEntry":
        return cls(
            fingerprint=fingerprint(issue),
            rule=issue.rule,
            url=issue.url,
            severity=issue.severity.value,
            hreflang=issue.hreflang,
            target=issue.target,
            source=issue.source,
            message=issue.message,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BaselineEntry":
        if not isinstance(data, Mapping):
            raise BaselineError("every baseline issue must be a JSON object")
        rule = data.get("rule")
        url = data.get("url")
        if not isinstance(rule, str) or not isinstance(url, str):
            raise BaselineError("every baseline issue needs string 'rule' and 'url' fields")
        hreflang = data.get("hreflang")
        target = data.get("target")
        source = data.get("source")
        fp = data.get("fingerprint")
        if not isinstance(fp, str) or not fp:
            fp = fingerprint_fields(rule, url, hreflang, target, source)
        return cls(
            fingerprint=fp,
            rule=rule,
            url=url,
            severity=str(data.get("severity") or ""),
            hreflang=hreflang,
            target=target,
            source=source,
            message=str(data.get("message") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "rule": self.rule,
            "severity": self.severity,
            "url": self.url,
            "hreflang": self.hreflang,
            "target": self.target,
            "source": self.source,
            "message": self.message,
        }


@dataclass
class Baseline:
    """A set of accepted issues, loaded from or saved to a JSON file."""

    entries: List[BaselineEntry] = field(default_factory=list)
    created_at: str = ""
    path: Optional[str] = None

    @classmethod
    def from_issues(cls, issues: Iterable[Issue]) -> "Baseline":
        entries = [BaselineEntry.from_issue(i) for i in issues]
        entries.sort(key=lambda e: (e.url, e.rule, e.hreflang or "", e.target or "", e.fingerprint))
        created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        return cls(entries=entries, created_at=created)

    @classmethod
    def from_dict(cls, data: Any) -> "Baseline":
        """Build a baseline from a baseline document or a ``--format json`` report."""
        if not isinstance(data, Mapping):
            raise BaselineError("a baseline must be a JSON object")
        kind = data.get("kind")
        if kind is not None and kind != BASELINE_KIND:
            raise BaselineError(f"unexpected document kind {kind!r}")
        if kind == BASELINE_KIND:
            fmt = data.get("format")
            if not isinstance(fmt, int) or fmt > BASELINE_FORMAT:
                raise BaselineError(
                    f"unsupported baseline format {fmt!r}; this version reads format {BASELINE_FORMAT}"
                )
        elif data.get("tool") != "hreflang-auditor":
            raise BaselineError("not an hreflang-auditor baseline or JSON report")
        issues = data.get("issues")
        if not isinstance(issues, list):
            raise BaselineError("the document has no 'issues' list")
        return cls(
            entries=[BaselineEntry.from_dict(item) for item in issues],
            created_at=str(data.get("created_at") or data.get("finished_at") or ""),
        )

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Baseline":
        try:
            text = Path(path).read_text("utf-8")
        except OSError as exc:
            raise BaselineError(f"cannot read baseline {str(path)!r}: {exc.strerror or exc}") from None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BaselineError(f"baseline {str(path)!r} is not valid JSON: {exc.msg}") from None
        baseline = cls.from_dict(data)
        baseline.path = str(path)
        return baseline

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": BASELINE_KIND,
            "format": BASELINE_FORMAT,
            "tool": "hreflang-auditor",
            "version": __version__,
            "created_at": self.created_at,
            "issues": [e.to_dict() for e in self.entries],
        }

    def dumps(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    def save(self, path: Union[str, Path]) -> None:
        Path(path).write_text(self.dumps(), encoding="utf-8")

    def __len__(self) -> int:
        return len(self.entries)


@dataclass
class BaselineComparison:
    """The outcome of comparing current issues with a baseline."""

    new: List[Issue]
    known: List[Issue]
    fixed: List[BaselineEntry]
    path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "new": len(self.new),
            "known": len(self.known),
            "fixed": len(self.fixed),
            "fixed_issues": [e.to_dict() for e in self.fixed],
        }


def compare(issues: Iterable[Issue], baseline: Baseline) -> BaselineComparison:
    """Split ``issues`` into new and known ones and list baseline entries that are gone.

    Fingerprints are matched as a multiset: if the baseline holds one entry for
    a fingerprint and the audit now finds two issues with it, one is new.
    """
    budget: Counter = Counter(e.fingerprint for e in baseline.entries)
    new: List[Issue] = []
    known: List[Issue] = []
    for issue in issues:
        fp = fingerprint(issue)
        if budget[fp] > 0:
            budget[fp] -= 1
            known.append(issue)
        else:
            new.append(issue)
    fixed: List[BaselineEntry] = []
    for entry in baseline.entries:
        if budget[entry.fingerprint] > 0:
            budget[entry.fingerprint] -= 1
            fixed.append(entry)
    return BaselineComparison(new=new, known=known, fixed=fixed, path=baseline.path)
