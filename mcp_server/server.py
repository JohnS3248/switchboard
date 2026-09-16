"""Switchboard MCP server.

Exposes the same three tools the in-repo Claude agent uses (`agent/tools.py`) over the Model Context
Protocol, so an MCP client such as Claude Code can look up records, do arithmetic and (when explicitly
allowed) write back to a whitelisted field.

Security posture (deliberate):
  * read-only by default: `write_back` refuses unless MCP_ALLOW_WRITES=1 is set in the server's environment
  * the write whitelist and audit log live in agent/tools.py and are enforced there, not here
  * every tool call is logged to stderr (stdout is the MCP stdio transport and must stay clean)
  * tool errors are returned as data, never raised, so the client model can recover

Run:  python3 -m mcp_server.server            (stdio transport, from the repo root)
Test: python3 -m pytest mcp_server/test_mcp.py -q
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys

from mcp.server.fastmcp import FastMCP

from agent import tools as t

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[switchboard-mcp] %(message)s")
log = logging.getLogger("switchboard-mcp")

ALLOW_WRITES = os.environ.get("MCP_ALLOW_WRITES", "0") == "1"

mcp = FastMCP(
    "switchboard",
    instructions=(
        "Tools over Switchboard's customer and order records. lookup_record is read-only. "
        "calculate must be used for every refund, discount or total. write_back only changes whitelisted "
        "fields, is audited, and is disabled unless the server was started with MCP_ALLOW_WRITES=1."
    ),
)


@mcp.tool()
def lookup_record(record_type: str, record_id: str) -> dict:
    """Look up a customer (by id like C1001, or email) or an order (by id like O-5001). Read-only.
    For a customer, also returns their orders."""
    log.info("lookup_record %s %s", record_type, record_id)
    return t.lookup_record(record_type, record_id)


@mcp.tool()
def calculate(expression: str) -> dict:
    """Evaluate a plain arithmetic expression (numbers and + - * / ** only), e.g. '249.00 * 0.15'."""
    log.info("calculate %s", expression)
    return t.calculate(expression)


@mcp.tool()
def write_back(record_type: str, record_id: str, field: str, value: str, reason: str) -> dict:
    """Update ONE whitelisted field (orders.status, customers.tier, customers.email) and log the change.
    Refused unless the server runs with MCP_ALLOW_WRITES=1. `reason` is stored in the audit log."""
    log.info("write_back %s %s %s=%s (%s)", record_type, record_id, field, value, reason)
    if not ALLOW_WRITES:
        return {"error": "writes are disabled on this MCP server; start it with MCP_ALLOW_WRITES=1 to enable"}
    return t.write_back(record_type, record_id, field, value, reason)


@mcp.resource("switchboard://writeback-log")
def writeback_log() -> str:
    """The audit log of every write made through the tools, newest first (JSON)."""
    conn = sqlite3.connect(t.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM writeback_log ORDER BY rowid DESC LIMIT 50").fetchall()
    conn.close()
    return json.dumps([dict(r) for r in rows], indent=2)


@mcp.resource("switchboard://policy")
def policy() -> str:
    """The operating policy the in-repo agent follows (system prompt), for clients that want the same rules."""
    from agent.agent import SYSTEM
    return SYSTEM


if __name__ == "__main__":
    log.info("starting (writes %s)", "ENABLED" if ALLOW_WRITES else "disabled")
    mcp.run()
