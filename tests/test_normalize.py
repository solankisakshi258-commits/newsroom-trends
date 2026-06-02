from newsroom_trends.models import SourceType
from newsroom_trends.normalize import clean_text, normalize, normalize_all

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
