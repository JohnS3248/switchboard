# Switchboard

**An inbox where an AI agent handles incoming requests on its own, within rules a team sets, and hands a person only the cases that need one.**

## The problem it solves

In most operations teams someone reads every incoming request, works out what it is, looks something up, and types the same kind of answer again. Orders, cancellations, address changes, refund questions, alerts from a data feed. The work is repetitive, but nobody wants a machine acting on customer accounts without oversight, and nobody wants a request silently dropped when an automation fails.

Switchboard is my answer to that. Every inbound event is classified, summarised and recorded automatically. Routine requests are answered by an agent that can look records up, do the arithmetic and make a small, whitelisted change, with every change logged. Anything outside the rules, a refund, a complaint, a large amount, an unclear message, goes to a person with a summary attached. When an AI step fails, the row still lands with a flag on it, so a human can act. And the whole thing is measured: per-event latency and error metrics, and a 20-scenario evaluation suite that runs before any change ships.

I built it end to end, alone, in September 2026: the receiver, the pipelines, the agent (twice, by hand and with LangGraph), the evaluation suite, the MCP server, the tests and the runbook.

## What an operations team gets

| Instead of | Switchboard |
|---|---|
| Reading every incoming event to decide what it is | Every event arrives classified, prioritised and summarised, with a suggested action, in a sheet the team already uses |
| Answering the same routine requests by hand | An agent answers them, looking up the record first and calculating every amount, and writes back only the fields it is allowed to |
| Worrying about what an AI might do to a customer account | Read-only by default; three whitelisted fields; a stated reason for every write; a full write-back log; hard rules for when a person must decide |
| Finding out days later that an automation had quietly failed | A failed AI step still produces a row marked `needs_human` with the error text; the receiver retries, records the failure, and keeps the event for replay |
| Watching a dashboard for changes | A scheduled check pulls a public API every 15 minutes and, on a real move, has the model write a two-sentence alert |
| Trusting that a prompt change did not break anything | 20 scenarios assert category, outcome, escalation, which tools ran and which writes happened; both versions of the agent pass 20 of 20 |

## How it stays safe

The operating policy lives in one place and is enforced in code, not just in the prompt:

- **Look up before answering, calculate every amount.** The agent has three tools: `lookup_record` (read-only), `calculate` (restricted arithmetic), `write_back` (three whitelisted fields, reason required, every write logged).
- **Two write-backs without a human, no more.** Refunds, complaints, anything over 1,000 AUD and anything ambiguous escalate with `needs_human=true`.
- **Instructions inside customer text are ignored.** The evaluation suite includes a prompt-injection scenario; the agent refuses to write.
- **Schema-valid output by construction.** The intake prompt demands strict JSON and falls back to `needs_human=true` if the model's answer cannot be parsed; the agent's final answer is enforced with `output_config.format`.
- **Trust boundary at the edge.** A small receiver in front of n8n verifies the HMAC signature, drops duplicates on the idempotency key, retries with backoff and records every event, so the orchestration layer only ever sees clean, signed, deduplicated input.
- **The MCP server is read-only unless someone decides otherwise.** Writes need `MCP_ALLOW_WRITES=1` at start-up, and the whitelist and audit log are the same code the agent uses, so the two entry points cannot drift.

## Results (measured on this machine, 16 Sep 2026)

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
| Agent evals, LangGraph edition | **20/20 passed** on the identical suite · p50 8257.3 ms · p95 13213.6 ms · 87,259 input / 8,527 output tokens · same tools, prompt and schema as the manual loop (`report_langgraph.md`) |
| Offline tests, LangGraph | 2 passed: scripted chat model drives the graph, the real tool runs on a temp database and its result reaches the next model call; the round cap returns `needs_human` |
| MCP server | 2 end-to-end tests passed over stdio: 3 tools listed, lookup and calculate return structured results, an injected expression is refused as data, `write_back` is refused with writes disabled, and with `MCP_ALLOW_WRITES=1` a non-whitelisted field is still refused while a whitelisted write succeeds and appears first in the `writeback-log` resource |
| Versions | n8n 2.39.5 · anthropic SDK 1.6.0 · langgraph 1.2.11 · langchain-anthropic 1.7.2 · Python 3.12 (receiver image) · model `claude-opus-5` |
<!-- EVIDENCE:END -->

## Dropping it into a real team

Switchboard is built so the team, not the developer, owns it after handover:

1. **Point it at the real inbox.** The receiver accepts any signed webhook (an order platform, a form tool, a helpdesk). Replace the CSV sink with Google Sheets and the Slack node with the team's channel; nothing else changes.
2. **Teach it the team's categories.** The classification prompt and the escalation rules are plain text in the intake workflow and the agent's policy. Operators can read them; a developer changes them in one place.
3. **Add a tool when the agent needs to do something new.** Tools are small, typed functions with a whitelist. Add one, add a scenario to the evaluation suite, run the suite.
4. **Measure before and after.** `/metrics` gives events, failures, retries and latency percentiles; the eval report gives pass rate, latency and token cost per run. Baseline first, then compare.
5. **Hand over with the runbook.** `docs/runbook.md` covers daily checks, the failure modes seen so far, backup and restore, rollback and a recovery drill that has actually been run.

## How it is put together

```
 inbound event ──HMAC-signed──▶ receiver (FastAPI) ──▶ n8n · Intake ──▶ Claude (classify / summarise)
                                 │ idempotency key         │                    │
                                 │ retries + backoff        │            needs_human? ──▶ Slack
                                 │ latency / error metrics  └──────────▶ sheet sink (Google Sheets or CSV)
 schedule (15 min) ────────────▶ n8n · Watch ──▶ public API ──▶ anomaly check ──▶ Claude (explain) ──▶ sink + Slack

 customer request ────────────▶ agent/ (Claude tool-use loop: lookup · calculate · write_back) ──▶ structured result + audit log
```

| Piece | What it does | Where |
|---|---|---|
| **Receiver** (FastAPI) | Verifies `X-Signature` (HMAC-SHA256), de-duplicates on `X-Idempotency-Key`, forwards to n8n with bounded retries, records per-event latency / status / retries in SQLite, exposes `/metrics` (JSON or Prometheus text). Also hosts the local sheet sink (`/sink/rows` → CSV) so everything runs end to end without third-party credentials. | `receiver/app.py` |
| **Intake pipeline** (n8n) | Webhook trigger → normalise → Claude classifies and summarises into strict JSON → append to sheet sink → if `needs_human` and Slack is configured, notify. The Claude step retries 3× with backoff; on final failure an error branch still lands the row with `needs_human=true` and the error text. | `n8n/workflows/01_intake_classify_route.json` |
| **Watch pipeline** (n8n) | Schedule trigger every 15 min → pull a public API (AUD FX rates) → compare with the previous run → on a ≥0.5 % move, Claude writes a two-sentence alert → sink + Slack; otherwise a heartbeat row. | `n8n/workflows/02_watch_scheduled_anomaly.json` |
| **Agent** (Claude tool use) | A hand-written agentic loop with the three strict-schema tools and the operating policy above; final answer enforced as JSON. | `agent/agent.py`, `agent/tools.py` |
| **Agent, LangGraph edition** | The same agent as a LangGraph `StateGraph` (agent node ⇄ `ToolNode`) over the same audited functions, policy and schema, so the two orchestrations can be compared on identical evals: `python -m agent.evals.run_evals --impl langgraph`. | `agent/langgraph_agent.py` |
| **Evals** | 20 business scenarios asserting category, outcome, `needs_human`, which tools ran, which writes happened (or did not), and amounts. Re-seeds the database before each scenario. Produces `report.md` / `report.json` with pass rate, p50 / p95 latency and token usage. | `agent/evals/` |
| **MCP server** | The same three tools plus two resources (`switchboard://writeback-log`, `switchboard://policy`) over the Model Context Protocol (stdio), so Claude Code or any MCP client can use them. Read-only unless `MCP_ALLOW_WRITES=1`. `.mcp.json` registers it for Claude Code at project scope. | `mcp_server/server.py`, `.mcp.json` |
| **Retrieval branch** | Policy questions answered from documents, with citations: `docs/policies/` → heading-level chunks → `all-MiniLM-L6-v2` embeddings (ONNX runtime) → cosine top-k → Claude answers from those passages only, or `needs_human`. Labelled QA set with hit@1 / hit@4; optional read-only agent tool `lookup_policy`. | `agent/retrieval/`, `docs/policies/` |
| **Offline tests** | Tool behaviour, whitelist, strict schemas, the manual loop with a fake client, the LangGraph graph with a scripted chat model, and MCP end-to-end tests that spawn the server over stdio as a real client would. No API calls. | `agent/tests/`, `mcp_server/test_mcp.py` |
| **Runbook** | Daily checks, failure modes, backup / restore, rollback, a tested recovery drill. | `docs/runbook.md` |

## Retrieval branch

The agent answers questions about *records* ("what is the status of O-5003") by reading the database. The retrieval branch answers questions about *policy* ("how long is the refund window for a gold customer") by reading documents. `agent/retrieval/` indexes the six sample policy documents in `docs/policies/` (refunds and cancellations, shipping and address changes, escalation rules, data handling and privacy, the agent's own operating policy, and the operations runbook; each is marked as a demo sample at the top), retrieves the passages closest to a question, and has Claude answer from those passages only, citing document and heading, or set `needs_human=true` when the passages do not contain the answer.

- **Chunking:** one chunk per `##` section, with document name, title and heading kept as metadata; 41 chunks from 6 documents, roughly 60–250 tokens each (`chunk.py`).
- **Embedding:** `sentence-transformers/all-MiniLM-L6-v2` (384-d, L2-normalised, cosine similarity), executed through `fastembed` on ONNX runtime. The `sentence-transformers` package itself cannot import on the development machine (its `transformers` dependency pulls in a locally installed `torchvision`, which needs the `lzma` module the local Python build lacks), so the same model is run without torch. If the model cannot be loaded at all, `index.py` falls back to a numpy TF-IDF vectoriser and records that in the index file and the report; the numbers below come from the neural model, not the fallback.
- **Store:** a plain numpy matrix in `data/retrieval.npz` (git-ignored). At 41 chunks a vector database would be more dependency than data.
- **Answer:** `answer(question)` sends the top 4 passages to the same model and client the agent uses, enforces the JSON result with `output_config.format`, and maps the passage numbers the model cites back to (document, heading), so a citation can only point at a passage that was actually retrieved. No citation, or a refusal, routes the question to a person.
- **Agent tool:** `lookup_policy(question)` is registered in `agent/tools.py` as a fourth, read-only tool, but it is not in the agent's default tool list: set `SWITCHBOARD_POLICY_TOOL=1` to add it. The 20-scenario evals were written for three tools and still run on exactly those.

```bash
python -m agent.retrieval.index                                         # chunk + embed docs/policies → data/retrieval.npz (downloads the ~90 MB model once)
python -m agent.retrieval.retrieve "Can I change the address after shipping?"          # top chunks with scores, no API call
python -m agent.retrieval.answer "How long is the refund window for gold customers?"   # cited answer (one API call)
python -m agent.retrieval.eval_retrieval                                # hit@1 / hit@4 over agent/retrieval/qa_set.json, no API calls
python -m agent.retrieval.eval_retrieval --with-answers                 # + one answer() call per question
```

Measured on this machine, 28 Sep 2026 (`agent/retrieval/report_retrieval.md`), over a labelled set of 20 questions (17 answerable, 3 that no document answers):

| What | Result |
|---|---|
| Retrieval alone (no model calls) | **hit@1 0.824 (14/17) · hit@4 1.000 (17/17) · MRR 0.902** |
| `needs_human` routing, all 20 questions | **20/20**: every answerable question answered, all 3 unanswerable ones handed to a person |
| Citation correctness, 17 answerable | **17/17**: every answer cites a passage that contains the answer |
| Expected fact in the answer, 17 answerable | **16/17**: the miss is q01, answered correctly as "30 calendar days" where the checker looks for the literal "30 days" |
| Errors · latency | 0/20 · p50 about 3.0 s per answer |

The three questions not retrieved at rank 1 (q01, q11, q15) still had the right passage in the top 4, so every answer had what it needed. An earlier run on 18 Sep scored hit@1 0.882 with an older cached snapshot of the ONNX export. The snapshot downloaded on 28 Sep pads to a fixed 128 tokens but truncates at 256, which broke batches containing longer chunks, so `index.py` now pads each batch to its longest sequence; the difference in hit@1 most likely comes from that change in the model files. Offline tests: 7 for this branch (chunking, index round-trip, three retrieval questions on both backends, the answer path with a scripted client, the tool's read-only and opt-in contract), 17 in total.

## Running on Azure

The receiver also runs on Azure Container Apps in Australia East, deployed and verified on 28 Sep 2026. The public URL is kept out of this README; everything below is reproducible with the Azure CLI.

| Piece | How it is set up |
|---|---|
| **Compute** | Azure Container Apps (Consumption plan), 0.25 vCPU / 0.5 GiB, **scales to zero** when idle and back up on the first request (a cold start of roughly 20–60 s, the price of paying nothing while idle) |
| **Image** | Azure Container Registry (Standard). The app pulls with its **system-assigned managed identity**, so the registry has no admin user and no password |
| **Secrets** | The webhook signing secret and the Application Insights connection string live in **Key Vault** (RBAC mode). The app reads them through its managed identity with the read-only *Key Vault Secrets User* role; the app configuration holds only Key Vault references |
| **Telemetry** | `receiver/app.py` switches on `azure-monitor-opentelemetry` only when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, so requests, outbound httpx calls and exceptions land in **Application Insights**; nothing changes locally |
| **Second model provider** | Azure OpenAI `gpt-4.1-mini` (GlobalStandard) is the fallback for policy answers: if the Claude call fails, `agent/retrieval/answer.py` sends the same prompt and JSON schema to Azure (`agent/azure_openai.py`). Authentication is **Microsoft Entra ID, no API key**: `az login` locally, a managed identity in Azure |
| **Deploy** | `.github/workflows/deploy-receiver-azure.yml` builds the image, pushes it and rolls out a new revision on every push to `main` that touches `receiver/`, then checks `/healthz`. GitHub signs in with **OpenID Connect** through a federated credential limited to this repository's `main` branch, so no Azure secret is stored in GitHub; the identity can only push to the registry and update this one app and its environment |

Verified against the Azure deployment: `/healthz` 200; a correctly signed webhook accepted (202) and, with no n8n instance deployed in Azure, recorded as a failed forward after 3 retries, exactly as the recovery path is designed; the same idempotency key again returns `duplicate`; a wrong signature returns 401; the Key Vault secret swap was re-verified the same way; requests appear in Application Insights within a few minutes. The retrieval evaluation run with Azure OpenAI answering (`SWITCHBOARD_ANSWER_PROVIDER=azure python -m agent.retrieval.eval_retrieval --with-answers`) scored the same as Claude on the 20-question set: `needs_human` routing 20/20, citation correctness 17/17, expected fact in answer 16/17, 0 errors, p50 about 2.1 s per answer.

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

Use the tools from Claude Code (MCP):

```bash
python3 -m pytest mcp_server/test_mcp.py -q      # end-to-end over stdio
# Claude Code picks up .mcp.json when opened in this directory; check with /mcp
# writes are disabled by default; to allow them: set MCP_ALLOW_WRITES=1 in .mcp.json env
```

## Design notes

- **Why a receiver in front of n8n:** n8n's webhook node accepts anything. Signature verification, idempotency and retry accounting belong at the edge, in code you can test. n8n does the orchestration; the receiver does the trust boundary.
- **Why structured outputs on both sides:** downstream nodes never guess at free text. If the model cannot produce valid JSON, the row is flagged for a person instead of being dropped.
- **Why the agent's writes are whitelisted:** the model can only change three fields, only with a stated reason, and every change is logged. The policy says when a human must decide; the eval suite checks it stays that way, prompt injection included.
- **Why two orchestrations of one agent:** the manual loop keeps the mechanics visible (every request, every tool result, the round cap, the schema-enforced answer). The LangGraph edition proves the same policy, tools and schema survive a framework and gives a place to attach checkpointing, streaming and tracing later. Both are held to the same evaluation suite, so a regression in either shows up as a failed scenario, not an opinion.
- **Why the MCP server is read-only by default:** an MCP client is often an interactive coding agent with a human in the loop, not the audited business agent. Exposing writes to it should be an explicit decision by whoever starts the server.
- **Why an error branch instead of "continue on fail":** a failed LLM step must still produce a row a person can act on. Silent drops are the failure mode that hurts an operations team most.

## Layout

```
receiver/        FastAPI webhook receiver + sink + metrics (Dockerised; Application Insights when configured)
.github/         deploy-receiver-azure.yml: build, push and roll out to Azure Container Apps (OIDC)
n8n/workflows/   the two pipelines as importable JSON (source of truth)
agent/           Claude tool-use agent (manual loop + LangGraph edition), tools, seed data, evals, offline tests;
                 azure_openai.py = Azure OpenAI fallback provider (Entra ID auth)
agent/retrieval/ policy retrieval: chunk → embed (all-MiniLM-L6-v2) → retrieve → cited answer; labelled QA set + hit@k eval
mcp_server/      MCP server over the same tools (stdio) + end-to-end client tests; .mcp.json at the root
scripts/         fire_webhook.py (signed test events)
docs/            runbook and screenshots
docs/policies/   six sample operations policy documents (markdown) that the retrieval branch indexes
data/            SQLite event log + CSV sink + retrieval index (git-ignored)
```
