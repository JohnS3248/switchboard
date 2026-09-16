"""Send a signed test event through the receiver (HMAC-SHA256 + idempotency key).

Usage: python scripts/fire_webhook.py <source> '<json payload>' [idempotency-key]
"""
import hashlib, hmac, json, sys, time, urllib.request, urllib.error
from pathlib import Path

env = dict(l.split("=", 1) for l in (Path(__file__).resolve().parents[1] / ".env").read_text().splitlines() if "=" in l and not l.startswith("#"))
source = sys.argv[1] if len(sys.argv) > 1 else "web-form"
payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"event_type": "contact", "customer": "ava@example.com", "text": "Where is my order O-5002?"}
idem = sys.argv[3] if len(sys.argv) > 3 else f"evt-{int(time.time())}"
body = json.dumps(payload).encode()
sig = "sha256=" + hmac.new(env["WEBHOOK_SECRET"].encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(f"http://localhost:8000/webhooks/{source}", data=body, method="POST",
                             headers={"Content-Type": "application/json", "X-Signature": sig, "X-Idempotency-Key": idem})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(json.dumps(json.loads(r.read()), indent=2))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:200])
