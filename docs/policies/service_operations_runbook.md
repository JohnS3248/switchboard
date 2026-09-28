# Service operations runbook

> **Part of the Switchboard demo.** This is the operational content of `docs/runbook.md` rewritten as numbered rules so that retrieval can answer questions about how the service is run. `docs/runbook.md` remains the page operators follow.

## 1. Services and health checks

1. n8n (the workflow engine) listens on port 5678. Health: `curl localhost:5678/healthz`. Logs: `docker compose logs n8n`.
2. The receiver (FastAPI: signed webhooks, idempotency, forwarding, sink, metrics) listens on port 8000. Health: `curl localhost:8000/healthz`. Logs: `docker compose logs receiver`.
3. The MCP server is started on demand by the MCP client over stdio (`python3 -m mcp_server.server`); there is nothing to keep running. It logs to stderr, never stdout.
4. Both containers restart automatically (`restart: unless-stopped`); the receiver starts after n8n.

## 2. Daily checks

1. `curl localhost:8000/metrics`: `error_rate` should be 0 and `retries_total` should be flat. Add `?format=prometheus` for scraping.
2. n8n, Executions page: a red run on the Intake workflow means the Claude step failed after 3 retries. The row still lands in the sink with `needs_human=true` and the error text, through the error branch, so nothing is lost.
3. `data/sink.csv` grows with every intake event and every scheduled check; heartbeat rows say `baseline stored` or `no anomaly`.
4. Writes made through the MCP server appear in the `switchboard://writeback-log` resource or the `writeback_log` table in `data/switchboard.db`.

## 3. Failure modes and what to do

| Symptom | Cause | Action |
|---|---|---|
| Receiver returns HTTP 401 | signature mismatch | check `WEBHOOK_SECRET` on both sides; the signature is `sha256=` followed by the HMAC-SHA256 of the raw body |
| Receiver returns `status: duplicate` | the same `X-Idempotency-Key` was seen before | expected; the first delivery already ran, nothing to do |
| Receiver status `failed:*` with `retries=3` | n8n down, or the webhook path inactive | `docker compose ps`; confirm the Intake workflow is active (`n8n list:workflow`); the event stays in the `events` table of `data/switchboard.db` for replay |
| Intake rows with `needs_human=true` and `error` filled | Anthropic API error or timeout after the retries | check `ANTHROPIC_API_KEY` and the API status page; re-fire the event with a new idempotency key |
| Scheduled workflow silent | n8n was not restarted after the workflow was activated | `docker compose restart n8n`; the log must show `Activated workflow "Switchboard · Watch…"` |

## 4. Backup, restore and rollback

1. Workflows: the source of truth is `n8n/workflows/*.json` in git. Restore with `docker exec switchboard-n8n n8n import:workflow --separate --input=/workflows`, then activate and restart n8n.
2. n8n state (credentials, executions) lives in the `./n8n_data/` volume. Back it up with `tar czf n8n_data-$(date +%F).tgz n8n_data`.
3. Receiver state is `data/switchboard.db` (the event log with idempotency keys) and `data/sink.csv`. Copy both; SQLite is safe to copy when the receiver is stopped.
4. Rollback: pin `n8nio/n8n:<version>` in `docker-compose.yml` (this build ran on 2.39.5) and re-import the workflow JSON from git at the wanted commit.

## 5. The watch pipeline schedule

1. The Watch workflow runs every 15 minutes on a schedule trigger.
2. Each run pulls the AUD exchange rates against USD, EUR and GBP from a public API and compares them with the previous run's row.
3. A move of 0.5% or more in any rate counts as an anomaly: Claude writes a two-sentence alert, which goes to the sink and to Slack.
4. When nothing moved, a heartbeat row is written, so a workflow that has gone silent can be noticed at the daily check.

## 6. Recovery drill

1. `docker compose stop n8n`, then fire an event: the receiver reports `failed:...` after 3 retries with backoff, and the event row is persisted.
2. `docker compose start n8n`, then re-fire the event with a new idempotency key: the receiver reports `forwarded`.
3. Run the drill after any change to the receiver's retry or forwarding code, and record the result in the README's evidence table.
