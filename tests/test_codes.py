from hreflang_auditor import codes


def test_language_table_is_complete_iso_639_1():
    table = codes.languages()
    assert len(table) == 183
    assert all(len(c) == 2 and c.islower() for c in table)
    for code in ("en", "de", "bn", "zh", "ja", "uk", "he", "id", "nb", "nn"):
        assert code in table


def test_withdrawn_language_codes_are_not_valid():
    for code in ("iw", "in", "ji", "bh"):
        assert not codes.is_language(code)


def test_region_table_is_complete_iso_3166_1():
    table = codes.regions()
    assert len(table) == 249
    assert all(len(c) == 2 and c.isupper() for c in table)
    for code in ("GB", "US", "BD", "DE", "IN", "SS", "AX"):
        assert code in table


def test_reserved_regions_are_not_in_table():
    for code in ("UK", "EU", "UN", "XK", "EL"):
        assert not codes.is_region(code)


def test_lookups_are_case_insensitive():
    assert codes.is_language("EN")
    assert codes.is_region("gb")
    assert codes.is_script("hant")
    assert codes.language_name("BN") == "Bengali"
    assert codes.region_name("bd") == "Bangladesh"


def test_describe():
    assert codes.describe("en-GB") == "English (United Kingdom)"
    assert codes.describe("zh-Hant-TW") == "Chinese (Han (Traditional), Taiwan)"
    assert codes.describe("x-default") == "x-default (fallback)"
    assert codes.describe("qq") == "qq"


def test_mistake_tables_point_at_valid_codes():
    for wrong, right in codes.LANGUAGE_MISTAKES.items():
        assert not codes.is_language(wrong)
        assert codes.is_language(right)
    for wrong, right in codes.SUSPICIOUS_LANGUAGES.items():
        assert codes.is_language(wrong)
        assert codes.is_language(right)
    for wrong, right in codes.REGION_MISTAKES.items():
        assert not codes.is_region(wrong)
        assert codes.is_region(right)
