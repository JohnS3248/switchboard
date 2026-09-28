"""answer(question) -> {"answer", "citations": [{"doc", "heading"}], "needs_human"}: a policy answer grounded in
the retrieved chunks. Same client, model and output_config.format JSON enforcement as agent/agent.py.

The model cites passages by number; the numbers are mapped back to (doc, heading) here, so a citation can only
ever point at a chunk that was actually retrieved. No citation -> needs_human=true.

CLI: python -m agent.retrieval.answer "How long is the refund window for gold customers?"
"""
from __future__ import annotations

import json

import anthropic

from ..agent import MODEL  # loads .env the same way the agent does
from .retrieve import retrieve

SYSTEM = """You answer operations policy questions for the Switchboard team using ONLY the numbered policy passages provided.
Rules:
1. Answer from the passages alone. Quote the exact numbers, time limits and conditions they state.
2. In `citations` list the numbers of every passage you relied on.
3. If the passages do not contain the answer, say so in one sentence, give no citations and set needs_human=true. Do not guess and do not use outside knowledge.
4. Keep the answer to one to three sentences in plain English."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "integer"}, "description": "Passage numbers used"},
        "needs_human": {"type": "boolean"},
    },
    "required": ["answer", "citations", "needs_human"],
    "additionalProperties": False,
}


def _passages(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{i}] doc: {c['doc']} | heading: {c['heading']}\n{c['text']}" for i, c in enumerate(chunks, 1))


def answer(question: str, k: int = 4, client: anthropic.Anthropic | None = None, model: str = MODEL, index=None) -> dict:
    chunks = retrieve(question, k=k, index=index)
    client = client or anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
        messages=[{"role": "user", "content": f"Passages:\n\n{_passages(chunks)}\n\nQuestion: {question}"}],
    )
    if response.stop_reason == "refusal":
        return {"answer": "Model declined the question.", "citations": [], "needs_human": True}
    raw = json.loads(next((b.text for b in response.content if b.type == "text"), "{}"))
    cited = sorted({n for n in raw.get("citations", []) if 1 <= n <= len(chunks)})
    citations = [{"doc": chunks[n - 1]["doc"], "heading": chunks[n - 1]["heading"]} for n in cited]
    return {"answer": raw.get("answer", ""), "citations": citations,
            "needs_human": bool(raw.get("needs_human", False)) or not citations}


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "How long is the refund window for gold customers?"
    print(json.dumps(answer(q), indent=2))
