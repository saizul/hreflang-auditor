import json

import pytest

from hreflang_auditor.cli import main
from hreflang_auditor.generate import (
    MappingError,
    parse_mapping,
    render_headers,
    render_html,
    render_json,
    render_sitemap,
)
from hreflang_auditor.parsers.headers import parse_link_header
from hreflang_auditor.parsers.html import parse_html
from hreflang_auditor.parsers.sitemap import parse_sitemap

LONG = """group,hreflang,url
home,en-gb,https://example.com/en/
home,de-DE,https://example.com/de/
home,x-default,https://example.com/en/
about,en-GB,https://example.com/en/about/
about,de-DE,https://example.com/de/ueber-uns/
"""

WIDE = """page;en-GB;de-DE;fr
home;https://example.com/en/;https://example.com/de/;https://example.com/fr/
about;https://example.com/en/about/;https://example.com/de/ueber-uns/;
"""


def test_long_layout_and_canonical_case():
    mapping = parse_mapping(LONG)
    assert mapping.problems == []
    assert [c.name for c in mapping.clusters] == ["home", "about"]
    assert mapping.clusters[0].entries == [
        ("en-GB", "https://example.com/en/"),
        ("de-DE", "https://example.com/de/"),
        ("x-default", "https://example.com/en/"),
    ]
    assert mapping.clusters[0].urls() == ["https://example.com/en/", "https://example.com/de/"]


def test_wide_layout_with_semicolons_and_empty_cells():
    mapping = parse_mapping(WIDE)
    assert mapping.errors == []
    about = mapping.alternates()["https://example.com/de/ueber-uns/"]
    assert about == [
        ("en-GB", "https://example.com/en/about/"),
        ("de-DE", "https://example.com/de/ueber-uns/"),
    ]
    assert len(mapping.alternates()) == 5


def test_x_default_option():
    mapping = parse_mapping(WIDE, x_default="fr")
    home = mapping.alternates()["https://example.com/en/"]
    assert ("x-default", "https://example.com/fr/") in home
    assert [str(w) for w in mapping.warnings] == ["warning: group 'about' has no fr URL for x-default"]
    assert parse_mapping(WIDE, x_default="xx-yy").errors


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("home,en-uk,https://example.com/uk/", "use 'GB'"),
        ("home,jp,https://example.com/ja/", "'jp'"),
        ("home,fr,/fr/", "not an absolute http(s) URL (relative)"),
        ("home,fr,//example.com/fr/", "protocol-relative"),
        ("home,de-DE,https://example.com/de-2/", "already points to https://example.com/de/"),
        ("other,fr,https://example.com/de/", "already in group 'home'"),
        (",fr,https://example.com/fr/", "missing group"),
    ],
)
def test_errors(row, message):
    mapping = parse_mapping(LONG + row + "\n")
    assert len(mapping.errors) == 1, mapping.problems
    assert message in mapping.errors[0].message
    assert mapping.errors[0].line == 7


def test_duplicate_identical_rows_are_ignored_and_single_url_warns():
    mapping = parse_mapping(LONG + "home,en-GB,https://example.com/en/\nsolo,en,https://example.com/solo/\n")
    assert mapping.errors == []
    assert [w.message for w in mapping.warnings] == ["group 'solo' has only one URL, so it has no alternates"]


def test_unreadable_mappings():
    with pytest.raises(MappingError, match="empty"):
        parse_mapping("\n# just a comment\n")
    with pytest.raises(MappingError, match="group"):
        parse_mapping("hreflang,url\nen,https://example.com/\n")


def test_sitemap_round_trips_through_the_parser():
    mapping = parse_mapping(LONG + "home,fr,https://example.com/fr/?a=1&b=2\n")
    doc = parse_sitemap(render_sitemap(mapping).encode("utf-8"))
    assert doc.warnings == []
    entries = {e.loc: e.alternates for e in doc.entries}
    assert set(entries) == {
        "https://example.com/en/",
        "https://example.com/de/",
        "https://example.com/fr/?a=1&b=2",
        "https://example.com/en/about/",
        "https://example.com/de/ueber-uns/",
    }
    # Every page lists the whole set, itself included, so return links are complete.
    for loc, alternates in entries.items():
        assert loc in [href for _, href in alternates]
    assert ("fr", "https://example.com/fr/?a=1&b=2") in entries["https://example.com/de/"]


def test_html_and_headers_round_trip_through_the_parsers():
    mapping = parse_mapping(LONG)
    html = render_html(mapping)
    first_block = html.split("\n\n")[0]
    doc = parse_html(f"<html><head>{first_block}</head><body></body></html>")
    assert [(a.hreflang, a.href) for a in doc.alternates] == mapping.alternates()["https://example.com/en/"]
    headers = render_headers(mapping).split("\n\n")[0].split("Link: ", 1)[1].strip()
    links = parse_link_header([headers])
    assert [(link.hreflang, link.uri) for link in links] == mapping.alternates()["https://example.com/en/"]
    data = json.loads(render_json(mapping))
    assert data["https://example.com/de/"][0] == {"hreflang": "en-GB", "href": "https://example.com/en/"}


def test_cli_generate(tmp_path, capsys):
    src = tmp_path / "mapping.csv"
    src.write_text(WIDE, encoding="utf-8")
    out = tmp_path / "sitemap.xml"
    assert main(["generate", str(src), "-o", str(out), "--x-default", "en-GB"]) == 0
    assert "wrote" in capsys.readouterr().err
    assert 'hreflang="x-default" href="https://example.com/en/"' in out.read_text(encoding="utf-8")

    assert main(["generate", str(src), "-f", "html"]) == 0
    assert '<link rel="alternate" hreflang="fr" href="https://example.com/fr/">' in capsys.readouterr().out

    bad = tmp_path / "bad.csv"
    bad.write_text(LONG + "home,en-uk,https://example.com/uk/\n", encoding="utf-8")
    target = tmp_path / "never.xml"
    assert main(["generate", str(bad), "-o", str(target)]) == 1
    err = capsys.readouterr().err
    assert "line 7: error" in err and "nothing was written" in err
    assert not target.exists()

    assert main(["generate", str(tmp_path / "missing.csv")]) == 2
