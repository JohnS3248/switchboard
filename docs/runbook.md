# Switchboard runbook

## Services
| Service | Port | Health | Logs |
|---|---|---|---|
| n8n (workflow engine) | 5678 | `curl localhost:5678/healthz` | `docker compose logs n8n` |
| receiver (FastAPI: signed webhooks, idempotency, forwarding, sink, metrics) | 8000 | `curl localhost:8000/healthz` | `docker compose logs receiver` |

## Daily checks
- `curl localhost:8000/metrics` → `error_rate` should be 0 and `retries_total` flat. `format=prometheus` for scraping.
- n8n → Executions: any red run on **Intake** means the Claude step failed after 3 retries; the row still lands in the sink with `needs_human=true` and the error text (the error branch), so nothing is lost.
- `data/sink.csv` grows with every intake event and every scheduled check (heartbeat rows say `baseline stored` / `no anomaly`).

## Failure modes and what to do
| Symptom | Cause | Action |
|---|---|---|
| Receiver returns 401 | signature mismatch | check `WEBHOOK_SECRET` on both sides; signature is `sha256=` + HMAC-SHA256 of the raw body |
| Receiver returns `duplicate` | same `X-Idempotency-Key` seen before | expected; the first delivery already ran |
| Receiver status `failed:*` with retries=3 | n8n down or webhook path inactive | `docker compose ps`; confirm the Intake workflow is active (`n8n list:workflow`); events stay in `data/switchboard.db` (`events` table) for replay |
| Intake rows with `needs_human=true` and `error` filled | Anthropic API error / timeout after retries | check `ANTHROPIC_API_KEY`, API status; re-fire the event with a new idempotency key |
| Scheduled workflow silent | n8n not restarted after activation | `docker compose restart n8n`; the log must show `Activated workflow "Switchboard · Watch…"` |

## Backup and restore
- **Workflows**: source of truth is `n8n/workflows/*.json` (version-controlled). Restore: `docker exec switchboard-n8n n8n import:workflow --separate --input=/workflows`, activate, restart n8n.
- **n8n state** (credentials, executions): `./n8n_data/` volume. Back up with `tar czf n8n_data-$(date +%F).tgz n8n_data`.
- **Receiver state**: `data/switchboard.db` (event log with idempotency keys) and `data/sink.csv`. Copy both; SQLite is safe to copy when the receiver is stopped.
- **Rollback**: pin `n8nio/n8n:<version>` in `docker-compose.yml` (this build ran on 2.39.5) and re-import the workflow JSON from git at the wanted commit.

## Recovery drill (tested)
1. `docker compose stop n8n` → fire an event → receiver reports `failed:...` after 3 retries with backoff; event row persisted.
2. `docker compose start n8n` → re-fire with a new idempotency key → `forwarded`.
