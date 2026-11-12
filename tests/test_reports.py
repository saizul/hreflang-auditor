import csv
import io
import json

import pytest

from hreflang_auditor.reports import (
    build_matrices,
    render,
    render_annotations_csv,
    render_csv,
    render_html,
    render_json,
    render_text,
)
from hreflang_auditor.reports.matrix import CONFLICT, MISSING, NO_RETURN, OK, SELF, TARGET_PROBLEM


@pytest.fixture
def broken(site_factory, run_audit):
    return run_audit(site_factory("broken"), ["https://shop.test/en/"])


@pytest.fixture
def good(site_factory, run_audit):
    return run_audit(site_factory("good"), ["https://example.com/en/"])


def test_text_report(broken):
    text = render_text(broken)
    assert text.startswith("hreflang audit")
    assert "https://shop.test/en/" in text
    assert "E known-mistake-region [html]" in text
    assert "Issues by rule" in text


def test_text_report_clean(good):
    assert "No issues found." in render_text(good)


def test_json_report(broken):
    data = json.loads(render_json(broken))
    assert data["version"]
    assert data["summary"]["issues"]["error"] > 0
    assert all({"rule", "severity", "url", "message"} <= set(i) for i in data["issues"])


def test_csv_report(broken):
    rows = list(csv.DictReader(io.StringIO(render_csv(broken))))
    assert len(rows) == len(broken.issues)
    assert set(rows[0]) == {"severity", "rule", "url", "hreflang", "target", "source", "message"}


def test_csv_neutralises_formulas(good):
    from hreflang_auditor.models import Issue, Severity

    good.issues.append(Issue("relative-url", Severity.ERROR, "=HYPERLINK(\"x\")", "-1+1"))
    rows = list(csv.reader(io.StringIO(render_csv(good))))
    assert rows[1][2].startswith("'=")
    assert rows[1][6] == "'-1+1"


def test_annotations_csv(good):
    rows = list(csv.DictReader(io.StringIO(render_annotations_csv(good))))
    assert len(rows) == 16
    assert rows[0]["source"] == "html"


def test_matrix_good(good):
    (matrix,) = build_matrices(good)
    assert matrix.columns == ["de-DE", "en", "fr", "x-default"]
    assert matrix.size == 4
    for row in matrix.rows:
        states = {c.state for c in row.cells.values()}
        assert states <= {SELF, OK}
        assert SELF in states


def test_matrix_broken_states(broken):
    (matrix,) = build_matrices(broken)
    rows = {r.url: r for r in matrix.rows}
    en = rows["https://shop.test/en/"].cells
    cols = dict(zip(matrix.columns, en.values()))
    assert cols["en"].state == CONFLICT
    assert cols["it"].state == TARGET_PROBLEM
    assert cols["fr"].state == NO_RETURN
    de = dict(zip(matrix.columns, rows["https://shop.test/de/"].cells.values()))
    assert de["fr"].state == MISSING


def test_html_report(broken):
    html = render_html(broken)
    assert html.startswith("<!DOCTYPE html>")
    assert "Language matrix" in html
    assert 'class="c target-problem"' in html
    assert "known-mistake-region" in html


def test_html_escapes_untrusted_values(good):
    from hreflang_auditor.models import Issue, Severity

    good.issues.append(Issue("invalid-format", Severity.ERROR, "https://x/<script>", "<b>x</b>"))
    html = render_html(good)
    assert "<script>alert" not in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html
    assert "https://x/&lt;script&gt;" in html


def test_render_dispatch(good):
    assert render(good, "json").startswith("{")
    with pytest.raises(ValueError):
        render(good, "pdf")
