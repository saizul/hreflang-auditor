import gzip

import pytest

from hreflang_auditor.parsers import (
    SitemapError,
    parse_html,
    parse_link_header,
    parse_sitemap,
    parse_x_robots_tag,
)

# -- Link header ---------------------------------------------------------------


def test_link_header_multiple_values_and_entries():
    links = parse_link_header(
        [
            '<https://a.com/en>; rel="alternate"; hreflang="en", '
            '<https://a.com/de>; rel="alternate"; hreflang="de"',
            "<https://a.com/>; rel=alternate; hreflang=x-default",
        ]
    )
    assert [(link.uri, link.hreflang) for link in links] == [
        ("https://a.com/en", "en"),
        ("https://a.com/de", "de"),
        ("https://a.com/", "x-default"),
    ]
    assert all("alternate" in link.rels for link in links)


def test_link_header_commas_inside_uri_and_quotes():
    links = parse_link_header(['<https://a.com/a,b>; rel="alternate"; title="x, y"; hreflang="fr"'])
    assert len(links) == 1
    assert links[0].uri == "https://a.com/a,b"
    assert links[0].params["title"] == "x, y"
    assert links[0].hreflang == "fr"


def test_link_header_multiple_rel_tokens_and_case():
    links = parse_link_header(['<https://a.com/>; REL="Canonical Alternate"; HrefLang="EN"'])
    assert links[0].rels == ["canonical", "alternate"]
    assert links[0].hreflang == "EN"


def test_link_header_skips_garbage():
    assert parse_link_header(["garbage", "", "https://a.com/; rel=alternate"]) == []


def test_link_header_first_param_wins():
    links = parse_link_header(['<https://a.com/>; hreflang="en"; hreflang="de"'])
    assert links[0].hreflang == "en"


# -- X-Robots-Tag ----------------------------------------------------------------


@pytest.mark.parametrize(
    "values, expected",
    [
        (["noindex"], True),
        (["noindex, nofollow"], True),
        (["none"], True),
        (["nofollow"], False),
        (["googlebot: noindex"], True),
        (["otherbot: noindex"], False),
        (["otherbot: noindex", "googlebot: nofollow"], False),
        (["unavailable_after: 25 Jun 2010 15:00:00 PST"], False),
        (["max-snippet:50, noindex"], True),
        ([], False),
    ],
)
def test_x_robots_tag(values, expected):
    assert parse_x_robots_tag(values) is expected


# -- HTML --------------------------------------------------------------------------


def test_html_extracts_alternates_canonical_lang_and_robots():
    doc = parse_html(
        """<!doctype html><html lang="en-GB"><head>
        <base href="https://cdn.example.com/">
        <link rel="canonical" href="https://example.com/en/">
        <meta name="robots" content="NOINDEX,follow">
        <link rel="alternate" hreflang="en" href="https://example.com/en/">
        <link hreflang="de" rel="alternate" href="https://example.com/de/" media="only screen">
        <link rel="alternate" href="https://example.com/feed" type="application/rss+xml">
        </head><body></body></html>"""
    )
    assert [(a.hreflang, a.href) for a in doc.alternates] == [
        ("en", "https://example.com/en/"),
        ("de", "https://example.com/de/"),
    ]
    assert doc.alternates[1].media == "only screen"
    assert doc.canonical == "https://example.com/en/"
    assert doc.noindex
    assert doc.html_lang == "en-GB"
    assert doc.base_href == "https://cdn.example.com/"


def test_html_links_in_body_are_marked():
    doc = parse_html(
        '<html><head><title>x</title></head><body>'
        '<link rel="alternate" hreflang="fr" href="/fr/"></body></html>'
    )
    assert doc.alternates[0].in_head is False


def test_html_head_is_closed_by_non_head_element():
    doc = parse_html(
        '<html><head><title>x</title><img src="a.png">'
        '<link rel="alternate" hreflang="fr" href="/fr/"></head></html>'
    )
    assert doc.head_closed_early
    assert doc.alternates[0].in_head is False


def test_html_noscript_does_not_close_head():
    doc = parse_html(
        "<html><head><noscript><style>a{}</style></noscript>"
        '<link rel="alternate" hreflang="fr" href="/fr/"></head></html>'
    )
    assert doc.alternates[0].in_head is True


def test_html_without_explicit_head():
    doc = parse_html('<link rel="alternate" hreflang="de" href="https://x.com/de">')
    assert doc.alternates[0].in_head is True


def test_html_googlebot_meta_and_other_bot_meta():
    assert parse_html('<head><meta name="googlebot" content="noindex"></head>').noindex
    assert not parse_html('<head><meta name="bingbot" content="noindex"></head>').noindex


def test_html_malformed_markup_does_not_raise():
    doc = parse_html('<html><head><link rel="alternate" hreflang="en" href="/x"<<<</head')
    assert isinstance(doc.alternates, list)


# -- Sitemaps --------------------------------------------------------------------------

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url>
    <loc> https://a.com/en/ </loc>
    <xhtml:link rel="alternate" hreflang="en" href="https://a.com/en/"/>
    <xhtml:link rel="alternate" hreflang="de" href="https://a.com/de/"/>
  </url>
  <url><loc>https://a.com/plain/</loc></url>
</urlset>"""


def test_sitemap_urlset_with_alternates():
    doc = parse_sitemap(URLSET, "https://a.com/sitemap.xml")
    assert doc.kind == "urlset"
    assert [e.loc for e in doc.entries] == ["https://a.com/en/", "https://a.com/plain/"]
    assert doc.entries[0].alternates == [("en", "https://a.com/en/"), ("de", "https://a.com/de/")]
    assert doc.warnings == []


def test_sitemap_gzip():
    doc = parse_sitemap(gzip.compress(URLSET))
    assert len(doc.entries) == 2


def test_sitemap_index():
    doc = parse_sitemap(
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<sitemap><loc>https://a.com/s1.xml</loc></sitemap>"
        b"<sitemap><loc>https://a.com/s2.xml.gz</loc></sitemap></sitemapindex>"
    )
    assert doc.kind == "sitemapindex"
    assert doc.child_sitemaps == ["https://a.com/s1.xml", "https://a.com/s2.xml.gz"]


def test_sitemap_wrong_xhtml_namespace_is_reported():
    doc = parse_sitemap(
        b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        b'xmlns:xhtml="http://www.w3.org/TR/xhtml11/xhtml11_schema.html">'
        b'<url><loc>https://a.com/</loc><xhtml:link rel="alternate" hreflang="en" '
        b'href="https://a.com/"/></url></urlset>'
    )
    assert doc.entries[0].alternates == []
    assert "xhtml namespace" in doc.warnings[0]


def test_sitemap_wrong_root_namespace_warns():
    doc = parse_sitemap(b"<urlset><url><loc>https://a.com/</loc></url></urlset>")
    assert doc.entries[0].loc == "https://a.com/"
    assert any("namespace" in w for w in doc.warnings)


def test_sitemap_unknown_root():
    doc = parse_sitemap(b"<rss></rss>")
    assert doc.kind == "unknown"
    assert doc.warnings


@pytest.mark.parametrize(
    "data",
    [
        b"<urlset><url>",
        b"not xml",
        b"\x1f\x8bbroken",
        b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><urlset/>',
    ],
)
def test_sitemap_errors(data):
    with pytest.raises(SitemapError):
        parse_sitemap(data)
