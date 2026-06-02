"""RawSignal -> Signal normalization, with Hindi-aware text handling.

Goals:
  * Build the clustering `text` field from title + summary, stripped of HTML and noise.
  * Assign a stable dedup id.
  * Keep Devanagari intact while removing markup and URLs.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from .models import RawSignal, Signal

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")
_WS_RE = re.compile(r"\s+")
# Keep Devanagari (ऀ-ॿ), ASCII letters/digits, and basic whitespace.
_KEEP_RE = re.compile(r"[^ऀ-ॿa-zA-Z0-9\s]")

# Letter ranges of scripts we DROP when restricting to English + Hindi only.
# (We keep Latin/English and Devanagari/Hindi; everything here is "another language".)
_DISALLOWED_SCRIPT_RANGES = (
    (0x0980, 0x09FF),  # Bengali / Assamese
    (0x0A00, 0x0A7F),  # Gurmukhi (Punjabi)
    (0x0A80, 0x0AFF),  # Gujarati
    (0x0B00, 0x0B7F),  # Odia
    (0x0B80, 0x0BFF),  # Tamil
    (0x0C00, 0x0C7F),  # Telugu
    (0x0C80, 0x0CFF),  # Kannada
    (0x0D00, 0x0D7F),  # Malayalam
    (0x0D80, 0x0DFF),  # Sinhala
    (0x0600, 0x06FF),  # Arabic / Urdu
    (0x0700, 0x074F),  # Syriac
    (0x0E00, 0x0E7F),  # Thai
    (0x0370, 0x03FF),  # Greek
    (0x0400, 0x04FF),  # Cyrillic
    (0x3040, 0x30FF),  # Japanese kana
    (0x4E00, 0x9FFF),  # CJK (Chinese/Japanese/Korean ideographs)
    (0xAC00, 0xD7AF),  # Hangul (Korean)
)


def has_disallowed_script(text: str) -> bool:
    """True if `text` contains a letter from a script other than Latin or Devanagari."""
    for ch in text:
        o = ord(ch)
        if o < 0x0370:  # ASCII + Latin-1 + Latin Extended: always allowed, skip fast
            continue
        for lo, hi in _DISALLOWED_SCRIPT_RANGES:
            if lo <= o <= hi:
                return True
    return False


def clean_text(raw: str) -> str:
    """Strip HTML, URLs, and punctuation; collapse whitespace. Preserves Hindi."""
    if not raw:
        return ""
    txt = html.unescape(raw)
    txt = _TAG_RE.sub(" ", txt)
    txt = _URL_RE.sub(" ", txt)
    txt = _KEEP_RE.sub(" ", txt)
    return _WS_RE.sub(" ", txt).strip()


def normalize(raw: RawSignal) -> Signal:
    """Convert a single RawSignal into a normalized Signal."""
    title = (raw.title or "").strip()
    summary = raw.summary or ""
    text = clean_text(f"{title} {summary}")

    published = raw.published_at or datetime.now(timezone.utc)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)

    return Signal(
        id=Signal.make_id(raw.source_type, raw.url, title),
        source_type=raw.source_type,
        source_name=raw.source_name,
        title=title,
        text=text or title,
        url=raw.url,
        published_at=published,
        ingested_at=datetime.now(timezone.utc),
        engagement=max(0.0, float(raw.engagement)),
        lang=raw.lang,
        extra=dict(raw.extra),
    )


def normalize_all(raws: list[RawSignal], restrict_languages: bool = True) -> list[Signal]:
    """Normalize and in-memory dedup by id (later sources don't overwrite earlier).

    When `restrict_languages` is True, signals whose title is in a script other than
    Latin (English) or Devanagari (Hindi) are dropped — e.g. Tamil/Telugu/Bengali
    Google Trends entries."""
    seen: dict[str, Signal] = {}
    for raw in raws:
        title = (raw.title or "").strip()
        if not title:
            continue
        if restrict_languages and has_disallowed_script(title):
            continue
        sig = normalize(raw)
        seen.setdefault(sig.id, sig)
    return list(seen.values())
