from __future__ import annotations

from pathlib import Path


class LocalSemanticRanker:
    """Optional local-only ranker. Construction fails if model files are absent."""

    def __init__(self, model_dir: Path, model_name: str) -> None:
        self.model_path = model_dir / model_name.replace("/", "--")
        if not self.model_path.exists():
            raise FileNotFoundError(f"local embedding model missing: {self.model_path.name}")

    @property
    def available(self) -> bool:
        return self.model_path.exists()
