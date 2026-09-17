"""Offline test for the LangGraph edition: a scripted fake chat model drives the graph, the real tools run
against a temporary copy of the seeded database, and the final message is parsed into the result schema."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def tmp_db(monkeypatch):
    d = tempfile.mkdtemp()
    dst = Path(d) / "switchboard.db"
    src = ROOT / "data" / "switchboard.db"
    if src.exists():
        shutil.copy(src, dst)
    else:
        from agent.seed import seed
        seed(str(dst))
    from agent import tools
    monkeypatch.setattr(tools, "DB_PATH", str(dst))
    return str(dst)


class ScriptedChat(BaseChatModel):
    """Returns pre-scripted AIMessages in order; records what it was asked."""
    script: list
    seen: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):  # the graph calls this; tools are executed by ToolNode, not by us
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(messages)
        msg = self.script.pop(0)
        return ChatResult(generations=[ChatGeneration(message=msg)])


def test_graph_runs_tool_then_returns_structured_result(tmp_db):
    from agent.langgraph_agent import run
    conn = sqlite3.connect(tmp_db)
    cust = conn.execute("SELECT id, email FROM customers LIMIT 1").fetchone()
    conn.close()
    final = {"outcome": "resolved", "category": "order_status", "summary": "Looked up the customer.",
             "actions_taken": ["lookup_record"], "recommended_action": "None", "needs_human": False, "amount_aud": None}
    fake = ScriptedChat(script=[
        AIMessage(content="", tool_calls=[{"name": "lookup_record", "args": {"record_type": "customer", "record_id": cust[1]}, "id": "call_1"}],
                  usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}),
        AIMessage(content=json.dumps(final), usage_metadata={"input_tokens": 20, "output_tokens": 8, "total_tokens": 28}),
    ])
    result, trace = run("where is my order?", chat_model=fake)
    assert result == final
    assert trace.rounds == 2 and trace.tool_calls[0]["name"] == "lookup_record" and trace.tool_calls[0]["error"] is False
    assert trace.input_tokens == 30 and trace.output_tokens == 13
    # the tool really ran: the second model call saw a ToolMessage carrying the customer's id
    second_call = fake.seen[1]
    tool_msgs = [m for m in second_call if isinstance(m, ToolMessage)]
    assert tool_msgs and cust[0] in str(tool_msgs[0].content)


def test_graph_stops_at_round_cap(tmp_db):
    from agent.langgraph_agent import run
    from agent.agent import MAX_ROUNDS
    looping = [AIMessage(content="", tool_calls=[{"name": "calculate", "args": {"expression": "1+1"}, "id": f"c{i}"}])
               for i in range(MAX_ROUNDS + 2)]
    result, trace = run("loop forever", chat_model=ScriptedChat(script=looping))
    assert result["needs_human"] is True and "round cap" in result["summary"]
    assert trace.rounds == MAX_ROUNDS
