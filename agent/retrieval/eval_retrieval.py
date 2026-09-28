"""Measure the retrieval branch on the labelled QA set and write report_retrieval.md.

  python -m agent.retrieval.eval_retrieval                 # hit@1 / hit@4 only, no API calls
  python -m agent.retrieval.eval_retrieval --with-answers  # also runs answer() per question (API calls)

hit@k: at least one of a question's expected (doc, heading) chunks is in the top k. Computed over the
answerable questions only. With --with-answers, the report adds needs_human accuracy over all questions,
citation correctness (an expected chunk is among the citations) and whether an expected answer fragment
appears in the answer, over the answerable questions.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import date
from pathlib import Path

from .index import INDEX_PATH, build_index
from .retrieve import get_index, retrieve

HERE = Path(__file__).resolve().parent


def _rank(hits: list[dict], expected: list[dict]) -> int | None:
    want = {(e["doc"], e["heading"]) for e in expected}
    for i, h in enumerate(hits, 1):
        if (h["doc"], h["heading"]) in want:
            return i
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--with-answers", action="store_true", help="also call answer() for every question (API calls)")
    ap.add_argument("--rebuild", action="store_true", help="rebuild data/retrieval.npz first")
    args = ap.parse_args()
    if args.rebuild or not INDEX_PATH.exists():
        build_index()
    index = get_index()
    qa = json.loads((HERE / "qa_set.json").read_text(encoding="utf-8"))
    answerable = [q for q in qa if q["expected"]]

    rows = []
    for q in answerable:
        hits = retrieve(q["question"], k=args.k, index=index)
        rank = _rank(hits, q["expected"])
        rows.append({"id": q["id"], "rank": rank, "top1": f"{hits[0]['doc']} › {hits[0]['heading']}", "score": hits[0]["score"]})
        print(f"{'hit' if rank else 'MISS':4s} {q['id']} rank={rank} top1={rows[-1]['top1']} ({hits[0]['score']:.3f})")
    hit1 = sum(r["rank"] == 1 for r in rows) / len(rows)
    hitk = sum(r["rank"] is not None for r in rows) / len(rows)
    mrr = sum(1 / r["rank"] for r in rows if r["rank"]) / len(rows)
    print(f"\nhit@1 {hit1:.3f}  hit@{args.k} {hitk:.3f}  MRR {mrr:.3f}  ({len(rows)} answerable questions, "
          f"{len(index.chunks)} chunks, {index.backend})")

    md = [f"# Retrieval evaluation\n",
          f"Run on {date.today().isoformat()} · embedding: `{index.backend}` · {len(index.chunks)} chunks from "
          f"{len({c.doc for c in index.chunks})} documents in `docs/policies/` · k = {args.k} · "
          f"{len(qa)} questions ({len(answerable)} answerable, {len(qa) - len(answerable)} expected `needs_human`)\n",
          "## Retrieval (no model calls)\n",
          f"| hit@1 | hit@{args.k} | MRR |", "|---|---|---|",
          f"| **{hit1:.3f}** ({sum(r['rank'] == 1 for r in rows)}/{len(rows)}) | **{hitk:.3f}** "
          f"({sum(r['rank'] is not None for r in rows)}/{len(rows)}) | {mrr:.3f} |\n",
          "| id | rank of expected chunk | top-1 chunk | top-1 score |", "|---|---|---|---|"]
    md += [f"| {r['id']} | {r['rank'] if r['rank'] else 'miss'} | {r['top1']} | {r['score']:.3f} |" for r in rows]

    if args.with_answers:
        from .answer import answer
        arows, t_all = [], time.perf_counter()
        for q in qa:
            t0 = time.perf_counter()
            try:
                res, err = answer(q["question"], k=args.k, index=index), None
            except Exception as e:  # noqa: BLE001 - keep going, record the failure
                res, err = {"answer": "", "citations": [], "needs_human": None}, f"{type(e).__name__}: {e}"
            ms = round((time.perf_counter() - t0) * 1000)
            want = {(e["doc"], e["heading"]) for e in q["expected"]}
            cited = {(c["doc"], c["heading"]) for c in res["citations"]}
            row = {"id": q["id"], "needs_human_ok": res["needs_human"] == q["needs_human"] and not err,
                   "citation_ok": bool(want & cited) if q["expected"] else None,
                   "fragment_ok": any(f.lower() in res["answer"].lower() for f in q["answer_fragments"]) if q["expected"] else None,
                   "needs_human": res["needs_human"], "citations": [f"{c['doc']} › {c['heading']}" for c in res["citations"]],
                   "answer": res["answer"], "ms": ms, "error": err}
            arows.append(row)
            print(f"{q['id']} needs_human={row['needs_human']} ok={row['needs_human_ok']} cite={row['citation_ok']} "
                  f"frag={row['fragment_ok']} {ms}ms {err or ''}")
        ok_rows = [r for r in arows if not r["error"]]
        n_ans = [r for r in ok_rows if r["citation_ok"] is not None]
        errors = [r["error"] for r in arows if r["error"]]
        lat = [r["ms"] for r in ok_rows]

        def score(rows: list[dict], key: str) -> str:  # "0.950 (19/20)" over the calls that succeeded, or "not measured"
            return f"**{sum(r[key] for r in rows) / len(rows):.3f}** ({sum(r[key] for r in rows)}/{len(rows)})" if rows else "not measured"

        nh, cite, frag = score(ok_rows, "needs_human_ok"), score(n_ans, "citation_ok"), score(n_ans, "fragment_ok")
        print(f"\nneeds_human accuracy {nh}  citation correctness {cite}  fragment match {frag}  "
              f"errors {len(errors)}/{len(arows)}  p50 {statistics.median(lat) if lat else None} ms  total {round(time.perf_counter() - t_all)} s")
        md += ["\n## Answers (one `answer()` call per question, model from `agent.agent.MODEL`)\n",
               "Scores are over the calls that succeeded; a question whose call errored is counted in the errors column, not as a wrong answer.\n",
               "| needs_human accuracy (all questions) | citation correctness (answerable) | expected fragment in answer (answerable) | errors | latency p50 |",
               "|---|---|---|---|---|",
               f"| {nh} | {cite} | {frag} | {len(errors)}/{len(arows)} | {statistics.median(lat) if lat else None} ms |\n"]
        if errors:
            md.append(f"**{len(errors)} of {len(arows)} calls failed**, so the answer-side numbers above are "
                      f"{'not measured' if not ok_rows else 'measured on ' + str(len(ok_rows)) + ' questions only'}. "
                      "Distinct errors: " + "; ".join(f"`{e}`" for e in sorted(set(errors))) + "\n")
        md += ["| id | needs_human (expected) | citations | fragment | answer |", "|---|---|---|---|---|"]
        for q, r in zip(qa, arows):
            if r["error"]:
                md.append(f"| {r['id']} | error | | | `{r['error'].replace('|', '/')}` |")
                continue
            ans = r["answer"].replace("|", "\\|").replace("\n", " ")
            md.append(f"| {r['id']} | {r['needs_human']} ({q['needs_human']}) {'✅' if r['needs_human_ok'] else '❌'} | "
                      f"{'; '.join(r['citations'])} {'' if r['citation_ok'] is None else ('✅' if r['citation_ok'] else '❌')} | "
                      f"{'' if r['fragment_ok'] is None else ('✅' if r['fragment_ok'] else '❌')} | {ans} |")
    else:
        md += ["\n## Answers\n", "Not run in this invocation (`--with-answers` not passed)."]
    (HERE / "report_retrieval.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"wrote {HERE / 'report_retrieval.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
