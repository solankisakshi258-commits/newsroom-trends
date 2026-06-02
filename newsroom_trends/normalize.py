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


def normalize_all(raws: list[RawSignal]) -> list[Signal]:
    """Normalize and in-memory dedup by id (later sources don't overwrite earlier)."""
    seen: dict[str, Signal] = {}
    for raw in raws:
        if not (raw.title or "").strip():
            continue
        sig = normalize(raw)
        seen.setdefault(sig.id, sig)
    return list(seen.values())
