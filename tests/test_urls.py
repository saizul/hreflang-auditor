import pytest

from hreflang_auditor import urls as U


@pytest.mark.parametrize(
    "raw, kind",
    [
        ("https://example.com/a", U.ABSOLUTE),
        ("http://example.com", U.ABSOLUTE),
        ("//example.com/a", U.PROTOCOL_RELATIVE),
        ("/a/b", U.RELATIVE),
        ("a/b", U.RELATIVE),
        ("?lang=de", U.RELATIVE),
        ("", U.INVALID),
        ("   ", U.INVALID),
        ("mailto:me@example.com", U.INVALID),
        ("javascript:void(0)", U.INVALID),
        ("ftp://example.com/file", U.INVALID),
    ],
)
def test_classify(raw, kind):
    assert U.classify(raw) == kind


def test_resolve_relative_and_protocol_relative():
    assert U.resolve("/de/", "https://ex.com/en/") == ("https://ex.com/de/", U.RELATIVE)
    assert U.resolve("de/", "https://ex.com/en/") == ("https://ex.com/en/de/", U.RELATIVE)
    assert U.resolve("//ex.com/fr", "http://ex.com/") == ("http://ex.com/fr", U.PROTOCOL_RELATIVE)
    assert U.resolve("mailto:x", "https://ex.com/") == (None, U.INVALID)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("HTTPS://Example.COM", "https://example.com/"),
        ("https://example.com:443/a#frag", "https://example.com/a"),
        ("http://example.com:80/a?b=1", "http://example.com/a?b=1"),
        ("https://example.com:8443/a/", "https://example.com:8443/a/"),
        ("https://example.com/A/", "https://example.com/A/"),
    ],
)
def test_normalize(url, expected):
    assert U.normalize(url) == expected


def test_near_match():
    assert U.near_match("http://a.com/x", "https://a.com/x") == "differs only in http/https"
    assert U.near_match("https://a.com/x", "https://a.com/x/") == "differs only by a trailing slash"
    assert U.near_match("https://www.a.com/x", "https://a.com/x") == "differs only by the www. prefix"
    assert U.near_match("https://a.com/x?a=1", "https://a.com/x") == "differs only in the query string"
    assert U.near_match("https://a.com/x", "https://b.com/y") is None
    assert U.near_match("https://a.com/x", "https://a.com/x") is None


def test_helpers():
    assert U.origin("https://a.com:8080/x?y") == "https://a.com:8080"
    assert U.host("https://A.com/x") == "a.com"
    assert U.scheme("HTTP://a.com") == "http"
