"""Lightweight, deterministic trend categorisation (Hindi + English keywords).

No ML — each category has a bilingual keyword lexicon; a cluster is scored by how many
distinct category keywords appear in its text (label + keywords + signal titles), and the
top-scoring category wins. Ties and no-match fall back to "General".

This is intentionally transparent and fast so it runs every cycle and is easy to tune:
add a word to a list and that's the whole change.
"""

from __future__ import annotations

import re

from .models import StoryCluster

# Order matters only for tie-breaking (earlier = preferred). Keywords are matched
# case-insensitively as whole tokens for Latin words and as substrings for Devanagari.
CATEGORIES: dict[str, list[str]] = {
    "Politics": [
        "election", "elections", "vote", "votes", "poll", "parliament", "minister",
        "government", "bjp", "congress", "modi", "rahul", "mla", "mp", "cabinet",
        "चुनाव", "सरकार", "मंत्री", "बीजेपी", "कांग्रेस", "मोदी", "राहुल", "सांसद",
        "विधायक", "संसद", "नेता", "पार्टी", "मतदान", "विपक्ष", "राजनीति",
    ],
    "Cricket & Sports": [
        "cricket", "match", "ipl", "odi", "test", "t20", "wicket", "runs", "batsman",
        "bowler", "world cup", "tournament", "football", "tennis", "olympic", "hockey",
        "क्रिकेट", "मैच", "विश्व कप", "खिलाड़ी", "टीम", "बल्लेबाज", "गेंदबाज", "विकेट",
        "फाइनल", "टेस्ट", "ओलंपिक", "खेल", "गोल", "टूर्नामेंट", "रन",
    ],
    "Entertainment": [
        "film", "movie", "bollywood", "actor", "actress", "song", "trailer", "box office",
        "ott", "web series", "cinema", "singer", "celebrity", "album",
        "फिल्म", "बॉलीवुड", "अभिनेता", "अभिनेत्री", "गाना", "गायक", "सिनेमा", "ट्रेलर",
        "वेब सीरीज", "टीवी", "बॉक्स ऑफिस", "सेलिब्रिटी",
    ],
    "Business & Economy": [
        "market", "share", "stock", "sensex", "nifty", "rupee", "gdp", "economy", "budget",
        "ipo", "inflation", "company", "gold", "petrol", "diesel", "profit", "revenue",
        "बाजार", "शेयर", "सेंसेक्स", "रुपया", "अर्थव्यवस्था", "बजट", "महंगाई", "कंपनी",
        "सोना", "पेट्रोल", "डीजल", "कीमत", "मुनाफा", "निवेश",
    ],
    "Crime & Law": [
        "murder", "crime", "arrest", "police", "rape", "fraud", "scam", "court", "accused",
        "attack", "fir", "cbi", "ed", "verdict", "jail",
        "हत्या", "अपराध", "गिरफ्तार", "पुलिस", "दुष्कर्म", "घोटाला", "केस", "कोर्ट",
        "आरोपी", "हमला", "जेल", "गिरफ्तारी", "अदालत", "मुकदमा",
    ],
    "Technology": [
        "tech", "mobile", "smartphone", "app", "ai", "gadget", "internet", "software",
        "google", "whatsapp", "instagram", "feature", "5g", "chatgpt", "iphone",
        "टेक", "मोबाइल", "स्मार्टफोन", "ऐप", "गैजेट", "इंटरनेट", "गूगल", "फीचर",
        "एआई", "तकनीक", "इलेक्ट्रॉनिक",
    ],
    "Auto": [
        "car", "bike", "scooter", "vehicle", "suv", "ev", "mileage", "launch", "motorcycle",
        "कार", "बाइक", "स्कूटर", "गाड़ी", "वाहन", "माइलेज", "मोटरसाइकिल", "इलेक्ट्रिक कार",
    ],
    "Weather & Disaster": [
        "weather", "rain", "monsoon", "cyclone", "earthquake", "flood", "heatwave",
        "temperature", "storm", "landslide",
        "मौसम", "बारिश", "मानसून", "तूफान", "भूकंप", "बाढ़", "गर्मी", "तापमान", "चक्रवात",
    ],
    "Health": [
        "health", "covid", "virus", "hospital", "disease", "vaccine", "doctor", "dengue",
        "cancer", "outbreak",
        "स्वास्थ्य", "वायरस", "अस्पताल", "बीमारी", "टीका", "डॉक्टर", "डेंगू", "इलाज", "संक्रमण",
    ],
    "Education": [
        "exam", "result", "board", "neet", "jee", "cuet", "admission", "university",
        "student", "school", "syllabus", "recruitment", "vacancy",
        "परीक्षा", "रिजल्ट", "बोर्ड", "एडमिशन", "यूनिवर्सिटी", "छात्र", "स्कूल", "भर्ती",
        "नौकरी", "पाठ्यक्रम",
    ],
    "World": [
        "pakistan", "china", "russia", "ukraine", "israel", "gaza", "trump", "putin", "un",
        "america", "usa", "uk", "iran",
        "पाकिस्तान", "चीन", "रूस", "यूक्रेन", "इजरायल", "गाजा", "अमेरिका", "ईरान", "विश्व",
        "अंतरराष्ट्रीय",
    ],
    "Religion & Festival": [
        "temple", "festival", "puja", "ram", "diwali", "holi", "eid", "yatra", "mandir",
        "मंदिर", "त्योहार", "पूजा", "राम", "दिवाली", "होली", "ईद", "यात्रा", "धार्मिक",
        "भगवान", "व्रत",
    ],
}

# Precompile Latin whole-word patterns; keep Devanagari terms for substring matching.
_LATIN = re.compile(r"[a-z]")
_COMPILED: dict[str, tuple[list[re.Pattern], list[str]]] = {}
for _cat, _words in CATEGORIES.items():
    _latin_words = [w for w in _words if _LATIN.search(w)]
    _deva_words = [w for w in _words if not _LATIN.search(w)]
    _patterns = [re.compile(rf"\b{re.escape(w)}\b") for w in _latin_words]
    _COMPILED[_cat] = (_patterns, _deva_words)


def classify(text: str) -> str:
    """Return the best-matching category for a block of text, or 'General'."""
    low = text.lower()
    best_cat, best_score = "General", 0
    for cat, (patterns, deva_words) in _COMPILED.items():
        score = sum(1 for p in patterns if p.search(low))
        score += sum(1 for w in deva_words if w in text)
        if score > best_score:
            best_cat, best_score = cat, score
    return best_cat


def categorize_clusters(clusters: list[StoryCluster]) -> None:
    """Set `category` on each cluster in place, using label + keywords + signal titles."""
    for c in clusters:
        parts = [c.label, " ".join(c.keywords)]
        parts.extend(s.title for s in c.signals[:8])
        c.category = classify(" ".join(parts))
