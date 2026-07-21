"""
Tests for the one guarantee this whole tool is built around: the final text
never contains an em dash or en dash, no matter what the model produces.

Run with:  pytest
"""

from sanitize import contains_dash, find_banned_words, strip_ai_tells


def test_em_dash_becomes_comma():
    result = strip_ai_tells("Cosy fabric — handmade with care")
    assert "—" not in result
    assert result == "Cosy fabric, handmade with care"


def test_en_dash_number_range_becomes_hyphen():
    result = strip_ai_tells("Sizes 5–10 available")
    assert "–" not in result
    assert "5-10" in result


def test_en_dash_between_words_becomes_comma():
    result = strip_ai_tells("Warm – inviting – timeless")
    assert "–" not in result


def test_smart_quotes_normalised():
    result = strip_ai_tells("She said “hi” and it’s lovely")
    assert "“" not in result and "”" not in result
    assert "’" not in result
    assert '"hi"' in result
    assert "it's lovely" in result


def test_ellipsis_normalised():
    result = strip_ai_tells("Wait for it… amazing")
    assert "…" not in result
    assert "..." in result


def test_no_dangling_double_commas_or_spaces():
    result = strip_ai_tells("Soft — warm — cosy.")
    assert ",," not in result
    assert "  " not in result
    assert not result.startswith(",")


def test_contains_dash_detects_em_and_en_dash():
    assert contains_dash("a — b") is True
    assert contains_dash("a – b") is True
    assert contains_dash("a, b") is False


def test_strip_ai_tells_is_idempotent():
    """Running the sanitizer twice should never change an already-clean string."""
    once = strip_ai_tells("Cosy fabric — handmade with care, sizes 5–10.")
    twice = strip_ai_tells(once)
    assert once == twice


def test_strip_ai_tells_handles_empty_string():
    assert strip_ai_tells("") == ""
    assert strip_ai_tells(None) is None


def test_find_banned_words_whole_word_case_insensitive():
    hits = find_banned_words("This is a CHEAP basic candle.", ["cheap", "basic"])
    assert set(hits) == {"cheap", "basic"}


def test_find_banned_words_no_partial_matches():
    # "cap" should not match inside "capable" - whole-word only.
    hits = find_banned_words("This tool is very capable.", ["cap"])
    assert hits == []


def test_find_banned_words_none_found():
    assert find_banned_words("A lovely, well-made candle.", ["cheap", "basic"]) == []


def test_find_banned_words_handles_empty_inputs():
    assert find_banned_words("", ["cheap"]) == []
    assert find_banned_words("Some text", []) == []
