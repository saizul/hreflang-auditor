"""Parse and validate a single hreflang value.

Google Search accepts ``x-default`` or ``language[-Script][-REGION]`` where the
language is ISO 639-1, the optional script is ISO 15924 and the optional region
is ISO 3166-1 alpha-2. The value is case-insensitive, a region code on its own
is not allowed and codes outside those standards (for example ``es-419``) are
not supported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from . import codes
from .models import Severity

_ALPHA = re.compile(r"^[A-Za-z]+$")
_DIGITS = re.compile(r"^[0-9]+$")


@dataclass(frozen=True)
class CodeFinding:
    rule: str
    severity: Severity
    message: str
    suggestion: Optional[str] = None


@dataclass(frozen=True)
class HreflangCode:
    raw: str
    language: Optional[str] = None
    script: Optional[str] = None
    region: Optional[str] = None
    is_x_default: bool = False
    findings: List[CodeFinding] = field(default_factory=list, compare=False, hash=False)

    @property
    def valid(self) -> bool:
        return not any(f.severity is Severity.ERROR for f in self.findings)

    @property
    def canonical(self) -> str:
        """The value in conventional case (``en-GB``, ``zh-Hant-TW``, ``x-default``)."""
        if self.is_x_default:
            return "x-default"
        parts = [p for p in (self.language, self.script, self.region) if p]
        return "-".join(parts) if parts else self.raw.strip()

    @property
    def key(self) -> str:
        """Case-folded comparison key."""
        return self.canonical.lower()

    @property
    def suggestion(self) -> Optional[str]:
        for finding in self.findings:
            if finding.suggestion:
                return finding.suggestion
        return None


def _finding(rule: str, severity: Severity, message: str, suggestion: Optional[str] = None):
    return CodeFinding(rule, severity, message, suggestion)


def parse_hreflang(value: str) -> HreflangCode:
    """Parse ``value`` and collect every problem found with it."""
    findings: List[CodeFinding] = []
    raw = value if value is not None else ""
    text = raw.strip()

    if text != raw:
        findings.append(
            _finding(
                "code-whitespace",
                Severity.WARNING,
                f"hreflang value {raw!r} has leading or trailing whitespace",
                text,
            )
        )

    if not text:
        findings.append(_finding("invalid-format", Severity.ERROR, "hreflang value is empty"))
        return HreflangCode(raw=raw, findings=findings)

    if text.lower() == "x-default":
        if text != "x-default":
            findings.append(
                _finding(
                    "non-canonical-case",
                    Severity.NOTICE,
                    f"{text!r} works (values are case-insensitive) but is usually written x-default",
                    "x-default",
                )
            )
        return HreflangCode(raw=raw, is_x_default=True, findings=findings)

    if "_" in text:
        fixed = text.replace("_", "-")
        findings.append(
            _finding(
                "underscore-separator",
                Severity.ERROR,
                f"{text!r} uses an underscore; hreflang subtags are separated by a hyphen",
                _conventional_case(fixed),
            )
        )
        text = fixed

    parts = text.split("-")
    if any(not p for p in parts):
        findings.append(
            _finding("invalid-format", Severity.ERROR, f"{text!r} has an empty subtag")
        )
        return HreflangCode(raw=raw, findings=findings)

    language_part = parts[0]
    rest = parts[1:]
    language: Optional[str] = None
    script: Optional[str] = None
    region: Optional[str] = None

    # --- language -------------------------------------------------------
    lower = language_part.lower()
    if not _ALPHA.match(language_part):
        findings.append(
            _finding(
                "invalid-language",
                Severity.ERROR,
                f"{language_part!r} is not an ISO 639-1 language code",
            )
        )
    elif len(language_part) == 2:
        language = lower
        if lower in codes.LANGUAGE_MISTAKES:
            fix = codes.LANGUAGE_MISTAKES[lower]
            findings.append(
                _finding(
                    "known-mistake-language",
                    Severity.ERROR,
                    f"{language_part!r} is not a language code; did you mean {fix!r}?",
                    _rebuild(fix, rest),
                )
            )
        elif not codes.is_language(lower):
            if codes.is_region(lower) and not rest:
                findings.append(
                    _finding(
                        "region-only",
                        Severity.ERROR,
                        f"{language_part!r} looks like a country code on its own; "
                        "hreflang needs a language first (for example en-"
                        f"{language_part.upper()})",
                    )
                )
            else:
                findings.append(
                    _finding(
                        "invalid-language",
                        Severity.ERROR,
                        f"{language_part!r} is not an ISO 639-1 language code",
                    )
                )
        elif lower in codes.SUSPICIOUS_LANGUAGES:
            fix = codes.SUSPICIOUS_LANGUAGES[lower]
            name = codes.language_name(lower)
            findings.append(
                _finding(
                    "suspicious-language",
                    Severity.WARNING,
                    f"{lower!r} is {name}; if you meant {codes.language_name(fix)} use {fix!r}",
                    _rebuild(fix, rest),
                )
            )
    elif len(language_part) == 3:
        findings.append(
            _finding(
                "three-letter-language",
                Severity.ERROR,
                f"{language_part!r} is a three-letter code; Google expects ISO 639-1 two-letter codes",
            )
        )
    else:
        findings.append(
            _finding(
                "invalid-language",
                Severity.ERROR,
                f"{language_part!r} is not an ISO 639-1 language code",
            )
        )

    # --- script and region ------------------------------------------------
    index = 0
    if index < len(rest) and len(rest[index]) == 4 and _ALPHA.match(rest[index]):
        script = rest[index].title()
        if not codes.is_script(script):
            findings.append(
                _finding(
                    "unknown-script",
                    Severity.WARNING,
                    f"{rest[index]!r} is not a known ISO 15924 script code",
                )
            )
        index += 1

    if index < len(rest):
        part = rest[index]
        upper = part.upper()
        if _DIGITS.match(part):
            findings.append(
                _finding(
                    "unsupported-region",
                    Severity.ERROR,
                    f"{part!r} is a UN M.49 area code; Google only supports ISO 3166-1 alpha-2 "
                    "regions, so use the language alone or list each country",
                    language,
                )
            )
        elif len(part) != 2 or not _ALPHA.match(part):
            findings.append(
                _finding(
                    "invalid-region",
                    Severity.ERROR,
                    f"{part!r} is not an ISO 3166-1 alpha-2 region code",
                )
            )
        elif upper in codes.REGION_MISTAKES:
            fix = codes.REGION_MISTAKES[upper]
            region = upper
            findings.append(
                _finding(
                    "known-mistake-region",
                    Severity.ERROR,
                    f"{upper!r} is not an ISO 3166-1 code; use {fix!r} "
                    f"({codes.region_name(fix)})",
                    "-".join(p for p in (language, script, fix) if p),
                )
            )
        elif upper in codes.RESERVED_REGIONS:
            region = upper
            findings.append(
                _finding(
                    "reserved-region",
                    Severity.ERROR,
                    f"{upper!r} is a reserved or user-assigned code, not a country; "
                    "Google ignores it",
                )
            )
        elif not codes.is_region(upper):
            findings.append(
                _finding(
                    "invalid-region",
                    Severity.ERROR,
                    f"{part!r} is not an ISO 3166-1 alpha-2 region code",
                )
            )
        else:
            region = upper
        index += 1

    if index < len(rest):
        findings.append(
            _finding(
                "invalid-format",
                Severity.ERROR,
                f"{text!r} has unexpected extra subtags {'-'.join(rest[index:])!r}; "
                "use language[-Script][-REGION]",
            )
        )

    code = HreflangCode(raw=raw, language=language, script=script, region=region, findings=findings)

    if code.valid and text != code.canonical and "_" not in raw:
        findings.append(
            _finding(
                "non-canonical-case",
                Severity.NOTICE,
                f"{text!r} works (values are case-insensitive) but the conventional form is "
                f"{code.canonical!r}",
                code.canonical,
            )
        )
    return code


def _rebuild(language: str, rest: List[str]) -> str:
    return _conventional_case("-".join([language, *rest]))


def _conventional_case(value: str) -> str:
    parts = value.split("-")
    out = [parts[0].lower()]
    for part in parts[1:]:
        if len(part) == 4 and part.isalpha():
            out.append(part.title())
        elif len(part) == 2:
            out.append(part.upper())
        else:
            out.append(part)
    return "-".join(out)
