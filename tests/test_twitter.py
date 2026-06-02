"""Tests for the X/Twitter trends scraper parsing (no network)."""

from newsroom_trends.connectors.twitter import TwitterConnector, _ITEM_RE

SAMPLE_HTML = """
<ol class="trend-card__list">
  <li><a href="https://twitter.com/search?q=%23Election2026" class="trend-link">#Election2026</a>
      <span class="tweet-count">125K Tweets</span></li>
  <li><a href="https://twitter.com/search?q=Virat" class="trend-link">Virat Kohli</a>
      <span class="tweet-count">1.2M Tweets</span></li>
  <li><a href="https://twitter.com/search?q=Monsoon" class="trend-link">Monsoon</a></li>
</ol>
"""


def test_item_regex_extracts_trends_and_counts():
    matches = [(m.group(1).strip(), m.group(2)) for m in _ITEM_RE.finditer(SAMPLE_HTML)]
    names = [n for n, _ in matches]
    assert "#Election2026" in names
    assert "Virat Kohli" in names
    assert "Monsoon" in names
    counts = dict(matches)
    assert counts["#Election2026"].strip() == "125K"
    assert counts["Virat Kohli"].strip() == "1.2M"


def test_parse_volume_handles_suffixes():
    assert TwitterConnector._parse_volume("125K") == 125_000
    assert TwitterConnector._parse_volume("1.2M") == 1_200_000
    assert TwitterConnector._parse_volume("3,500") == 3500
    assert TwitterConnector._parse_volume(None) == 0.0
    assert TwitterConnector._parse_volume("") == 0.0
