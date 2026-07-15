from app.models import SearchResult
from app.search.deduplication import deduplicate_results
from app.search.normalization import normalize_result


def test_deduplicates_canonical_urls_and_merges_engines() -> None:
    items = [
        normalize_result(
            SearchResult(url="https://example.com/x?utm_source=a", title="Example", engine="a")
        ),
        normalize_result(SearchResult(url="https://example.com/x", title="Example", engine="b")),
    ]
    output = deduplicate_results(items)
    assert len(output) == 1
    assert output[0].engines == ["a", "b"]
