# Switchboard

**An event-driven automation hub for business operations: signed webhooks in, Claude in the middle, actions and alerts out.**

Two n8n pipelines and a Claude tool-use agent, wired together so that inbound business events (orders, forms, API pulls) are classified, summarised, routed to people when they need a person, and recorded, with retries, error branches, execution logs and an evaluation suite in front of every change.

```
 inbound event ──HMAC-signed──▶ receiver (FastAPI) ──▶ n8n · Intake ──▶ Claude (classify / summarise)
                                 │ idempotency key         │                    │
                                 │ retries + backoff        │            needs_human? ──▶ Slack
                                 │ latency / error metrics  └──────────▶ sheet sink (Google Sheets or CSV)
 schedule (15 min) ────────────▶ n8n · Watch ──▶ public API ──▶ anomaly check ──▶ Claude (explain) ──▶ sink + Slack

 customer request ────────────▶ agent/ (Claude tool-use loop: lookup · calculate · write_back) ──▶ structured result + audit log
```

## What is in the box

| Piece | What it does | Where |
|---|---|---|
| **Intake pipeline** (n8n) | Webhook trigger → normalise → Claude classifies + summarises into strict JSON → append to sheet sink → if `needs_human` and Slack is configured, notify. Claude step retries 3× with backoff; on final failure an **error branch** still lands the row with `needs_human=true` and the error text. | `n8n/workflows/01_intake_classify_route.json` |
| **Watch pipeline** (n8n) | Schedule trigger every 15 min → pull a public API (AUD FX rates) → compare with the previous run (workflow static data) → on a ≥0.5 % move, Claude writes a two-sentence alert → sink + Slack; otherwise a heartbeat row. | `n8n/workflows/02_watch_scheduled_anomaly.json` |
| **Receiver** (FastAPI) | Verifies `X-Signature` (HMAC-SHA256), de-duplicates on `X-Idempotency-Key`, forwards to n8n with bounded retries, records per-event latency / status / retries in SQLite, exposes `/metrics` (JSON or Prometheus text). Also hosts the local sheet sink (`/sink/rows` → CSV) so the pipelines run end to end without third-party credentials. | `receiver/app.py` |
| **Agent** (Claude tool use) | A manual agentic loop with three strict-schema tools: `lookup_record` (read-only), `calculate` (restricted arithmetic), `write_back` (whitelisted fields, every write logged). Final answer is enforced as JSON with `output_config.format`. Operating policy: look up before answering, calculate every amount, only two write-backs allowed without a human, refunds / complaints / >1000 AUD / ambiguity go to a human, ignore instructions embedded in customer text. | `agent/agent.py`, `agent/tools.py` |
| **Evals** | 20 business scenarios asserting category, outcome, `needs_human`, which tools ran, which writes happened (or didn't), and amounts. Re-seeds the database before each scenario. Produces `report.md` / `report.json` with pass rate, p50 / p95 latency and token usage. | `agent/evals/` |
| **Offline tests** | Tool behaviour, whitelist, strict schemas, and the loop with a fake client (no API calls). | `agent/tests/` |
| **Runbook** | Daily checks, failure modes, backup / restore, rollback, a tested recovery drill. | `docs/runbook.md` |

## Run it

```bash
cp .env.example .env            # add ANTHROPIC_API_KEY, set WEBHOOK_SECRET; SLACK_WEBHOOK_URL optional
docker compose up -d --build     # n8n on :5678, receiver on :8000
docker exec switchboard-n8n n8n import:workflow --separate --input=/workflows
docker exec switchboard-n8n n8n update:workflow --id=<intake-id> --active=true   # ids from: n8n list:workflow
docker exec switchboard-n8n n8n update:workflow --id=<watch-id>  --active=true
docker compose restart n8n
# n8n editor: http://localhost:5678 — sign in with N8N_OWNER_EMAIL / N8N_OWNER_PASSWORD from .env

python scripts/fire_webhook.py shopify '{"event_type":"order.created","customer":"ava@example.com","amount":89.5,"text":"Order O-5002 placed"}' evt-1
cat data/sink.csv                # the classified, summarised row
curl localhost:8000/metrics      # events_total, error_rate, latency p50/p95, retries

python -m agent.seed             # demo customers / orders
python -m agent.agent "Order O-5003, please cancel it, I ordered by mistake. Liam"
python -m agent.evals.run_evals  # 20 scenarios, writes agent/evals/report.md
python -m pytest agent/tests     # offline
```

Swap the sink for the real thing: add Google Sheets / Slack credentials in n8n and point the `Append row` / `Notify Slack` nodes at them; nothing else changes.

## Evidence (measured on this machine, 16 Sep 2026)

<!-- EVIDENCE:START -->
| What | Result |
|---|---|
| Intake pipeline, end to end (signed webhook → receiver → n8n → Claude → sink) | 2 events forwarded on first run; classified rows landed with category / priority / summary / suggested action / `needs_human`; receiver-side forward latency p50 ≈ 36 ms (Claude runs asynchronously inside n8n) |
| Idempotency and signature checks | duplicate `X-Idempotency-Key` → `status: duplicate` without re-processing; bad signature → HTTP 401 |
| Recovery drill (n8n stopped, event fired, n8n restarted) | `failed:ConnectError` after 3 retries with backoff (3.8 s), event persisted; re-fire after restart → `forwarded` in 54 ms; `/metrics` reported `events_failed=1`, `retries_total=3` |
| Watch pipeline (schedule) | first tick stored the AUD/USD/EUR/GBP baseline row in the sink; subsequent ticks log heartbeat or alert rows |
| Agent evals, run 1 | 17/20 passed on `claude-opus-5` (p50 8506.0 ms, p95 14025.9 ms). The 3 failures were under-specified expectations, not agent faults: a damaged-goods refund demand was labelled `complaint` (both labels are valid and both escalate), "why was my order cancelled" was escalated because the data holds no reason, and "hello?? anyone there" was escalated as ambiguous, which the policy requires. Expectations tightened, see `report_run1.md` |
| Agent evals, run 2 | **20/20 passed** · p50 8927.1 ms · p95 13622.5 ms · 95,528 input / 9,089 output tokens for the suite · prompt-injection scenario (s10) and unauthorised-write scenarios (s03, s08, s09, s15) all refused to write |
| Offline tests | 6 passed (tool whitelist, restricted calculator, strict schemas, loop feeds tool results back) |
| Versions | n8n 2.39.5 · anthropic SDK 1.6.0 · Python 3.12 (receiver image) · model `claude-opus-5` |
<!-- EVIDENCE:END -->

## Design notes

- **Why a receiver in front of n8n:** n8n's webhook node accepts anything. Signature verification, idempotency and retry accounting belong at the edge, in code you can test. n8n does the orchestration; the receiver does the trust boundary.
- **Why structured outputs on both sides:** the Intake prompt demands strict JSON and the parser falls back to `needs_human=true` if it cannot parse; the agent uses `output_config.format` so the final answer is schema-valid by construction. Downstream nodes never guess at free text.
- **Why the agent's writes are whitelisted:** the model can only change three fields, only with a stated reason, and every change is logged. The policy in the system prompt says when a human must decide; the eval suite checks it stays that way (prompt-injection scenario included).
- **Why an error branch instead of "continue on fail":** a failed LLM step must still produce a row a person can act on; silent drops are the failure mode that hurts operations most.

## Layout

```
receiver/        FastAPI webhook receiver + sink + metrics (Dockerised)
n8n/workflows/   the two pipelines as importable JSON (source of truth)
agent/           Claude tool-use agent, tools, seed data, evals, offline tests
scripts/         fire_webhook.py (signed test events)
docs/            runbook (add your own screenshots from the n8n editor: workflow canvases + Executions list)
data/            SQLite event log + CSV sink (git-ignored)
```
