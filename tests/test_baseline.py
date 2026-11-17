import json

import pytest

from hreflang_auditor import Baseline, BaselineError
from hreflang_auditor.baseline import (
    BASELINE_FORMAT,
    BASELINE_KIND,
    BaselineEntry,
    compare,
    fingerprint,
    fingerprint_fields,
)
from hreflang_auditor.cli import main
from hreflang_auditor.models import Issue, Severity
from hreflang_auditor.reports import render

from .conftest import FixtureSite

BROKEN_SEED = "https://shop.test/en/"


@pytest.fixture
def audit_site(run_audit):
    def _audit(name, urls):
        return run_audit(FixtureSite.load(name), urls)

    return _audit


def _issue(rule="missing-return-link", url="https://a.test/en/", **kw):
    kw.setdefault("severity", Severity.ERROR)
    kw.setdefault("message", "no return link")
    return Issue(rule=rule, url=url, **kw)


# -- fingerprints ---------------------------------------------------------------


def test_fingerprint_ignores_message_and_severity():
    a = _issue(hreflang="de", target="https://a.test/de/", message="one wording")
    b = _issue(hreflang="de", target="https://a.test/de/", message="another wording",
               severity=Severity.WARNING)
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_hreflang_and_source_are_case_insensitive():
    a = _issue(hreflang="en-GB", source="HTML")
    b = _issue(hreflang=" en-gb ", source="html")
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_distinguishes_target_rule_and_url():
    base = _issue(target="https://a.test/de/")
    assert fingerprint(base) != fingerprint(_issue(target="https://a.test/fr/"))
    assert fingerprint(base) != fingerprint(_issue(rule="target-redirect", target="https://a.test/de/"))
    assert fingerprint(base) != fingerprint(_issue(url="https://a.test/fr/", target="https://a.test/de/"))


def test_fingerprint_fields_matches_issue_fingerprint():
    issue = _issue(hreflang="de", target="https://a.test/de/", source="sitemap")
    assert fingerprint(issue) == fingerprint_fields(
        issue.rule, issue.url, "de", "https://a.test/de/", "sitemap"
    )
    assert len(fingerprint(issue)) == 20


# -- compare ------------------------------------------------------------------------


def test_compare_splits_new_known_and_fixed():
    old_kept = _issue(target="https://a.test/de/")
    old_gone = _issue(target="https://a.test/fr/")
    baseline = Baseline.from_issues([old_kept, old_gone])
    new_issue = _issue(rule="target-noindex", target="https://a.test/nl/")
    result = compare([old_kept, new_issue], baseline)
    assert result.new == [new_issue]
    assert result.known == [old_kept]
    assert [e.target for e in result.fixed] == ["https://a.test/fr/"]


def test_compare_counts_duplicate_fingerprints():
    issue = _issue(target="https://a.test/de/")
    baseline = Baseline.from_issues([issue])
    result = compare([issue, _issue(target="https://a.test/de/", message="again")], baseline)
    assert len(result.known) == 1 and len(result.new) == 1
    assert result.fixed == []


def test_compare_empty_baseline_everything_is_new():
    issues = [_issue(), _issue(rule="missing-x-default", severity=Severity.NOTICE)]
    result = compare(issues, Baseline())
    assert result.new == issues and result.known == [] and result.fixed == []


# -- load / save ----------------------------------------------------------------------


def test_round_trip(tmp_path):
    issues = [_issue(hreflang="de", target="https://a.test/de/", source="html")]
    path = tmp_path / "baseline.json"
    Baseline.from_issues(issues).save(path)
    data = json.loads(path.read_text("utf-8"))
    assert data["kind"] == BASELINE_KIND and data["format"] == BASELINE_FORMAT
    assert data["issues"][0]["fingerprint"] == fingerprint(issues[0])
    loaded = Baseline.load(path)
    assert loaded.path == str(path)
    assert len(loaded) == 1
    assert loaded.entries[0] == BaselineEntry.from_issue(issues[0])


def test_entries_are_sorted_for_stable_diffs():
    issues = [_issue(url="https://a.test/z/"), _issue(url="https://a.test/a/")]
    urls = [e.url for e in Baseline.from_issues(issues).entries]
    assert urls == ["https://a.test/a/", "https://a.test/z/"]


def test_load_accepts_json_report_without_fingerprints():
    report = {
        "tool": "hreflang-auditor",
        "finished_at": "2026-11-12T10:00:00+00:00",
        "issues": [{"rule": "missing-return-link", "url": "https://a.test/en/",
                    "hreflang": "de", "target": "https://a.test/de/", "source": None,
                    "severity": "error", "message": "x"}],
    }
    baseline = Baseline.from_dict(report)
    assert baseline.created_at == "2026-11-12T10:00:00+00:00"
    expected = fingerprint(_issue(hreflang="de", target="https://a.test/de/"))
    assert baseline.entries[0].fingerprint == expected


@pytest.mark.parametrize(
    "document, message",
    [
        ([], "JSON object"),
        ({"tool": "something-else", "issues": []}, "not an hreflang-auditor"),
        ({"kind": "other"}, "unexpected document kind"),
        ({"kind": BASELINE_KIND, "format": 99, "issues": []}, "unsupported baseline format"),
        ({"tool": "hreflang-auditor"}, "no 'issues' list"),
        ({"tool": "hreflang-auditor", "issues": ["x"]}, "JSON object"),
        ({"tool": "hreflang-auditor", "issues": [{"rule": "r"}]}, "'rule' and 'url'"),
    ],
)
def test_from_dict_rejects_bad_documents(document, message):
    with pytest.raises(BaselineError, match=message):
        Baseline.from_dict(document)


def test_load_missing_and_invalid_files(tmp_path):
    with pytest.raises(BaselineError, match="cannot read baseline"):
        Baseline.load(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(BaselineError, match="not valid JSON"):
        Baseline.load(bad)


# -- AuditResult and reports ------------------------------------------------------------


def test_apply_baseline_hides_known_issues(audit_site):
    first = audit_site("broken", [BROKEN_SEED])
    assert first.counts["error"] > 0
    baseline = Baseline.from_issues(first.issues)

    second = audit_site("broken", [BROKEN_SEED])
    total = len(second.issues)
    comparison = second.apply_baseline(baseline)
    assert second.issues == [] and len(comparison.known) == total
    assert second.counts == {"error": 0, "warning": 0, "notice": 0}
    assert not second.has_at_least(Severity.NOTICE)
    assert len(second.all_issues) == total

    data = json.loads(render(second, "json"))
    assert data["baseline"]["known"] == total and data["baseline"]["new"] == 0
    assert data["issues"] == []
    text = render(second, "text")
    assert f"Baseline: 0 new, {total} known (hidden), 0 fixed" in text
    assert "No new issues found." in text
    html = render(second, "html")
    assert "Known (baseline)" in html and "No new issues found." in html


def test_html_matrix_still_marks_known_problems(audit_site):
    plain = render(audit_site("broken", [BROKEN_SEED]), "html")
    result = audit_site("broken", [BROKEN_SEED])
    result.apply_baseline(Baseline.from_issues(result.issues))
    with_baseline = render(result, "html")
    for state in ("no-return", "target-problem"):
        marker = f'class="c {state}"'
        assert with_baseline.count(marker) == plain.count(marker)
    assert plain.count('class="c target-problem"') + plain.count('class="c no-return"') > 0


def test_json_report_has_no_baseline_key_without_baseline(audit_site):
    data = json.loads(render(audit_site("good", ["https://example.com/en/"]), "json"))
    assert "baseline" not in data


# -- CLI -------------------------------------------------------------------------------


def test_cli_write_then_use_baseline(tmp_path, capsys):
    site = FixtureSite.load("broken")
    path = tmp_path / "hreflang-baseline.json"
    assert main(["audit", "-q", "--write-baseline", str(path), BROKEN_SEED], site.transport()) == 1
    capsys.readouterr()
    assert len(Baseline.load(path)) > 0

    site = FixtureSite.load("broken")
    code = main(["audit", "-f", "json", "--baseline", str(path), BROKEN_SEED], site.transport())
    assert code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["issues"] == [] and data["baseline"]["fixed"] == 0
    assert "Baseline: 0 new" in captured.err


def test_cli_report_json_works_as_baseline(tmp_path, capsys):
    site = FixtureSite.load("broken")
    report = tmp_path / "report.json"
    main(["audit", "-q", "-f", "json", "-o", str(report), BROKEN_SEED], site.transport())
    site = FixtureSite.load("broken")
    assert main(["audit", "-q", "--baseline", str(report), BROKEN_SEED], site.transport()) == 0


def test_cli_new_issue_fails_and_fixed_is_reported(tmp_path, capsys):
    path = tmp_path / "baseline.json"
    known = {
        "rule": "missing-return-link", "url": "https://shop.test/gone/", "hreflang": "de",
        "target": "https://shop.test/de/", "source": None, "severity": "error", "message": "x",
    }
    path.write_text(json.dumps({"kind": BASELINE_KIND, "format": 1, "issues": [known]}), "utf-8")
    site = FixtureSite.load("broken")
    code = main(["audit", "-q", "-f", "json", "--baseline", str(path), BROKEN_SEED], site.transport())
    assert code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["baseline"]["fixed"] == 1
    assert data["baseline"]["fixed_issues"][0]["url"] == "https://shop.test/gone/"
    assert data["baseline"]["new"] == len(data["issues"]) > 0


def test_cli_fail_on_fixed(tmp_path, capsys):
    path = tmp_path / "baseline.json"
    site = FixtureSite.load("broken")
    main(["audit", "-q", "--write-baseline", str(path), BROKEN_SEED], site.transport())
    data = json.loads(path.read_text("utf-8"))
    data["issues"].append({"rule": "target-noindex", "url": "https://shop.test/old/",
                           "target": "https://shop.test/old-de/"})
    path.write_text(json.dumps(data), "utf-8")

    site = FixtureSite.load("broken")
    assert main(["audit", "-q", "--baseline", str(path), BROKEN_SEED], site.transport()) == 0
    site = FixtureSite.load("broken")
    args = ["audit", "-q", "--baseline", str(path), "--fail-on-fixed", BROKEN_SEED]
    assert main(args, site.transport()) == 1


def test_cli_fail_on_fixed_requires_baseline(capsys):
    assert main(["audit", "-q", "--fail-on-fixed", BROKEN_SEED]) == 2
    assert "needs --baseline" in capsys.readouterr().err


def test_cli_bad_baseline_is_usage_error(tmp_path, capsys):
    assert main(["audit", "-q", "--baseline", str(tmp_path / "missing.json"), BROKEN_SEED]) == 2
    assert "cannot read baseline" in capsys.readouterr().err
