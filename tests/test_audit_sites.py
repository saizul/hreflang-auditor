"""End-to-end audits of the fixture sites through a mocked HTTP transport."""

from .conftest import rules_for


def by_rule(result, rule):
    return [i for i in result.issues if i.rule == rule]


def test_good_site_is_clean(site_factory, run_audit):
    result = run_audit(site_factory("good"), ["https://example.com/en/"])
    assert result.issues == []
    stats = result.stats()
    assert stats["urls_fetched"] == 4
    assert stats["pages_with_hreflang"] == 4
    assert stats["clusters"] == 1


def test_broken_site_reports_every_problem(site_factory, run_audit):
    result = run_audit(site_factory("broken"), ["https://shop.test/en/"])
    en = "https://shop.test/en/"
    expected = {
        "known-mistake-region",
        "duplicate-hreflang",
        "relative-url",
        "protocol-relative-url",
        "link-outside-head",
        "missing-return-link",
        "target-redirect",
        "target-non-200",
        "target-noindex",
        "target-canonical-mismatch",
        "target-blocked",
        "mixed-protocol",
        "non-canonical-case",
        "html-lang-mismatch",
    }
    assert expected <= set(rules_for(result, en))
    assert "page-canonical-conflict" in rules_for(result, "https://shop.test/pt/")
    assert "page-noindex" in rules_for(result, "https://shop.test/nl/")
    assert "cluster-code-conflict" in rules_for(result)

    redirect_targets = sorted(i.target for i in by_rule(result, "target-redirect"))
    assert redirect_targets == ["http://shop.test/", "https://shop.test/es-old/"]
    trailing = [i for i in by_rule(result, "missing-return-link") if i.target == "https://shop.test/de/"]
    assert "trailing slash" in trailing[0].message
    assert result.has_at_least(result.issues[0].severity)
    assert result.worst().value == "error"


def test_header_sources(site_factory, run_audit):
    result = run_audit(
        site_factory("headers"),
        ["https://docs.test/guide-en.pdf", "https://docs.test/page-en"],
    )
    pdf_issues = [i for i in result.issues if i.url.endswith(".pdf")]
    assert pdf_issues == []
    assert "conflicting-sources" in rules_for(result, "https://docs.test/page-en")
    assert result.stats()["annotations_by_source"] == {"header": 8, "html": 4}


def test_sitemap_site(site_factory, run_audit):
    result = run_audit(site_factory("sitemap"), sitemaps=["https://intl.test/sitemap_index.xml"])
    assert rules_for(result, "https://intl.test/about-en/") == [
        "missing-self-reference",
        "missing-x-default",
    ]
    assert "missing-return-link" not in rules_for(result)
    assert rules_for(result, "https://intl.test/sitemap-missing.xml") == ["sitemap-error"]
    assert rules_for(result, "https://intl.test/sitemap-blog.xml") == ["sitemap-warning"]
    assert rules_for(result, "https://intl.test/en/") == []


def test_local_sitemap_file(tmp_path, site_factory, run_audit):
    from .conftest import SITES

    path = SITES / "sitemap" / "sitemap-pages.xml"
    result = run_audit(site_factory("sitemap"), sitemap_files=[str(path)])
    assert result.stats()["pages_with_hreflang"] == 4
    assert "sitemap-error" not in rules_for(result)


def test_missing_local_sitemap_file(tmp_path, site_factory, run_audit):
    result = run_audit(site_factory("sitemap"), sitemap_files=[str(tmp_path / "nope.xml")])
    assert rules_for(result) == ["sitemap-error"]


def test_no_follow_limits_checks(site_factory, run_audit):
    result = run_audit(site_factory("broken"), ["https://shop.test/en/"], follow_alternates=False)
    assert not by_rule(result, "target-non-200")
    assert not by_rule(result, "missing-return-link")
    assert by_rule(result, "known-mistake-region")


def test_to_dict_is_serialisable(site_factory, run_audit):
    import json

    result = run_audit(site_factory("broken"), ["https://shop.test/en/"])
    data = json.loads(json.dumps(result.to_dict()))
    assert data["tool"] == "hreflang-auditor"
    errors = sum(1 for i in result.issues if i.severity.value == "error")
    assert data["summary"]["issues"]["error"] == errors
    assert len(data["issues"]) == len(result.issues)
    assert {"issues", "pages", "annotations", "clusters"} <= set(data)
