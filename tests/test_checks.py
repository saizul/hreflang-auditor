"""Unit tests for the checks, using hand-built crawl data (no HTTP)."""

from hreflang_auditor.auditor import AuditConfig, evaluate
from hreflang_auditor.crawler import CrawlResult, make_annotation
from hreflang_auditor.models import PageInfo, Severity, SitemapDocument


def page(url, status=200, **kw):
    return PageInfo(url=url, status=status, fetched=True, **kw)


def ann(page_url, code, href, source="html", **kw):
    return make_annotation(page_url, code, href, page_url, source, **kw)


def full_set(urls_by_code, source="html"):
    out = []
    for page_url in dict.fromkeys(urls_by_code.values()):
        for code, href in urls_by_code.items():
            out.append(ann(page_url, code, href, source))
    return out


A, B, C = "https://x.com/en/", "https://x.com/de/", "https://x.com/fr/"


def result_for(pages, annotations, **kw):
    crawl = CrawlResult(pages={p.url: p for p in pages}, annotations=annotations, **kw)
    return evaluate(crawl)


def rules(result, url=None):
    return sorted({i.rule for i in result.issues if url is None or i.url == url})


def test_clean_cluster_has_only_x_default_notice():
    result = result_for([page(A), page(B)], full_set({"en": A, "de": B}))
    assert rules(result) == ["missing-x-default"]
    assert result.clusters == [[B, A]]


def test_clean_cluster_with_x_default_has_no_issues():
    result = result_for([page(A), page(B)], full_set({"en": A, "de": B, "x-default": A}))
    assert result.issues == []


def test_missing_return_link():
    anns = [ann(A, "en", A), ann(A, "de", B), ann(B, "de", B)]
    result = result_for([page(A), page(B)], anns)
    missing = [i for i in result.issues if i.rule == "missing-return-link"]
    assert len(missing) == 1
    assert missing[0].url == A and missing[0].target == B
    assert missing[0].severity is Severity.ERROR


def test_return_link_from_any_source_counts():
    anns = [ann(A, "en", A), ann(A, "de", B), ann(B, "en", A, source="sitemap"),
            ann(B, "de", B, source="sitemap")]
    result = result_for([page(A), page(B)], anns)
    assert "missing-return-link" not in rules(result)


def test_return_link_not_checked_for_uncrawled_target():
    anns = [ann(A, "en", A), ann(A, "de", B)]
    result = result_for([page(A)], anns)
    assert "missing-return-link" not in rules(result)


def test_return_link_near_match_hint():
    anns = [ann(A, "en", A), ann(A, "de", B), ann(B, "de", B), ann(B, "en", "http://x.com/en/")]
    result = result_for([page(A), page(B)], anns)
    item = [i for i in result.issues if i.rule == "missing-return-link"][0]
    assert "http/https" in item.message


def test_missing_self_reference_per_source():
    anns = [ann(A, "de", B), ann(B, "de", B), ann(B, "en", A)]
    result = result_for([page(A), page(B)], anns)
    items = [i for i in result.issues if i.rule == "missing-self-reference"]
    assert [(i.url, i.source) for i in items] == [(A, "html")]


def test_duplicate_hreflang_and_duplicate_annotation():
    anns = [ann(A, "en", A), ann(A, "EN", "https://x.com/en-us/"), ann(A, "de", B), ann(A, "de", B)]
    result = result_for([page(A)], anns)
    assert "duplicate-hreflang" in rules(result)
    assert "duplicate-annotation" in rules(result)


def test_duplicate_x_default():
    anns = [ann(A, "en", A), ann(A, "x-default", A), ann(A, "x-default", B)]
    result = result_for([page(A)], anns)
    dup = [i for i in result.issues if i.rule == "duplicate-hreflang"]
    assert dup and dup[0].hreflang == "x-default"


def test_one_url_many_languages():
    anns = [ann(A, "en", A), ann(A, "de", A), ann(A, "x-default", A)]
    result = result_for([page(A)], anns)
    assert "one-url-many-languages" in rules(result)


def test_same_language_two_regions_one_url_is_fine():
    anns = [ann(A, "en", A), ann(A, "en-GB", A), ann(A, "x-default", A)]
    result = result_for([page(A)], anns)
    assert "one-url-many-languages" not in rules(result)


def test_relative_protocol_relative_and_invalid_urls():
    anns = [ann(A, "en", A), ann(A, "de", "/de/"), ann(A, "fr", "//x.com/fr/"),
            ann(A, "it", "mailto:a@b.c")]
    result = result_for([page(A)], anns)
    assert {"relative-url", "protocol-relative-url", "invalid-url"} <= set(rules(result))


def test_mixed_protocol():
    anns = [ann(A, "en", A), ann(A, "de", "http://x.com/de/")]
    result = result_for([page(A)], anns)
    assert "mixed-protocol" in rules(result)


def test_link_outside_head_is_ignored_for_set_checks():
    anns = [ann(A, "en", A), ann(A, "de", B, in_head=False)]
    result = result_for([page(A), page(B)], anns)
    assert "link-outside-head" in rules(result)
    assert "missing-return-link" not in rules(result)


def test_media_attribute():
    anns = [ann(A, "en", A, media="only screen and (max-width: 640px)")]
    result = result_for([page(A)], anns)
    assert "media-attribute" in rules(result)


def test_target_status_rules():
    targets = {
        "de": (page(B, status=404), "target-non-200"),
        "fr": (page(C, status=302, location="https://x.com/fr/new"), "target-redirect"),
        "it": (page("https://x.com/it/", noindex=True), "target-noindex"),
        "es": (page("https://x.com/es/", canonical="https://x.com/en/"), "target-canonical-mismatch"),
        "nl": (PageInfo(url="https://x.com/nl/", blocked_by_robots=True), "target-blocked"),
        "pt": (page("https://x.com/pt/", status=None, error="ConnectError"), "target-unreachable"),
    }
    anns = [ann(A, "en", A)] + [ann(A, code, p.url) for code, (p, _) in targets.items()]
    result = result_for([page(A)] + [p for p, _ in targets.values()], anns)
    found = {i.hreflang: i.rule for i in result.issues if i.rule.startswith("target-")}
    assert found == {code: rule for code, (_, rule) in targets.items()}


def test_target_checks_skip_self():
    anns = [ann(A, "en", A)]
    result = result_for([page(A, noindex=True)], anns)
    assert rules(result) == ["missing-x-default", "page-noindex"]


def test_page_canonical_conflict():
    anns = [ann(B, "de", B), ann(B, "en", A)]
    result = result_for([page(B, canonical=A)], anns)
    assert "page-canonical-conflict" in rules(result, B)


def test_html_lang_mismatch():
    anns = [ann(A, "en", A), ann(A, "de", B), ann(B, "de", B), ann(B, "en", A)]
    result = result_for([page(A, html_lang="en"), page(B, html_lang="fr")], anns)
    items = [i for i in result.issues if i.rule == "html-lang-mismatch"]
    assert len(items) == 1 and items[0].target == B


def test_conflicting_sources():
    anns = [ann(A, "en", A), ann(A, "de", B), ann(A, "en", A, "sitemap"), ann(A, "fr", C, "sitemap")]
    result = result_for([page(A)], anns)
    item = [i for i in result.issues if i.rule == "conflicting-sources"][0]
    assert "html only: de=" in item.message and "sitemap only: fr=" in item.message


def test_inconsistent_set_and_cluster_code_conflict():
    anns = (
        [ann(A, "en", A), ann(A, "de", B), ann(A, "fr", C)]
        + [ann(B, "en", A), ann(B, "de", B)]
        + [ann(C, "en", A), ann(C, "de", "https://x.com/de-alt/"), ann(C, "fr", C)]
    )
    result = result_for([page(A), page(B), page(C)], anns)
    incons = [i for i in result.issues if i.rule == "inconsistent-set"]
    assert any(i.url == B and "fr=" in i.message for i in incons)
    assert "cluster-code-conflict" in rules(result)


def test_code_findings_become_issues_once_per_page_and_source():
    anns = [ann(A, "en-uk", A), ann(A, "en-uk", A)]
    result = result_for([page(A)], anns)
    assert [i.rule for i in result.issues].count("known-mistake-region") == 1


def test_crawl_issues():
    doc = SitemapDocument(url="https://x.com/s.xml", kind="urlset", warnings=["bad ns"])
    crawl = CrawlResult(
        sitemaps=[doc],
        sitemap_errors=[("https://x.com/missing.xml", "HTTP 404")],
        robots_notes={"https://x.com": "robots.txt returned 503"},
    )
    result = evaluate(crawl)
    assert rules(result) == ["robots-unavailable", "sitemap-error", "sitemap-warning"]
    robots = [i for i in result.issues if i.rule == "robots-unavailable"][0]
    assert "disallowed" in robots.message


def test_config_disable_override_and_min_severity():
    anns = [ann(A, "en", A), ann(A, "de", B), ann(B, "de", B)]
    crawl = CrawlResult(pages={A: page(A), B: page(B)}, annotations=anns)
    result = evaluate(crawl, AuditConfig(disabled_rules={"missing-x-default"}))
    assert "missing-x-default" not in rules(result)
    result = evaluate(crawl, AuditConfig(severity_overrides={"missing-return-link": Severity.NOTICE}))
    assert [i.severity for i in result.issues if i.rule == "missing-return-link"] == [Severity.NOTICE]
    result = evaluate(crawl, AuditConfig(min_severity=Severity.ERROR))
    assert all(i.severity is Severity.ERROR for i in result.issues)


def test_unknown_rule_in_config_raises():
    import pytest

    with pytest.raises(ValueError, match="nope"):
        evaluate(CrawlResult(), AuditConfig(disabled_rules={"nope"}))


def test_issues_sorted_by_severity():
    anns = [ann(A, "en-uk", A), ann(A, "EN", A)]
    result = result_for([page(A)], anns)
    ranks = [i.severity.rank for i in result.issues]
    assert ranks == sorted(ranks, reverse=True)


def test_clusters_are_separate():
    anns = full_set({"en": A, "de": B}) + full_set({"en": "https://y.com/a", "fr": "https://y.com/b"})
    pages = [page(A), page(B), page("https://y.com/a"), page("https://y.com/b")]
    result = result_for(pages, anns)
    assert len(result.clusters) == 2
