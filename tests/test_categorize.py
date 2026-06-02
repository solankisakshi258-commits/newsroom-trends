from newsroom_trends.categorize import categorize_clusters, classify
from newsroom_trends.models import StoryCluster


def test_classify_politics_hindi_and_english():
    assert classify("चुनाव में बीजेपी और कांग्रेस की टक्कर") == "Politics"
    assert classify("Election results: BJP wins, Congress concedes") == "Politics"


def test_classify_cricket():
    assert classify("भारत ने क्रिकेट विश्व कप का फाइनल जीता") == "Cricket & Sports"
    assert classify("India wins the cricket world cup final match") == "Cricket & Sports"


def test_classify_business_and_crime():
    assert classify("सेंसेक्स और निफ्टी में तेजी, शेयर बाजार उछला") == "Business & Economy"
    assert classify("Police arrest accused in murder case") == "Crime & Law"


def test_unmatched_is_general():
    assert classify("a quiet ordinary afternoon stroll") == "General"


def test_categorize_clusters_sets_field():
    c = StoryCluster(id="x", label="क्रिकेट मैच में भारत की जीत", keywords=["cricket"], signals=[])
    categorize_clusters([c])
    assert c.category == "Cricket & Sports"
