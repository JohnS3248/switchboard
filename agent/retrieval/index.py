"""Embed the policy chunks and persist them as a numpy matrix in data/retrieval.npz.

Embedding backends, in order of preference:
  1. "minilm": sentence-transformers/all-MiniLM-L6-v2 (384-d, L2-normalised) run through fastembed, which
     executes the same model with ONNX runtime. fastembed is used instead of the sentence-transformers package
     because that package cannot import on the development machine (its transformers dependency imports the
     locally installed torchvision, which needs the lzma module the local Python build lacks). The model
     (~90 MB) is downloaded once into the Hugging Face cache; after that everything runs offline.
  2. "tfidf": a small TF-IDF vectoriser written in numpy, used only when the neural model cannot be loaded (no
     cache and no network). It is a lexical fallback, NOT a neural embedding. The backend name is stored in the
     index file and printed by the evaluator so the two can never be confused in a report.

Storage is a plain .npz (embeddings, chunk metadata as JSON, backend name, TF-IDF vocabulary when relevant).
Six documents and a few dozen chunks do not justify a vector database and its dependency tree.

Build:  python -m agent.retrieval.index [--backend auto|minilm|tfidf]
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from math import log
from pathlib import Path

import numpy as np

from .chunk import DOCS_DIR, Chunk, load_chunks

INDEX_PATH = Path(__file__).resolve().parents[2] / "data" / "retrieval.npz"
MINILM = "sentence-transformers/all-MiniLM-L6-v2"


def _normalise(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return (m / np.where(norms == 0, 1.0, norms)).astype(np.float32)


def embed_text(c: Chunk) -> str:
    """What gets embedded: the title and heading give the section its context."""
    return f"{c.title}\n{c.heading}\n{c.text}"


class MiniLMEmbedder:
    name = f"{MINILM} via fastembed (ONNX)"

    def __init__(self) -> None:
        from fastembed import TextEmbedding  # imported here so the tfidf path never needs it
        self._model = TextEmbedding(MINILM)
        # Some snapshots of the ONNX export ship a tokenizer that pads to a fixed 128 but truncates at 256, so any
        # chunk longer than 128 tokens breaks the batch. Pad to the longest sequence in each batch; keep truncation at 256.
        tok = self._model.model.tokenizer
        tok.enable_padding(pad_id=tok.padding["pad_id"], pad_token=tok.padding["pad_token"])

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalise(np.array(list(self._model.embed(texts)), dtype=np.float32))


class TfidfEmbedder:
    """Lexical fallback: log-scaled term frequency times smoothed idf, L2-normalised. Not a neural embedding."""
    name = "tfidf (lexical fallback, not a neural embedding)"

    def __init__(self, vocab: dict[str, int] | None = None, idf: np.ndarray | None = None) -> None:
        self.vocab, self.idf = vocab or {}, idf if idf is not None else np.zeros(0, dtype=np.float32)

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())

    def fit(self, texts: list[str]) -> "TfidfEmbedder":
        df: dict[str, int] = {}
        for t in texts:
            for tok in set(self._tokens(t)):
                df[tok] = df.get(tok, 0) + 1
        self.vocab = {tok: i for i, tok in enumerate(sorted(df))}
        n = len(texts)
        self.idf = np.array([log((1 + n) / (1 + df[tok])) + 1 for tok in sorted(df)], dtype=np.float32)
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        m = np.zeros((len(texts), len(self.vocab)), dtype=np.float32)
        for row, t in enumerate(texts):
            for tok in self._tokens(t):
                if tok in self.vocab:
                    m[row, self.vocab[tok]] += 1
        m[m > 0] = 1 + np.log(m[m > 0])
        return _normalise(m * self.idf)


def get_embedder(backend: str = "auto"):
    """Return the embedder for `backend`; "auto" tries MiniLM and falls back to TF-IDF with a loud warning."""
    if backend == "tfidf":
        return TfidfEmbedder()
    try:
        return MiniLMEmbedder()
    except Exception as e:  # noqa: BLE001 - no network / no cache / missing package
        if backend == "minilm":
            raise
        print(f"[retrieval] WARNING: {MINILM} unavailable ({type(e).__name__}: {e}); "
              "falling back to TF-IDF, which is lexical, not a neural embedding", file=sys.stderr)
        return TfidfEmbedder()


@dataclass
class Index:
    embeddings: np.ndarray  # (n_chunks, dim), rows L2-normalised
    chunks: list[Chunk]
    embedder: MiniLMEmbedder | TfidfEmbedder

    @property
    def backend(self) -> str:
        return self.embedder.name


def build_index(docs_dir: Path | str = DOCS_DIR, out: Path | str = INDEX_PATH, backend: str = "auto") -> Index:
    chunks = load_chunks(docs_dir)
    if not chunks:
        raise FileNotFoundError(f"no markdown documents in {docs_dir}")
    texts = [embed_text(c) for c in chunks]
    embedder = get_embedder(backend)
    if isinstance(embedder, TfidfEmbedder):
        embedder.fit(texts)
    vectors = embedder.embed(texts)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, embeddings=vectors, chunks=json.dumps([c.to_dict() for c in chunks]), backend=embedder.name,
             tfidf_vocab=json.dumps(getattr(embedder, "vocab", {})), tfidf_idf=getattr(embedder, "idf", np.zeros(0)))
    return Index(vectors, chunks, embedder)


def load_index(path: Path | str = INDEX_PATH) -> Index:
    with np.load(Path(path)) as z:
        backend = str(z["backend"])
        chunks = [Chunk(**d) for d in json.loads(str(z["chunks"]))]
        embeddings = z["embeddings"]
        embedder = (TfidfEmbedder(json.loads(str(z["tfidf_vocab"])), z["tfidf_idf"].astype(np.float32))
                    if backend.startswith("tfidf") else MiniLMEmbedder())
    return Index(embeddings, chunks, embedder)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["auto", "minilm", "tfidf"], default="auto")
    args = ap.parse_args()
    idx = build_index(backend=args.backend)
    print(f"indexed {len(idx.chunks)} chunks from {len({c.doc for c in idx.chunks})} documents "
          f"with {idx.backend} -> {INDEX_PATH}")
