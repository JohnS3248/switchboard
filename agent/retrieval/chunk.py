"""Split markdown policy documents into heading-level chunks that carry their document name and heading.

A chunk is one `##`/`###` section (the `#` line is the document title and is attached as metadata, not
split on). Sections longer than MAX_TOKENS are split at paragraph boundaries; the pieces keep the same
heading and get a `part` number. Token counts are approximate (about four characters per token).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parents[2] / "docs" / "policies"
MAX_TOKENS = 400

_HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")


@dataclass
class Chunk:
    doc: str      # file stem, e.g. "refunds_and_cancellations"
    title: str    # the document's `#` title
    heading: str  # the section heading; the title itself for text before the first section
    text: str
    part: int = 0  # > 0 when a long section was split into several chunks

    def to_dict(self) -> dict:
        return asdict(self)


def approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _split_long(body: str) -> list[str]:
    if approx_tokens(body) <= MAX_TOKENS:
        return [body]
    pieces, current = [], ""
    for para in re.split(r"\n\s*\n", body):
        candidate = f"{current}\n\n{para}".strip() if current else para
        if current and approx_tokens(candidate) > MAX_TOKENS:
            pieces.append(current)
            current = para
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(text: str, doc: str) -> list[Chunk]:
    """Chunk one markdown document. `doc` is the name recorded in every chunk's metadata."""
    title, heading, buf, chunks = doc, None, [], []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            for i, piece in enumerate(_split_long(body)):
                chunks.append(Chunk(doc=doc, title=title, heading=heading or title, text=piece, part=i))
        buf.clear()

    for line in text.splitlines():
        m = _HEADING.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2)
        elif m:
            flush()
            heading = m.group(2)
        else:
            buf.append(line)
    flush()
    return chunks


def load_chunks(docs_dir: Path | str = DOCS_DIR) -> list[Chunk]:
    """Chunk every *.md file in `docs_dir`, in name order."""
    chunks: list[Chunk] = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), doc=path.stem))
    return chunks


if __name__ == "__main__":
    for c in load_chunks():
        print(f"{c.doc:32s} {c.heading:48s} part={c.part} ~{approx_tokens(c.text)} tokens")
