from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize("flag", ["enable_embeddings", "enable_reranker"])
def test_unimplemented_ranking_capability_flags_fail_closed(flag: str) -> None:
    flags = {"enable_embeddings": False, "enable_reranker": False}
    flags[flag] = True
    with pytest.raises(ValidationError, match="implements lexical ranking only"):
        Settings(**flags)


def test_disabled_flags_report_only_implemented_ranking_mode() -> None:
    settings = Settings(enable_embeddings=False, enable_reranker=False)

    assert settings.enable_embeddings is False
    assert settings.enable_reranker is False
