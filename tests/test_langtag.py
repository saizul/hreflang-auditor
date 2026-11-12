import pytest

from hreflang_auditor.langtag import parse_hreflang
from hreflang_auditor.models import Severity


def rules(value):
    return [f.rule for f in parse_hreflang(value).findings]


@pytest.mark.parametrize(
    "value, canonical",
    [
        ("en", "en"),
        ("de", "de"),
        ("en-GB", "en-GB"),
        ("bn-BD", "bn-BD"),
        ("zh-Hans", "zh-Hans"),
        ("zh-Hant-TW", "zh-Hant-TW"),
        ("sr-Latn-RS", "sr-Latn-RS"),
        ("x-default", "x-default"),
        ("pt-BR", "pt-BR"),
    ],
)
def test_valid_codes_have_no_findings(value, canonical):
    code = parse_hreflang(value)
    assert code.valid
    assert code.findings == []
    assert code.canonical == canonical


@pytest.mark.parametrize(
    "value, rule, suggestion",
    [
        ("en-uk", "known-mistake-region", "en-GB"),
        ("en-UK", "known-mistake-region", "en-GB"),
        ("el-EL", "known-mistake-region", "el-GR"),
        ("jp", "known-mistake-language", "ja"),
        ("cn-CN", "known-mistake-language", "zh-CN"),
        ("dk", "known-mistake-language", "da"),
        ("iw-IL", "known-mistake-language", "he-IL"),
        ("de_DE", "underscore-separator", "de-DE"),
        ("es-419", "unsupported-region", "es"),
    ],
)
def test_common_mistakes_have_suggestions(value, rule, suggestion):
    code = parse_hreflang(value)
    assert not code.valid
    assert rule in rules(value)
    assert code.suggestion == suggestion


@pytest.mark.parametrize(
    "value, rule",
    [
        ("gb", "region-only"),
        ("us", "region-only"),
        ("eng", "three-letter-language"),
        ("english", "invalid-language"),
        ("qq", "invalid-language"),
        ("e1", "invalid-language"),
        ("en-EU", "reserved-region"),
        ("en-UN", "reserved-region"),
        ("sq-XK", "reserved-region"),
        ("en-QQ", "invalid-region"),
        ("en-USA", "invalid-region"),
        ("en-US-x", "invalid-format"),
        ("en--US", "invalid-format"),
        ("", "invalid-format"),
        ("   ", "invalid-format"),
    ],
)
def test_invalid_codes(value, rule):
    code = parse_hreflang(value)
    assert not code.valid
    assert rule in rules(value)


@pytest.mark.parametrize("value, fixed", [("EN-gb", "en-GB"), ("en-us", "en-US"), ("ZH-hant", "zh-Hant"),
                                          ("X-Default", "x-default"), ("DE", "de")])
def test_wrong_case_is_valid_but_flagged(value, fixed):
    code = parse_hreflang(value)
    assert code.valid
    assert rules(value) == ["non-canonical-case"]
    assert code.findings[0].severity is Severity.NOTICE
    assert code.canonical == fixed


def test_key_is_case_insensitive():
    assert parse_hreflang("EN-gb").key == parse_hreflang("en-GB").key == "en-gb"


@pytest.mark.parametrize("value, fix", [("kr", "ko"), ("se-SE", "sv-SE"), ("ee", "et"), ("my-MY", "ms-MY")])
def test_suspicious_but_valid_languages_warn(value, fix):
    code = parse_hreflang(value)
    assert code.valid
    assert rules(value) == ["suspicious-language"]
    assert code.findings[0].severity is Severity.WARNING
    assert code.suggestion == fix


def test_unknown_script_is_warning_only():
    code = parse_hreflang("en-Zzzz-US")
    assert code.valid
    assert "unknown-script" in rules("en-Zzzz-US")
    assert code.region == "US"


def test_whitespace_is_flagged_and_stripped():
    code = parse_hreflang(" en-GB ")
    assert code.valid
    assert "code-whitespace" in rules(" en-GB ")
    assert code.canonical == "en-GB"


def test_x_default_is_recognised():
    code = parse_hreflang("x-default")
    assert code.is_x_default
    assert code.language is None


def test_parsed_parts():
    code = parse_hreflang("zh-hant-tw")
    assert (code.language, code.script, code.region) == ("zh", "Hant", "TW")
