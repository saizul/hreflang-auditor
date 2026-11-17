"""Build the URL x language matrix used by the HTML report."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..auditor import AuditResult
from ..langtag import parse_hreflang

TARGET_RULES = frozenset(
    {
        "target-non-200",
        "target-redirect",
        "target-noindex",
        "target-canonical-mismatch",
        "target-unreachable",
        "target-blocked",
    }
)

# Cell states, roughly from best to worst.
SELF = "self"
OK = "ok"
UNVERIFIED = "unverified"
NO_RETURN = "no-return"
TARGET_PROBLEM = "target-problem"
CONFLICT = "conflict"
MISSING = "missing"
ABSENT = "absent"


@dataclass
class Cell:
    state: str
    hrefs: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class Row:
    url: str
    status: Optional[int]
    declares: bool
    cells: Dict[str, Cell] = field(default_factory=dict)


@dataclass
class ClusterMatrix:
    columns: List[str]
    rows: List[Row]

    @property
    def size(self) -> int:
        return len(self.rows)


def _column_order(key: str) -> Tuple[int, str]:
    return (1 if key == "x-default" else 0, key)


def build_matrices(result: AuditResult) -> List[ClusterMatrix]:
    mapping: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    labels: Dict[str, str] = {}
    for ann in result.annotations:
        if not ann.in_head:
            continue
        code = parse_hreflang(ann.hreflang)
        mapping[ann.page_url][code.key].add(ann.href)
        labels.setdefault(code.key, code.canonical if code.valid else ann.hreflang.strip())

    problems: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    no_return: Set[Tuple[str, str]] = set()
    for item in result.all_issues:
        if item.target is None:
            continue
        if item.rule in TARGET_RULES:
            problems[(item.url, item.target)].append(item.message)
        elif item.rule == "missing-return-link":
            no_return.add((item.url, item.target))

    matrices: List[ClusterMatrix] = []
    for members in result.clusters:
        keys = sorted({k for m in members for k in mapping.get(m, {})}, key=_column_order)
        if not keys:
            continue
        rows: List[Row] = []
        for member in members:
            info = result.pages.get(member)
            declared = mapping.get(member, {})
            row = Row(url=member, status=info.status if info else None, declares=bool(declared))
            for key in keys:
                hrefs = sorted(declared.get(key, set()))
                if not hrefs:
                    row.cells[key] = Cell(MISSING if declared else ABSENT)
                elif len(hrefs) > 1:
                    row.cells[key] = Cell(CONFLICT, hrefs, ["several URLs for one code"])
                else:
                    href = hrefs[0]
                    if (member, href) in problems:
                        row.cells[key] = Cell(TARGET_PROBLEM, hrefs, problems[(member, href)])
                    elif (member, href) in no_return:
                        row.cells[key] = Cell(NO_RETURN, hrefs, ["no return link"])
                    elif href == member:
                        row.cells[key] = Cell(SELF, hrefs)
                    elif href in mapping or (
                        href in result.pages and result.pages[href].status == 200
                    ):
                        row.cells[key] = Cell(OK, hrefs)
                    else:
                        row.cells[key] = Cell(UNVERIFIED, hrefs, ["target not crawled"])
            rows.append(row)
        matrices.append(ClusterMatrix(columns=[labels.get(k, k) for k in keys], rows=rows))
    return matrices
