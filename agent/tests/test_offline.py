"""Offline tests: tool behaviour, schema, and the agent loop with a fake client (no API calls)."""
from __future__ import annotations

import json
import os
import tempfile
from types import SimpleNamespace

import pytest

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from agent import seed, tools  # noqa: E402
from agent import agent as agent_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _seed():
    seed.seed(os.environ["DB_PATH"])


def test_lookup_customer_by_email_returns_orders():
    out = tools.lookup_record("customer", "ava@example.com")
    assert out["customer"]["id"] == "C1001" and len(out["orders"]) == 2


def test_lookup_missing_is_error_not_exception():
    assert "error" in tools.lookup_record("order", "O-9999")


def test_calculate_is_restricted():
    assert tools.calculate("249.00 * 0.15")["value"] == 37.35
    assert "error" in tools.calculate("__import__('os').system('ls')")


def test_write_back_whitelist_and_log():
    assert "error" in tools.write_back("order", "O-5003", "amount", "0", "nope")
    assert "error" in tools.write_back("order", "O-5003", "status", "vanished", "nope")
    ok = tools.write_back("order", "O-5003", "status", "cancelled", "customer asked")
    assert ok["ok"] and ok["old"] == "processing"
    import sqlite3
    log = sqlite3.connect(os.environ["DB_PATH"]).execute("SELECT field, new_value FROM writeback_log").fetchall()
    assert log == [("status", "cancelled")]


def test_tool_schemas_are_strict():
    for t in tools.TOOL_DEFS:
        assert t["strict"] is True and t["input_schema"]["additionalProperties"] is False
        assert set(t["input_schema"]["required"]) == set(t["input_schema"]["properties"])


class _FakeClient:
    """Scripted client: first turn asks for a lookup, second turn returns the final JSON."""

    def __init__(self):
        self.calls = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls += 1
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        if self.calls == 1:
            block = SimpleNamespace(type="tool_use", id="tu_1", name="lookup_record",
                                    input={"record_type": "order", "record_id": "O-5001"})
            return SimpleNamespace(stop_reason="tool_use", content=[block], usage=usage)
        # verify the tool result was fed back
        last = kwargs["messages"][-1]
        assert last["role"] == "user" and last["content"][0]["type"] == "tool_result"
        assert "O-5001" in last["content"][0]["content"]
        final = {"outcome": "resolved", "category": "order_status", "summary": "Delivered.", "actions_taken": [],
                 "recommended_action": "None", "needs_human": False, "amount_aud": None}
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(final))], usage=usage)


def test_agent_loop_feeds_tool_results_back_and_returns_structured_result():
    client = _FakeClient()
    result, trace = agent_mod.run("status of O-5001?", client=client)
    assert result["outcome"] == "resolved" and trace.rounds == 2
    assert trace.tool_calls[0]["name"] == "lookup_record" and trace.tool_calls[0]["error"] is False
