"""Seed the demo business database used by the agent tools."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "switchboard.db"))

CUSTOMERS = [
    ("C1001", "Ava Nguyen", "ava@example.com", "Brand Collective", "gold"),
    ("C1002", "Liam Patel", "liam@example.com", "Daniel's Donuts", "standard"),
    ("C1003", "Mia Rossi", "mia@example.com", "NBL Store", "standard"),
    ("C1004", "Noah Chen", "noah.c@example.com", "Brand Collective", "gold"),
    ("C1005", "Zara Khan", "zara@example.com", "Luxury Property", "vip"),
]
ORDERS = [
    ("O-5001", "C1001", 249.00, "delivered", "2026-09-01"),
    ("O-5002", "C1001", 89.50, "shipped", "2026-09-12"),
    ("O-5003", "C1002", 42.00, "processing", "2026-09-14"),
    ("O-5004", "C1003", 129.99, "delivered", "2026-08-20"),
    ("O-5005", "C1004", 1200.00, "cancelled", "2026-09-10"),
    ("O-5006", "C1005", 15000.00, "processing", "2026-09-15"),
]
REFUND_POLICY = {"gold": 30, "vip": 60, "standard": 14}  # days after delivery


def seed(path: str = DB_PATH) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.executescript(
        """
        DROP TABLE IF EXISTS customers; DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS writeback_log;
        CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT, email TEXT, business TEXT, tier TEXT);
        CREATE TABLE orders (id TEXT PRIMARY KEY, customer_id TEXT, amount REAL, status TEXT, ordered_on TEXT);
        CREATE TABLE writeback_log (id INTEGER PRIMARY KEY AUTOINCREMENT, record_id TEXT, field TEXT, old_value TEXT, new_value TEXT, reason TEXT, at TEXT DEFAULT CURRENT_TIMESTAMP);
        """
    )
    c.executemany("INSERT INTO customers VALUES (?,?,?,?,?)", CUSTOMERS)
    c.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", ORDERS)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed()
    print(f"seeded {DB_PATH}")
