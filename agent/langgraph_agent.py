"""Switchboard agent, LangGraph edition.

Same operating policy (SYSTEM), same three tools (agent/tools.py), same result schema and the same
20-scenario evaluation suite as the hand-written loop in agent/agent.py. The only thing that changes is the
orchestration: a LangGraph StateGraph (agent node ⇄ tool node) instead of a manual while-loop.

Why both exist: the manual loop shows the mechanics with no framework in the way; this version shows the same
agent expressed in LangGraph so it can plug into LangChain tooling (checkpointers, streaming, LangSmith).
Run the evals against either with `python -m agent.evals.run_evals --impl langgraph`.
"""
from __future__ import annotations

import json
import time
from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from . import tools as t
from .agent import MAX_ROUNDS, MODEL, RESULT_SCHEMA, SYSTEM, Trace


# ---- tools: thin LangChain wrappers over the audited implementations in agent/tools.py ----

@tool
def lookup_record(record_type: str, record_id: str) -> dict:
    """Look up a customer (by id like C1001, or email) or an order by id like O-5001. Read-only.
    record_type must be 'customer' or 'order'. For a customer, also returns their orders."""
    return t.lookup_record(record_type, record_id)


@tool
def calculate(expression: str) -> dict:
    """Evaluate a plain arithmetic expression (numbers and + - * / ** only), e.g. '249.00 * 0.15'.
    Use it for every refund, discount or total instead of doing arithmetic in your head."""
    return t.calculate(expression)


@tool
def write_back(record_type: str, record_id: str, field: str, value: str, reason: str) -> dict:
    """Update one field on a record (orders.status, customers.tier, customers.email). Only call this when the
    operating policy allows the change without human approval; every write is logged with `reason`."""
    return t.write_back(record_type, record_id, field, value, reason)


TOOLS = [lookup_record, calculate, write_back]


# ---- graph ----

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    rounds: int


def _default_model(model: str):
    from langchain_anthropic import ChatAnthropic
    # Ask the API for a schema-valid final answer, same as the manual loop's output_config.
    return ChatAnthropic(model=model, max_tokens=4096,
                         output_config={"format": {"type": "json_schema", "schema": RESULT_SCHEMA}})


def build_graph(chat_model: Any):
    """Build the agent graph around any LangChain chat model that supports bind_tools."""
    llm = chat_model.bind_tools(TOOLS)

    def agent_node(state: AgentState) -> dict:
        response = llm.invoke([SystemMessage(content=SYSTEM)] + state["messages"])
        return {"messages": [response], "rounds": state.get("rounds", 0) + 1}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls and state["rounds"] < MAX_ROUNDS:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def _text(msg: AIMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return "".join(b.get("text", "") for b in msg.content if isinstance(b, dict) and b.get("type") == "text")


def _trace_from(messages: list, latency_ms: float) -> Trace:
    trace = Trace(latency_ms=latency_ms)
    results_by_id = {m.tool_call_id: m for m in messages if isinstance(m, ToolMessage)}
    for m in messages:
        if isinstance(m, AIMessage):
            trace.rounds += 1
            usage = getattr(m, "usage_metadata", None) or {}
            trace.input_tokens += usage.get("input_tokens", 0)
            trace.output_tokens += usage.get("output_tokens", 0)
            trace.stop_reason = "tool_use" if m.tool_calls else "end_turn"
            for call in m.tool_calls:
                res = results_by_id.get(call["id"])
                content = res.content if res is not None else ""
                is_error = bool(res is not None and (res.status == "error" or '"error"' in str(content)))
                trace.tool_calls.append({"name": call["name"], "args": call["args"], "error": is_error, "ms": None})
    return trace


def run(request: str, chat_model: Any | None = None, model: str = MODEL) -> tuple[dict, Trace]:
    """Run the LangGraph agent on one request. Returns (structured_result, trace), same contract as agent.run."""
    app = build_graph(chat_model or _default_model(model))
    t0 = time.perf_counter()
    final = app.invoke({"messages": [HumanMessage(content=request)], "rounds": 0})
    latency = round((time.perf_counter() - t0) * 1000, 1)
    messages = final["messages"]
    trace = _trace_from(messages, latency)
    last = messages[-1]
    if not isinstance(last, AIMessage) or last.tool_calls:
        return ({"outcome": "needs_human", "category": "other", "summary": "Agent hit the tool-round cap without finishing.",
                 "actions_taken": [c["name"] for c in trace.tool_calls], "recommended_action": "Review manually",
                 "needs_human": True, "amount_aud": None}, trace)
    try:
        return (json.loads(_text(last)), trace)
    except json.JSONDecodeError:
        return ({"outcome": "needs_human", "category": "other", "summary": "Model did not return a valid structured result.",
                 "actions_taken": [c["name"] for c in trace.tool_calls], "recommended_action": "Review manually",
                 "needs_human": True, "amount_aud": None}, trace)


if __name__ == "__main__":
    import sys
    req = " ".join(sys.argv[1:]) or "Hi, I'm ava@example.com, what's the status of my latest order?"
    result, trace = run(req)
    print(json.dumps(result, indent=2))
    print(json.dumps(trace.__dict__, indent=2, default=str))
