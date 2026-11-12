import json

from hreflang_auditor.cli import main

from .conftest import FixtureSite


def test_check_command_valid(capsys):
    assert main(["check", "en-GB", "x-default"]) == 0
    out = capsys.readouterr().out
    assert "ok      en-GB -> en-GB (English (United Kingdom))" in out


def test_check_command_invalid_exit_code(capsys):
    assert main(["check", "en-uk"]) == 1
    assert "known-mistake-region" in capsys.readouterr().out


def test_check_command_json(capsys):
    main(["check", "--json", "EN-us", "jp"])
    data = json.loads(capsys.readouterr().out)
    assert data[0]["valid"] and data[0]["canonical"] == "en-US"
    assert data[1]["valid"] is False and data[1]["findings"][0]["suggestion"] == "ja"


def test_rules_command(capsys):
    assert main(["rules"]) == 0
    assert "missing-return-link" in capsys.readouterr().out
    main(["rules", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert any(r["id"] == "target-canonical-mismatch" for r in data)


def test_no_command_prints_help(capsys):
    assert main([]) == 2


def test_audit_requires_input(capsys):
    assert main(["audit"]) == 2
    assert "at least one URL" in capsys.readouterr().err


def test_audit_rejects_relative_url(capsys):
    assert main(["audit", "/en/"]) == 2


def test_audit_unknown_rule(capsys):
    site = FixtureSite.load("good")
    code = main(["audit", "-q", "--disable", "nope", "https://example.com/en/"], site.transport())
    assert code == 2
    assert "unknown rule" in capsys.readouterr().err


def test_audit_bad_severity_override(capsys):
    site = FixtureSite.load("good")
    assert main(["audit", "-q", "--severity", "missing-x-default", "https://example.com/en/"],
                site.transport()) == 2


def test_audit_good_site_exit_zero(capsys):
    site = FixtureSite.load("good")
    assert main(["audit", "-q", "https://example.com/en/"], site.transport()) == 0
    assert "No issues found." in capsys.readouterr().out


def test_audit_broken_site_writes_reports(tmp_path, capsys):
    site = FixtureSite.load("broken")
    out = tmp_path / "report.html"
    ann = tmp_path / "annotations.csv"
    code = main(
        ["audit", "-f", "html", "-o", str(out), "--annotations-csv", str(ann),
         "https://shop.test/en/"],
        site.transport(),
    )
    assert code == 1
    assert out.read_text().startswith("<!DOCTYPE html>")
    assert ann.read_text().startswith("page_url,")
    err = capsys.readouterr().err
    assert "Report written to" in err and "error(s)" in err


def test_audit_fail_on_never_and_min_severity(capsys):
    site = FixtureSite.load("broken")
    code = main(["audit", "-q", "-f", "json", "--fail-on", "never", "--min-severity", "error",
                 "https://shop.test/en/"], site.transport())
    assert code == 0
    data = json.loads(capsys.readouterr().out)
    assert {i["severity"] for i in data["issues"]} == {"error"}


def test_audit_disable_and_override(capsys):
    site = FixtureSite.load("headers")
    code = main(
        ["audit", "-q", "-f", "csv", "--disable", "missing-x-default,robots-unavailable",
         "--severity", "missing-return-link=warning", "https://docs.test/page-en"],
        site.transport(),
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "missing-x-default" not in out
    assert "warning,missing-return-link" in out


def test_audit_input_file(tmp_path, capsys):
    site = FixtureSite.load("good")
    listing = tmp_path / "urls.txt"
    listing.write_text("# seeds\nhttps://example.com/en/\n\nhttps://example.com/de/  # german\n")
    assert main(["audit", "-q", "-i", str(listing), "--no-follow"], site.transport()) == 0


def test_audit_sitemap_option(capsys):
    site = FixtureSite.load("sitemap")
    code = main(["audit", "-q", "-f", "json", "-s", "https://intl.test/sitemap_index.xml"],
                site.transport())
    assert code == 1  # sitemap-missing.xml is an error
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["annotations_by_source"] == {"sitemap": 9}


def test_version(capsys):
    import pytest

    with pytest.raises(SystemExit):
        main(["--version"])
    assert "hreflang-auditor 0.1.0" in capsys.readouterr().out
