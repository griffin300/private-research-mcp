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


def test_identical_snippets_from_independent_domains_are_retained() -> None:
    results = [
        normalize_result(
            SearchResult(
                url="https://secondary.example/fact",
                title="Release details",
                snippet="The release date was October 2, 2023.",
            )
        ),
        normalize_result(
            SearchResult(
                url="https://python.org/release",
                title="Official release",
                snippet="The release date was October 2, 2023.",
            )
        ),
    ]
    assert len(deduplicate_results(results)) == 2
