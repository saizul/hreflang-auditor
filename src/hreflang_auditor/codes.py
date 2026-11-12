"""Bundled ISO code tables used to validate hreflang values.

The tables live in ``hreflang_auditor/data`` as tab-separated files so they can be
reviewed and updated without touching code.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Dict, Optional

#: Invalid language subtags that are almost always a typo for a valid code.
LANGUAGE_MISTAKES: Dict[str, str] = {
    "jp": "ja",  # Japan (country) used instead of Japanese
    "cn": "zh",  # China (country) used instead of Chinese
    "gr": "el",  # Greece instead of Greek
    "dk": "da",  # Denmark instead of Danish
    "cz": "cs",  # Czechia instead of Czech
    "ua": "uk",  # Ukraine instead of Ukrainian
    "vn": "vi",  # Viet Nam instead of Vietnamese
    "sp": "es",  # informal abbreviation for Spanish
    "al": "sq",  # Albania instead of Albanian
    "rs": "sr",  # Serbia instead of Serbian
    "iw": "he",  # withdrawn ISO 639 code for Hebrew
    "in": "id",  # withdrawn ISO 639 code for Indonesian
    "ji": "yi",  # withdrawn ISO 639 code for Yiddish
    "ge": "ka",  # Georgia (country) instead of Georgian
}

#: Valid ISO 639-1 codes that are frequently used by mistake for another language.
SUSPICIOUS_LANGUAGES: Dict[str, str] = {
    "kr": "ko",  # Kanuri, usually meant to be Korean
    "se": "sv",  # Northern Sami, usually meant to be Swedish
    "ee": "et",  # Ewe, usually meant to be Estonian
    "my": "ms",  # Burmese, usually meant to be Malay (Malaysia)
}

#: Region subtags that are not valid ISO 3166-1 alpha-2 codes but have a clear fix.
REGION_MISTAKES: Dict[str, str] = {
    "UK": "GB",
    "EL": "GR",
}

#: Reserved, exceptionally reserved or user-assigned codes. Google ignores them.
RESERVED_REGIONS = frozenset(
    {"EU", "EZ", "UN", "AC", "CP", "DG", "EA", "IC", "TA", "XK", "QO", "AA", "ZZ"}
)


def _load(name: str) -> Dict[str, str]:
    text = resources.files("hreflang_auditor").joinpath("data", name).read_text("utf-8")
    table: Dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        code, _, label = line.partition("\t")
        table[code.strip()] = label.strip()
    return table


@lru_cache(maxsize=None)
def languages() -> Dict[str, str]:
    """ISO 639-1 codes (lower case) mapped to English names."""
    return _load("iso639-1.tsv")


@lru_cache(maxsize=None)
def regions() -> Dict[str, str]:
    """ISO 3166-1 alpha-2 codes (upper case) mapped to English names."""
    return _load("iso3166-1.tsv")


@lru_cache(maxsize=None)
def scripts() -> Dict[str, str]:
    """ISO 15924 script codes (title case) mapped to English names."""
    return _load("iso15924.tsv")


def is_language(code: str) -> bool:
    return code.lower() in languages()


def is_region(code: str) -> bool:
    return code.upper() in regions()


def is_script(code: str) -> bool:
    return code.title() in scripts()


def language_name(code: str) -> Optional[str]:
    return languages().get(code.lower())


def region_name(code: str) -> Optional[str]:
    return regions().get(code.upper())


def describe(code: str) -> str:
    """Human label for a normalised hreflang value, e.g. ``en-GB`` -> ``English (United Kingdom)``."""
    if code.lower() == "x-default":
        return "x-default (fallback)"
    parts = code.split("-")
    lang = language_name(parts[0]) or parts[0]
    extra = []
    for part in parts[1:]:
        if len(part) == 4:
            extra.append(scripts().get(part.title(), part))
        else:
            extra.append(region_name(part) or part)
    return f"{lang} ({', '.join(extra)})" if extra else lang
