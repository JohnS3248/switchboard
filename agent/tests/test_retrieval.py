"""Offline tests for the retrieval branch: chunking, index build, retrieval on the sample docs, the answer path
with a fake client, and the read-only lookup_policy tool. No API calls; no network (HF_HUB_OFFLINE)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # use the cached MiniLM model if present, never download in tests

from agent.retrieval import chunk as chunk_mod  # noqa: E402
from agent.retrieval import retrieve as retrieve_mod  # noqa: E402
from agent.retrieval.index import MiniLMEmbedder, build_index, load_index  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = [  # three questions with an unambiguous chunk
    ("How many days after delivery can a gold customer ask for a refund?", "refunds_and_cancellations", "1. Refund eligibility windows"),
    ("After how many business days is a parcel treated as lost?", "shipping_and_address_changes", "3. Lost or delayed parcels"),
    ("How often does the watch pipeline run?", "service_operations_runbook", "5. The watch pipeline schedule"),
]


def test_chunking_keeps_doc_and_heading_metadata():
    chunks = chunk_mod.chunk_markdown((ROOT / "docs/policies/refunds_and_cancellations.md").read_text(), doc="refunds_and_cancellations")
    headings = [c.heading for c in chunks]
    assert "1. Refund eligibility windows" in headings and "4. Cancelling an order" in headings
    assert all(c.doc == "refunds_and_cancellations" and c.title == "Refunds and cancellations policy" and c.text for c in chunks)
    assert all(chunk_mod.approx_tokens(c.text) <= chunk_mod.MAX_TOKENS for c in chunks)
    assert "30 days" in next(c.text for c in chunks if c.heading == "1. Refund eligibility windows")


def test_long_sections_are_split_but_keep_their_heading():
    body = "\n\n".join(f"Paragraph {i}. " + "word " * 120 for i in range(6))
    chunks = chunk_mod.chunk_markdown(f"# T\n\n## Long section\n\n{body}\n", doc="d")
    assert len(chunks) > 1 and {c.heading for c in chunks} == {"Long section"} and [c.part for c in chunks] == list(range(len(chunks)))


@pytest.fixture(scope="module")
def tfidf_index():
    out = Path(tempfile.mkdtemp()) / "retrieval.npz"
    build_index(out=out, backend="tfidf")
    return load_index(out)  # round-trips through the file, as the CLI does


def test_index_round_trip_and_retrieval_tfidf(tfidf_index):
    assert tfidf_index.backend.startswith("tfidf") and len(tfidf_index.chunks) >= 30
    assert tfidf_index.embeddings.shape[0] == len(tfidf_index.chunks)
    for question, doc, heading in QUESTIONS:
        hits = retrieve_mod.retrieve(question, k=4, index=tfidf_index)
        assert (doc, heading) in {(h["doc"], h["heading"]) for h in hits}, (question, [(h["doc"], h["heading"]) for h in hits])
        assert hits[0]["score"] >= hits[-1]["score"]


def test_retrieval_with_cached_minilm_model():
    try:
        embedder = MiniLMEmbedder()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"MiniLM not available offline: {type(e).__name__}")
    out = Path(tempfile.mkdtemp()) / "retrieval.npz"
    index = build_index(out=out, backend="minilm")
    assert index.embeddings.shape[1] == 384 and abs(float((index.embeddings[0] ** 2).sum()) - 1) < 1e-4
    for question, doc, heading in QUESTIONS:
        hits = retrieve_mod.retrieve(question, k=4, index=index)
        assert (doc, heading) in {(h["doc"], h["heading"]) for h in hits}, (question, [(h["doc"], h["heading"]) for h in hits])
    del embedder


class _FakeClient:
    """Returns a scripted structured answer; records the prompt it was given."""

    def __init__(self, payload: dict, stop_reason: str = "end_turn"):
        self.payload, self.stop_reason, self.seen = payload, stop_reason, None
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.seen = kwargs
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=json.dumps(self.payload))])


def test_answer_maps_passage_numbers_to_citations(tfidf_index):
    from agent.retrieval.answer import answer
    client = _FakeClient({"answer": "Gold customers have 30 days after delivery.", "citations": [1, 99], "needs_human": False})
    res = answer(QUESTIONS[0][0], client=client, index=tfidf_index)
    assert res["needs_human"] is False and len(res["citations"]) == 1  # 99 is out of range and dropped
    assert set(res["citations"][0]) == {"doc", "heading"}
    assert "[1] doc:" in client.seen["messages"][0]["content"] and client.seen["output_config"]["format"]["type"] == "json_schema"


def test_answer_needs_human_when_nothing_is_cited(tfidf_index):
    from agent.retrieval.answer import answer
    client = _FakeClient({"answer": "The passages do not cover gift wrapping.", "citations": [], "needs_human": True})
    res = answer("Do we offer gift wrapping?", client=client, index=tfidf_index)
    assert res == {"answer": "The passages do not cover gift wrapping.", "citations": [], "needs_human": True}
    # a model that claims confidence but cites nothing is still routed to a person
    client = _FakeClient({"answer": "Yes, 5 AUD.", "citations": [], "needs_human": False})
    assert answer("Do we offer gift wrapping?", client=client, index=tfidf_index)["needs_human"] is True
    # a refusal is routed to a person too
    assert answer("x", client=_FakeClient({}, stop_reason="refusal"), index=tfidf_index)["needs_human"] is True


def test_lookup_policy_tool_is_read_only_and_opt_in(tfidf_index, monkeypatch):
    from agent import tools
    monkeypatch.setattr(retrieve_mod, "_INDEX", tfidf_index)
    out = tools.lookup_policy(QUESTIONS[0][0])
    assert "error" not in out and out["passages"] and {"doc", "heading", "text", "score"} <= set(out["passages"][0])
    assert "lookup_policy" in tools.TOOL_FUNCS and tools.POLICY_TOOL_DEF["strict"] is True
    assert [t["name"] for t in tools.TOOL_DEFS] == ["lookup_record", "calculate", "write_back"]  # default list unchanged
