"""Registry of every rule the auditor can report.

Each rule has a stable id that can be used with ``--disable`` and
``--severity`` on the command line and in JSON/CSV output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .models import Severity

E, W, N = Severity.ERROR, Severity.WARNING, Severity.NOTICE


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    category: str
    title: str
    help: str


_RULES: List[Rule] = [
    # -- value syntax --------------------------------------------------------
    Rule("invalid-format", E, "code", "Malformed hreflang value",
         "Use x-default or language[-Script][-REGION], for example de, en-GB or zh-Hant-TW."),
    Rule("underscore-separator", E, "code", "Underscore in hreflang value",
         "Subtags are separated by a hyphen: en-US, not en_US."),
    Rule("invalid-language", E, "code", "Unknown language code",
         "The first subtag must be an ISO 639-1 two-letter language code."),
    Rule("three-letter-language", E, "code", "Three-letter language code",
         "Google documents ISO 639-1 (two-letter) language codes for hreflang."),
    Rule("region-only", E, "code", "Region without a language",
         "A country code cannot be used on its own; prefix it with a language (en-IE)."),
    Rule("known-mistake-language", E, "code", "Country code used as a language",
         "Common mistakes: jp (use ja), cn (use zh), dk (use da), gr (use el), ua (use uk)."),
    Rule("suspicious-language", W, "code", "Valid but probably unintended language",
         "kr is Kanuri, se is Northern Sami, ee is Ewe, my is Burmese. Check the intent."),
    Rule("invalid-region", E, "code", "Unknown region code",
         "The region must be an ISO 3166-1 alpha-2 country code."),
    Rule("known-mistake-region", E, "code", "Common region mistake",
         "UK is not an ISO 3166-1 code; the United Kingdom is GB (en-GB). EL is GR."),
    Rule("reserved-region", E, "code", "Reserved region code",
         "Codes such as EU, UN or XK are reserved or user-assigned and have no effect."),
    Rule("unsupported-region", E, "code", "Unsupported numeric region",
         "UN M.49 area codes such as es-419 are not supported; list each country instead."),
    Rule("unknown-script", W, "code", "Unknown script subtag",
         "The optional script must be an ISO 15924 code such as Hans, Hant, Latn or Cyrl."),
    Rule("non-canonical-case", N, "code", "Unconventional letter case",
         "hreflang values are case-insensitive. Conventional form: en-GB, zh-Hant, x-default."),
    Rule("code-whitespace", W, "code", "Whitespace around hreflang value",
         "Remove spaces inside the hreflang attribute value."),
    # -- URLs ---------------------------------------------------------------------
    Rule("relative-url", E, "url", "Relative alternate URL",
         "Alternate URLs must be fully qualified, including the protocol."),
    Rule("protocol-relative-url", E, "url", "Protocol-relative alternate URL",
         "Write https://example.com/page, not //example.com/page."),
    Rule("invalid-url", E, "url", "Unusable alternate URL",
         "The href is empty or does not use http or https."),
    Rule("mixed-protocol", W, "url", "Mixed http and https alternates",
         "All versions in a set should use the protocol the site is actually served on."),
    # -- placement -----------------------------------------------------------------
    Rule("link-outside-head", E, "placement", "hreflang link outside <head>",
         "Google only reads hreflang <link> elements inside a well-formed <head>. An element "
         "that is not allowed in <head> (img, div, iframe) closes it early."),
    Rule("media-attribute", W, "placement", "hreflang combined with media",
         "Do not combine hreflang with other attributes such as media in a single <link>."),
    # -- set structure -------------------------------------------------------------
    Rule("missing-self-reference", W, "set", "Missing self-referencing hreflang",
         "Each version should list itself as well as all other versions."),
    Rule("missing-return-link", E, "set", "Missing return link",
         "If page X links to page Y, page Y must link back to X, otherwise the annotations "
         "may be ignored."),
    Rule("missing-x-default", N, "set", "No x-default",
         "x-default is optional but recommended for the fallback or language selector page."),
    Rule("duplicate-hreflang", E, "set", "Same hreflang points to different URLs",
         "Each language code (including x-default) may appear once per page with one URL."),
    Rule("duplicate-annotation", N, "set", "Repeated identical annotation",
         "The same hreflang/URL pair is declared more than once in the same source."),
    Rule("one-url-many-languages", N, "set", "One URL for several languages",
         "A single URL is declared for different languages. Check this is intended."),
    Rule("inconsistent-set", W, "set", "Incomplete or inconsistent set",
         "The set of hreflang annotations should be identical on every version."),
    Rule("cluster-code-conflict", W, "set", "Pages disagree on a language URL",
         "Different versions declare different URLs for the same hreflang value."),
    Rule("conflicting-sources", W, "set", "Sources disagree",
         "HTML, HTTP headers and the sitemap declare different sets for the same page."),
    # -- target and page status ------------------------------------------------------
    Rule("target-non-200", E, "target", "Alternate URL does not return 200",
         "Alternate URLs should return 200 OK. 4xx and 5xx targets are dropped."),
    Rule("target-redirect", E, "target", "Alternate URL redirects",
         "Point hreflang at the final URL rather than at a redirect."),
    Rule("target-noindex", E, "target", "Alternate URL is noindex",
         "A noindex page cannot be shown as an alternate in search results."),
    Rule("target-canonical-mismatch", E, "target", "Alternate URL is canonicalised elsewhere",
         "hreflang and rel=canonical conflict: the target declares another URL as canonical. "
         "Point hreflang at canonical URLs only."),
    Rule("target-unreachable", W, "target", "Alternate URL could not be fetched",
         "The request failed (DNS, TLS, timeout or connection error)."),
    Rule("target-blocked", W, "target", "Alternate URL blocked by robots.txt",
         "Search engines cannot crawl the target to confirm the return link."),
    Rule("page-canonical-conflict", E, "page", "Page with hreflang is canonicalised elsewhere",
         "The page declares hreflang annotations but its canonical points to another URL."),
    Rule("page-noindex", W, "page", "Page with hreflang is noindex",
         "hreflang on a noindex page has no effect."),
    Rule("html-lang-mismatch", N, "page", "html lang disagrees with hreflang",
         "The target's <html lang> names a different language than the hreflang pointing to "
         "it. Google does not use the lang attribute, but the mismatch often reveals a mistake."),
    # -- crawl --------------------------------------------------------------------
    Rule("sitemap-error", E, "crawl", "Sitemap could not be read",
         "The sitemap failed to download or parse."),
    Rule("sitemap-warning", W, "crawl", "Sitemap structure problem",
         "For example the xhtml namespace is missing or wrong, so alternates are ignored."),
    Rule("robots-unavailable", N, "crawl", "robots.txt unavailable",
         "robots.txt returned an error or could not be fetched; see the message for the effect."),
]

RULES: Dict[str, Rule] = {rule.id: rule for rule in _RULES}


def get(rule_id: str) -> Rule:
    return RULES[rule_id]


def all_rules() -> List[Rule]:
    return list(_RULES)
