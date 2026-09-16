"""Switchboard webhook receiver.

Inbound business events (orders, forms) land here first. The receiver:
  1. verifies an HMAC-SHA256 signature (X-Signature) against WEBHOOK_SECRET
  2. de-duplicates on X-Idempotency-Key (or a body hash) using SQLite
  3. forwards the event to the n8n intake workflow with bounded retries
  4. records latency, status and retry count per event, exposed on /metrics

It also hosts a local "sink" (/sink/rows -> CSV) so the n8n pipelines can be
run end to end without third-party credentials; swap the sink for the Google
Sheets / Slack nodes once credentials are configured.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import sqlite3
import statistics
import time
from contextlib import contextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response

SECRET = os.environ.get("WEBHOOK_SECRET", "change-me").encode()
N8N_URL = os.environ.get("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/switchboard/intake")
DB_PATH = os.environ.get("DB_PATH", "./data/switchboard.db")
SINK_CSV = os.environ.get("SINK_CSV", "./data/sink.csv")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))

app = FastAPI(title="Switchboard receiver", version="0.1.0")


@contextmanager
def db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
            idem_key TEXT PRIMARY KEY, source TEXT, received_at REAL,
            status TEXT, retries INTEGER, latency_ms REAL, body TEXT)"""
    )
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def verify_signature(body: bytes, signature: str | None) -> None:
    if not signature:
        raise HTTPException(status_code=401, detail="missing X-Signature")
    expected = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.removeprefix("sha256=")):
        raise HTTPException(status_code=401, detail="bad signature")


async def forward(source: str, payload: dict[str, Any]) -> tuple[str, int]:
    """Forward to n8n with exponential backoff. Returns (status, retries)."""
    last_error = "unknown"
    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = await client.post(N8N_URL, json={"source": source, **payload})
                if r.status_code < 500:
                    return ("forwarded" if r.status_code < 400 else f"rejected:{r.status_code}", attempt)
                last_error = f"upstream {r.status_code}"
            except httpx.HTTPError as e:
                last_error = type(e).__name__
            if attempt < MAX_RETRIES:
                time.sleep(0.5 * (2**attempt))
    return (f"failed:{last_error}", MAX_RETRIES)


@app.post("/webhooks/{source}", status_code=202)
async def inbound(
    source: str,
    request: Request,
    x_signature: str | None = Header(default=None),
    x_idempotency_key: str | None = Header(default=None),
):
    body = await request.body()
    verify_signature(body, x_signature)
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="body must be JSON")
    idem = x_idempotency_key or hashlib.sha256(body).hexdigest()
    with db() as conn:
        if conn.execute("SELECT 1 FROM events WHERE idem_key=?", (idem,)).fetchone():
            return {"status": "duplicate", "idempotency_key": idem}
        conn.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            (idem, source, time.time(), "received", 0, None, body.decode("utf-8", "replace")),
        )
    t0 = time.perf_counter()
    status, retries = await forward(source, payload)
    latency = (time.perf_counter() - t0) * 1000
    with db() as conn:
        conn.execute(
            "UPDATE events SET status=?, retries=?, latency_ms=? WHERE idem_key=?",
            (status, retries, latency, idem),
        )
    return {"status": status, "retries": retries, "latency_ms": round(latency, 1), "idempotency_key": idem}


@app.post("/sink/rows", status_code=201)
async def sink(request: Request):
    """Local stand-in for a spreadsheet: append one JSON object as a CSV row."""
    row = await request.json()
    os.makedirs(os.path.dirname(SINK_CSV) or ".", exist_ok=True)
    new_file = not os.path.exists(SINK_CSV)
    with open(SINK_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new_file:
            w.writeheader()
        w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row.items()})
    return {"ok": True}


@app.get("/metrics")
def metrics(format: str = "json"):
    with db() as conn:
        rows = conn.execute("SELECT status, retries, latency_ms FROM events").fetchall()
    total = len(rows)
    errors = sum(1 for s, _, _ in rows if s.startswith("failed") or s.startswith("rejected"))
    retries = sum(r or 0 for _, r, _ in rows)
    lat = sorted(l for _, _, l in rows if l is not None)
    p50 = statistics.median(lat) if lat else 0.0
    p95 = lat[int(0.95 * (len(lat) - 1))] if lat else 0.0
    data = {"events_total": total, "events_failed": errors, "retries_total": retries,
            "latency_ms_p50": round(p50, 1), "latency_ms_p95": round(p95, 1),
            "error_rate": round(errors / total, 4) if total else 0.0}
    if format == "prometheus":
        text = "\n".join(f"switchboard_{k} {v}" for k, v in data.items()) + "\n"
        return Response(text, media_type="text/plain; version=0.0.4")
    return data


@app.get("/healthz")
def healthz():
    return {"ok": True}
