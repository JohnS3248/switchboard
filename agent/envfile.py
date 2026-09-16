"""Minimal .env loader (no extra dependency): only sets keys that are not already in the environment."""
from __future__ import annotations
import os
from pathlib import Path


def load_dotenv(path: str | os.PathLike | None = None) -> None:
    p = Path(path) if path else Path(__file__).resolve().parents[1] / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
