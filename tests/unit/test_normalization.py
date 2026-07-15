from app.models import SearchResult
from app.search.normalization import normalize_result, normalize_url


def test_tracking_parameters_and_fragments_are_removed() -> None:
    assert (
        normalize_url("HTTPS://Example.COM:443/a/?utm_source=x&b=2#part")
        == "https://example.com/a?b=2"
    )


def test_result_fields_are_normalized() -> None:
    value = normalize_result(
        SearchResult(url="https://EXAMPLE.com", title=" A   title ", engines=["b", "a", "a"])
    )
    assert value.domain == "example.com"
    assert value.title == "A title"
    assert value.engines == ["a", "b"]
