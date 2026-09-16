"""Run the 20 business scenarios against the live agent and assert outcomes.

Usage: python -m agent.evals.run_evals [--only s05,s06]
Writes agent/evals/report.json and agent/evals/report.md. Re-seeds the DB before every scenario so
write-back assertions are deterministic.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from .. import seed as seeder
from ..agent import run
from ..tools import DB_PATH
import sqlite3

HERE = Path(__file__).resolve().parent


def writes_since_seed() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT record_id, field, old_value, new_value FROM writeback_log").fetchall()
    conn.close()
    return [dict(zip(["record_id", "field", "old", "new"], r)) for r in rows]


def check(expect: dict, result: dict, trace, writes: list[dict]) -> list[str]:
    failures = []
    for key in ("category", "outcome", "needs_human"):
        if key in expect and result.get(key) != expect[key]:
            failures.append(f"{key}: expected {expect[key]!r}, got {result.get(key)!r}")
    if "category_in" in expect and result.get("category") not in expect["category_in"]:
        failures.append(f"category: expected one of {expect['category_in']}, got {result.get('category')!r}")
    used = [c["name"] for c in trace.tool_calls]
    for t in expect.get("tools_include", []):
        if t not in used:
            failures.append(f"tool {t} not called (called: {used})")
    if expect.get("no_write") and writes:
        failures.append(f"unexpected write(s): {writes}")
    if "max_writes" in expect and len(writes) > expect["max_writes"]:
        failures.append(f"too many writes: {len(writes)} > {expect['max_writes']}")
    if "write_field" in expect:
        if not any(w["field"] == expect["write_field"] and w["new"] == expect["write_value"] for w in writes):
            failures.append(f"expected write {expect['write_field']}={expect['write_value']!r}, got {writes}")
    if "amount_between" in expect:
        lo, hi = expect["amount_between"]
        amt = result.get("amount_aud")
        if amt is None or not (lo <= float(amt) <= hi):
            failures.append(f"amount_aud {amt} not in [{lo}, {hi}]")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    scenarios = json.loads((HERE / "scenarios.json").read_text())
    if args.only:
        keep = set(args.only.split(","))
        scenarios = [s for s in scenarios if s["id"] in keep]
    rows = []
    for s in scenarios:
        seeder.seed(DB_PATH)
        t0 = time.perf_counter()
        try:
            kwargs = {"model": args.model} if args.model else {}
            result, trace = run(s["request"], **kwargs)
            err = None
        except Exception as e:  # noqa: BLE001
            result, trace, err = {}, None, f"{type(e).__name__}: {e}"
        writes = writes_since_seed()
        failures = [err] if err else check(s["expect"], result, trace, writes)
        row = {"id": s["id"], "passed": not failures, "failures": failures, "result": result,
               "tools": [c["name"] for c in trace.tool_calls] if trace else [],
               "rounds": trace.rounds if trace else 0, "latency_ms": trace.latency_ms if trace else None,
               "input_tokens": trace.input_tokens if trace else 0, "output_tokens": trace.output_tokens if trace else 0,
               "writes": writes}
        rows.append(row)
        print(f"{'PASS' if row['passed'] else 'FAIL'} {s['id']} {row['latency_ms']}ms tools={row['tools']} {failures if failures else ''}")
    passed = sum(r["passed"] for r in rows)
    lat = [r["latency_ms"] for r in rows if r["latency_ms"]]
    summary = {"total": len(rows), "passed": passed, "pass_rate": round(passed / len(rows), 3) if rows else 0,
               "latency_ms_p50": round(statistics.median(lat), 1) if lat else None,
               "latency_ms_p95": round(sorted(lat)[int(0.95 * (len(lat) - 1))], 1) if lat else None,
               "input_tokens": sum(r["input_tokens"] for r in rows), "output_tokens": sum(r["output_tokens"] for r in rows),
               "model": args.model or __import__("agent.agent", fromlist=["MODEL"]).MODEL}
    (HERE / "report.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, default=str))
    md = [f"# Switchboard agent evals\n", f"Model: `{summary['model']}` · {passed}/{len(rows)} passed · p50 {summary['latency_ms_p50']} ms · p95 {summary['latency_ms_p95']} ms · tokens in/out {summary['input_tokens']}/{summary['output_tokens']}\n",
          "| id | pass | tools | rounds | latency ms | failures |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {'✅' if r['passed'] else '❌'} | {' → '.join(r['tools'])} | {r['rounds']} | {r['latency_ms']} | {'; '.join(r['failures'])} |")
    (HERE / "report.md").write_text("\n".join(md) + "\n")
    print(json.dumps(summary, indent=2))
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
