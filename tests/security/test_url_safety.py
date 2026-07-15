import pytest

from app.fetch.url_safety import UnsafeUrlError, validate_url


@pytest.mark.security
@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://[::1]/x",
        "http://169.254.169.254/latest/meta-data",
        "http://2130706433/x",
        "http://0x7f000001/x",
        "http://0177.0000.0000.0001/x",
        "http://metadata.google.internal/x",
        "http://searxng/x",
        "http://user:pass@example.com/x",
        "javascript:alert(1)",
        "data:text/plain,test",
    ],
)
def test_blocked_url_forms(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url(url)


@pytest.mark.security
def test_public_http_url_allowed() -> None:
    assert validate_url("https://example.com/path") == "https://example.com/path"
