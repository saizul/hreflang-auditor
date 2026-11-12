import asyncio

from hreflang_auditor.crawler import CrawlConfig, Crawler

from .conftest import FixtureSite, html_page


def crawl(site, urls=(), sitemaps=(), **kwargs):
    kwargs.setdefault("retry_backoff", 0)
    crawler = Crawler(CrawlConfig(**kwargs), transport=site.transport())
    return asyncio.run(crawler.run(urls, sitemaps))


def chain_site(n, delay=0.0):
    """Pages p0..pn-1 that each list every page (a full cluster)."""
    urls = [f"https://c.test/p{i}" for i in range(n)]
    alts = [(f"en-{code}", u) for code, u in zip(["GB", "US", "IE", "AU", "CA", "NZ", "ZA", "IN",
                                                    "SG", "MT", "PH", "NG"], urls)]
    routes = {"https://c.test/robots.txt": {"body": ""}}
    for u in urls:
        routes[u] = {"body": html_page(alts), "headers": {"content-type": "text/html"}, "delay": delay}
    return FixtureSite(routes), urls


def test_follows_hreflang_targets_and_collects_annotations(site_factory):
    site = site_factory("good")
    result = crawl(site, ["https://example.com/en/"])
    fetched = sorted(u for u, p in result.pages.items() if p.fetched)
    assert fetched == [
        "https://example.com/",
        "https://example.com/de/",
        "https://example.com/en/",
        "https://example.com/fr/",
    ]
    assert len(result.annotations) == 16
    assert {a.source for a in result.annotations} == {"html"}
    assert result.pages["https://example.com/de/"].html_lang == "de-DE"
    assert result.pages["https://example.com/de/"].canonical == "https://example.com/de/"


def test_robots_txt_is_fetched_once_per_origin(site_factory):
    site = site_factory("good")
    crawl(site, ["https://example.com/en/"])
    assert site.count("https://example.com/robots.txt") == 1


def test_no_follow_fetches_only_seeds(site_factory):
    site = site_factory("good")
    result = crawl(site, ["https://example.com/en/"], follow_alternates=False)
    assert [u for u, p in result.pages.items() if p.fetched] == ["https://example.com/en/"]


def test_max_depth_zero_fetches_only_seeds(site_factory):
    site = site_factory("good")
    result = crawl(site, ["https://example.com/en/"], max_depth=0)
    assert sum(p.fetched for p in result.pages.values()) == 1


def test_concurrency_limit_is_respected():
    site, urls = chain_site(12, delay=0.02)
    result = crawl(site, urls, concurrency=3)
    assert sum(p.fetched for p in result.pages.values()) == 12
    assert site.max_in_flight <= 3
    assert site.max_in_flight >= 2  # requests really ran in parallel


def test_max_urls_limit_records_skipped():
    site, urls = chain_site(10)
    result = crawl(site, [urls[0]], max_urls=4)
    assert sum(p.fetched for p in result.pages.values()) == 4
    assert len(result.skipped) == 6


def test_robots_disallow_blocks_fetch(site_factory):
    site = site_factory("broken")
    result = crawl(site, ["https://shop.test/en/"])
    page = result.pages["https://shop.test/private/sv/"]
    assert page.blocked_by_robots and not page.fetched
    assert "https://shop.test/private/sv/" not in site.requests


def test_ignore_robots(site_factory):
    site = site_factory("broken")
    crawl(site, ["https://shop.test/en/"], respect_robots=False)
    assert "https://shop.test/robots.txt" not in site.requests
    assert "https://shop.test/private/sv/" in site.requests


def test_redirects_are_recorded_not_followed_transparently(site_factory):
    site = site_factory("broken")
    result = crawl(site, ["https://shop.test/en/"])
    old = result.pages["https://shop.test/es-old/"]
    assert old.status == 301
    assert old.location == "https://shop.test/es/"
    assert result.pages["https://shop.test/es/"].status == 200


def test_relative_hrefs_are_resolved_and_marked(site_factory):
    site = site_factory("broken")
    result = crawl(site, ["https://shop.test/en/"])
    fr = [a for a in result.annotations if a.hreflang == "fr"][0]
    assert fr.href == "https://shop.test/fr/"
    assert fr.raw_href == "/fr/"
    assert fr.url_kind == "relative"


def test_link_headers_are_collected(site_factory):
    site = site_factory("headers")
    result = crawl(site, ["https://docs.test/guide-en.pdf"])
    header = [a for a in result.annotations if a.page_url == "https://docs.test/guide-en.pdf"]
    assert sorted(a.hreflang for a in header) == ["de", "en", "x-default"]
    assert all(a.source == "header" for a in header)
    assert result.pages["https://docs.test/guide-de.pdf"].fetched


def test_sitemap_index_gzip_and_errors(site_factory):
    site = site_factory("sitemap")
    result = crawl(site, sitemaps=["https://intl.test/sitemap_index.xml"])
    locs = sorted(u for u, p in result.pages.items() if p.in_sitemap)
    assert locs == [
        "https://intl.test/about-bn/",
        "https://intl.test/about-en/",
        "https://intl.test/blog/",
        "https://intl.test/bn/",
        "https://intl.test/en/",
    ]
    assert all(result.pages[u].fetched for u in locs)
    assert result.sitemap_errors == [("https://intl.test/sitemap-missing.xml", "HTTP 404")]
    assert {a.source for a in result.annotations} == {"sitemap"}


def test_retries_on_503_then_success():
    calls = {"n": 0}
    page = html_page([("en", "https://r.test/")])

    import httpx

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    crawler = Crawler(CrawlConfig(retries=2, retry_backoff=0), transport=httpx.MockTransport(handler))
    result = asyncio.run(crawler.run(["https://r.test/"]))
    assert result.pages["https://r.test/"].status == 200
    assert calls["n"] == 2


def test_network_error_is_recorded():
    site = FixtureSite(
        {
            "https://n.test/robots.txt": {"status": 404},
            "https://n.test/": {"raise": "connection refused"},
        }
    )
    result = crawl(site, ["https://n.test/"], retries=1)
    page = result.pages["https://n.test/"]
    assert page.fetched and page.status is None
    assert "ConnectError" in page.error
    assert site.count("https://n.test/") == 2


def test_body_size_limit():
    big = html_page([("en", "https://b.test/")]) + "<!--" + "x" * 50_000 + "-->"
    site = FixtureSite(
        {
            "https://b.test/robots.txt": {"status": 404},
            "https://b.test/": {"body": big, "headers": {"content-type": "text/html"}},
        }
    )
    result = crawl(site, ["https://b.test/"], max_bytes=1000)
    assert result.pages["https://b.test/"].status == 200
    assert len(result.annotations) == 1


def test_allowed_hosts_scope():
    alts = [("en", "https://a.test/"), ("de", "https://b.test/")]
    site = FixtureSite(
        {
            "https://a.test/robots.txt": {"status": 404},
            "https://a.test/": {"body": html_page(alts), "headers": {"content-type": "text/html"}},
            "https://b.test/": {"body": html_page(alts), "headers": {"content-type": "text/html"}},
        }
    )
    result = crawl(site, ["https://a.test/"], allowed_hosts={"a.test"})
    assert "https://b.test/" not in site.requests
    assert "https://b.test/" not in result.pages


def test_x_robots_tag_and_header_canonical():
    site = FixtureSite(
        {
            "https://h.test/robots.txt": {"status": 404},
            "https://h.test/doc": {
                "body": "binary",
                "headers": [
                    ["content-type", "application/pdf"],
                    ["x-robots-tag", "noindex"],
                    ["link", '<https://h.test/main>; rel="canonical"'],
                ],
            },
        }
    )
    result = crawl(site, ["https://h.test/doc"])
    page = result.pages["https://h.test/doc"]
    assert page.noindex
    assert page.canonical == "https://h.test/main"


def test_base_href_is_used_for_resolution():
    body = html_page([("de", "de/")], extra_head='<base href="https://cdn.test/site/">')
    site = FixtureSite(
        {
            "https://base.test/robots.txt": {"status": 404},
            "https://base.test/": {"body": body, "headers": {"content-type": "text/html"}},
        }
    )
    result = crawl(site, ["https://base.test/"], follow_alternates=False)
    assert result.annotations[0].href == "https://cdn.test/site/de/"


def test_charset_from_content_type():
    body = html_page([("de", "https://e.test/münchen")]).encode("latin-1")
    import httpx

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=body,
                              headers={"content-type": "text/html; charset=iso-8859-1"})

    crawler = Crawler(CrawlConfig(follow_alternates=False), transport=httpx.MockTransport(handler))
    result = asyncio.run(crawler.run(["https://e.test/"]))
    assert result.annotations[0].href.endswith("münchen")
