"""End-to-end test: spawn the MCP server over stdio as a real client would, list tools, call each one.
Uses a temporary copy of the seeded database so nothing in data/ is touched."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
SEED_DB = ROOT / "data" / "switchboard.db"


def _payload(result) -> dict:
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


async def _session(env: dict, fn):
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], env={**os.environ, **env}, cwd=str(ROOT))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def _tmp_db() -> str:
    d = tempfile.mkdtemp()
    dst = Path(d) / "switchboard.db"
    if SEED_DB.exists():
        shutil.copy(SEED_DB, dst)
    else:
        os.environ["DB_PATH"] = str(dst)
        from agent.seed import seed
        seed(str(dst))
    return str(dst)


def _first_ids(db: str):
    conn = sqlite3.connect(db)
    cust = conn.execute("SELECT id FROM customers LIMIT 1").fetchone()[0]
    order = conn.execute("SELECT id, status FROM orders LIMIT 1").fetchone()
    conn.close()
    return cust, order[0], order[1]


def test_tools_listed_and_readonly_by_default():
    db = _tmp_db()
    cust, order, _ = _first_ids(db)

    async def run(session):
        tools = await session.list_tools()
        names = sorted(tl.name for tl in tools.tools)
        assert names == ["calculate", "lookup_record", "write_back"], names
        r = _payload(await session.call_tool("lookup_record", {"record_type": "customer", "record_id": cust}))
        assert r["customer"]["id"] == cust and "orders" in r
        r = _payload(await session.call_tool("calculate", {"expression": "249.00 * 0.15"}))
        assert r["value"] == 37.35
        r = _payload(await session.call_tool("calculate", {"expression": "__import__('os')"}))
        assert "error" in r
        r = _payload(await session.call_tool("write_back", {"record_type": "order", "record_id": order, "field": "status", "value": "shipped", "reason": "test"}))
        assert "disabled" in r["error"]
        res = await session.list_resources()
        uris = sorted(str(x.uri) for x in res.resources)
        assert "switchboard://writeback-log" in uris and "switchboard://policy" in uris
        return True

    assert asyncio.run(_session({"DB_PATH": db, "MCP_ALLOW_WRITES": "0"}, run))


def test_writes_when_enabled_are_whitelisted_and_audited():
    db = _tmp_db()
    _, order, old_status = _first_ids(db)

    async def run(session):
        r = _payload(await session.call_tool("write_back", {"record_type": "order", "record_id": order, "field": "total", "value": "0", "reason": "nope"}))
        assert "not writable" in r["error"]
        r = _payload(await session.call_tool("write_back", {"record_type": "order", "record_id": order, "field": "status", "value": "shipped", "reason": "mcp test"}))
        assert r.get("ok") is True and r["old"] == old_status
        logtxt = await session.read_resource("switchboard://writeback-log")
        entries = json.loads(logtxt.contents[0].text)
        assert entries[0]["record_id"] == order and entries[0]["reason"] == "mcp test"
        return True

    assert asyncio.run(_session({"DB_PATH": db, "MCP_ALLOW_WRITES": "1"}, run))
