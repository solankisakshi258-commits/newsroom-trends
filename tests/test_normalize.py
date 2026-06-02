from newsroom_trends.models import SourceType
from newsroom_trends.normalize import (
    clean_text,
    has_disallowed_script,
    normalize,
    normalize_all,
)

from .factories import raw


def test_clean_text_preserves_hindi_strips_markup():
    out = clean_text('<p>मोदी सरकार का <b>बड़ा</b> फैसला</p> https://x.com/a')
    assert "मोदी" in out and "सरकार" in out
    assert "<" not in out and "http" not in out


def test_normalize_builds_stable_id_and_text():
    r = raw("क्रिकेट टीम की जीत", summary="भारत ने मैच जीता")
    s = normalize(r)
    assert s.id == normalize(r).id  # stable
    assert "क्रिकेट" in s.text
    assert s.source_type == SourceType.RSS


def test_normalize_all_dedups_by_url():
    a = raw("समान खबर", url="https://example.com/same")
    b = raw("समान खबर भिन्न शीर्षक", url="https://example.com/same")
    out = normalize_all([a, b])
    assert len(out) == 1


def test_normalize_all_skips_empty_titles():
    assert normalize_all([raw("")]) == []


def test_has_disallowed_script_detects_other_languages():
    assert has_disallowed_script("எடப்பாடி கே. பழனிசாமி")   # Tamil
    assert has_disallowed_script("ఇందిరమ్మ ఇళ్ల పథకం")        # Telugu
    assert has_disallowed_script("ঋতব্রত ব্যানার্জী")          # Bengali
    assert not has_disallowed_script("शशि थरूर")               # Hindi (Devanagari) ok
    assert not has_disallowed_script("elina svitolina")        # English (Latin) ok
    assert not has_disallowed_script("मोदी government 2026")   # Hindi+English mix ok


def test_normalize_all_keeps_only_english_and_hindi():
    raws = [
        raw("शशि थरूर"),                 # Hindi -> keep
        raw("elina svitolina"),          # English -> keep
        raw("எடப்பாடி கே. பழனிசாமி"),    # Tamil -> drop
        raw("ఇందిరమ్మ ఇళ్ల పథకం"),       # Telugu -> drop
    ]
    titles = {s.title for s in normalize_all(raws, restrict_languages=True)}
    assert titles == {"शशि थरूर", "elina svitolina"}


def test_normalize_all_can_disable_language_filter():
    raws = [raw("எடப்பாடி கே. பழனிசாமி")]
    assert len(normalize_all(raws, restrict_languages=False)) == 1
