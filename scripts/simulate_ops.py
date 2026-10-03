"""Build a month of realistic operations data for the analytics models.

The live database only holds what the demo has actually received, which is too little to report on.
This script writes a separate SQLite file with the same tables the receiver and the agent use: the seeded
customers and orders, about 600 inbound events over 30 days (most forwarded, some retried, some failed or
rejected), and the agent's audited write-backs. It is deterministic, so CI and a laptop build the same data.

    python scripts/simulate_ops.py              # writes data/ops_sample.db
    python scripts/simulate_ops.py --out x.db
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.seed import CUSTOMERS, ORDERS, seed  # noqa: E402

SOURCES = ["shopify", "web-form", "email"]
CONTACT_TEXTS = [
    "Where is my order {order}?",
    "Can I change the delivery address on {order}?",
    "My order {order} arrived damaged, can I get a refund?",
    "Please update my email address on file.",
    "Is there a discount for bulk orders?",
]


def build(out: Path, days: int = 30, per_day: int = 20, rng_seed: int = 7) -> dict:
    rng = random.Random(rng_seed)
    if out.exists():
        out.unlink()
    seed(str(out))  # customers, orders, writeback_log

    conn = sqlite3.connect(out)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS events (
            idem_key TEXT PRIMARY KEY, source TEXT, received_at REAL,
            status TEXT, retries INTEGER, latency_ms REAL, body TEXT)"""
    )
    orders_by_customer: dict[str, list[str]] = {}
    for order_id, customer_id, *_ in ORDERS:
        orders_by_customer.setdefault(customer_id, []).append(order_id)

    # One upstream outage on day 12 so the reports have an incident to find.
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    outage_day = 12
    events = []
    for day in range(days):
        for n in range(per_day + rng.randint(-5, 5)):
            customer_id, _, email, _, _ = rng.choice(CUSTOMERS)
            order = rng.choice(orders_by_customer.get(customer_id, ["O-0000"]))
            source = rng.choice(SOURCES)
            if source == "shopify":
                body = {"event_type": "order.updated", "customer": email, "text": f"Order {order} updated"}
            else:
                body = {"event_type": "contact", "customer": email,
                        "text": rng.choice(CONTACT_TEXTS).format(order=order)}
            at = start + timedelta(days=day, seconds=rng.randint(0, 86_399))

            roll = rng.random()
            if day == outage_day and roll < 0.6:
                status, retries, latency = "failed:ConnectError", 3, rng.uniform(3_500, 4_200)
            elif roll < 0.01:
                status, retries, latency = "failed:ReadTimeout", 3, rng.uniform(15_000, 16_000)
            elif roll < 0.02:
                status, retries, latency = "rejected:422", 0, rng.uniform(20, 80)
            elif roll < 0.10:
                status, retries, latency = "forwarded", rng.randint(1, 2), rng.uniform(600, 2_500)
            else:
                status, retries, latency = "forwarded", 0, rng.uniform(15, 120)
            events.append((f"evt-{day:02d}-{n:03d}", source, at.timestamp(), status, retries,
                           round(latency, 1), json.dumps(body)))
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?)", events)

    # The agent's audited write-backs: only the whitelisted fields, always with a reason.
    writebacks = []
    for i in range(40):
        at = start + timedelta(days=rng.randrange(days), seconds=rng.randint(0, 86_399))
        if rng.random() < 0.7:
            order_id, *_ = rng.choice(ORDERS)
            new = rng.choice(["shipped", "delivered", "refunded"])
            writebacks.append((order_id, "status", "processing", new,
                               f"carrier confirmed {new}" if new != "refunded" else "refund approved by a person",
                               at.strftime("%Y-%m-%d %H:%M:%S")))
        else:
            customer_id, *_ = rng.choice(CUSTOMERS)
            writebacks.append((customer_id, "tier", "standard", "gold", "annual spend passed the gold threshold",
                               at.strftime("%Y-%m-%d %H:%M:%S")))
    conn.executemany(
        "INSERT INTO writeback_log (record_id, field, old_value, new_value, reason, at) VALUES (?,?,?,?,?,?)",
        writebacks,
    )
    conn.commit()
    conn.close()
    return {"events": len(events), "writebacks": len(writebacks)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "data" / "ops_sample.db"))
    args = parser.parse_args()
    counts = build(Path(args.out))
    print(f"wrote {args.out}: {counts['events']} events, {counts['writebacks']} write-backs")
