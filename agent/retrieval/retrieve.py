"""retrieve(query, k) -> the k most similar policy chunks (cosine similarity over L2-normalised embeddings)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .index import INDEX_PATH, Index, build_index, load_index

_INDEX: Index | None = None


def get_index(path: Path | str = INDEX_PATH) -> Index:
    """The index, loaded once per process; built from docs/policies if the file does not exist yet."""
    global _INDEX
    if _INDEX is None:
        _INDEX = load_index(path) if Path(path).exists() else build_index(out=path)
    return _INDEX


def retrieve(query: str, k: int = 4, index: Index | None = None) -> list[dict]:
    """Return up to k chunks as dicts: doc, title, heading, text, part, score (cosine, higher is better)."""
    index = index or get_index()
    q = index.embedder.embed([query])[0]
    # elementwise rather than `@`: Accelerate's float32 matmul raises spurious FP warnings on Apple Silicon,
    # and at a few dozen chunks BLAS buys nothing
    scores = (index.embeddings * q).sum(axis=1)
    top = np.argsort(-scores)[:k]
    return [{**index.chunks[i].to_dict(), "score": round(float(scores[i]), 4)} for i in top]


if __name__ == "__main__":
    import sys
    for hit in retrieve(" ".join(sys.argv[1:]) or "How long is the refund window for gold customers?"):
        print(f"{hit['score']:.3f}  {hit['doc']} › {hit['heading']}")
