from app.search.searxng import _categories_for_query


def test_searxng_adds_relevant_verticals_without_dropping_general() -> None:
    assert _categories_for_query("Python HTTP API release") == "general,it"
    assert _categories_for_query("peer-reviewed science paper") == "general,science"
    assert _categories_for_query("breaking election news today") == "general,news"
    assert _categories_for_query("ordinary factual question") == "general"
