"""Tool implementations for the Switchboard agent. Each returns a JSON-serialisable dict.

Design rules:
  * lookup is read-only; write_back is the only mutating tool and it logs every change
  * calculate uses a restricted arithmetic evaluator (no eval of arbitrary code)
  * tool errors are returned as data (`{"error": ...}`) so the model can recover
"""
from __future__ import annotations
import ast
import operator as op
import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "switchboard.db"))
ALLOWED_WRITE_FIELDS = {"orders": {"status"}, "customers": {"tier", "email"}}
ALLOWED_STATUS = {"processing", "shipped", "delivered", "cancelled", "refunded"}


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def lookup_record(record_type: str, record_id: str) -> dict:
    """Read one customer or order (with the customer's orders when looking up a customer)."""
    if record_type not in ("customer", "order"):
        return {"error": f"unknown record_type '{record_type}'"}
    with _conn() as conn:
        if record_type == "customer":
            row = conn.execute("SELECT * FROM customers WHERE id=? OR email=?", (record_id, record_id)).fetchone()
            if not row:
                return {"error": f"customer '{record_id}' not found"}
            orders = conn.execute("SELECT * FROM orders WHERE customer_id=? ORDER BY ordered_on DESC", (row["id"],)).fetchall()
            return {"customer": dict(row), "orders": [dict(o) for o in orders]}
        row = conn.execute("SELECT * FROM orders WHERE id=?", (record_id,)).fetchone()
        if not row:
            return {"error": f"order '{record_id}' not found"}
        cust = conn.execute("SELECT * FROM customers WHERE id=?", (row["customer_id"],)).fetchone()
        return {"order": dict(row), "customer": dict(cust) if cust else None}


_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.USub: op.neg, ast.Pow: op.pow}


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("only + - * / ** and numbers are allowed")


def calculate(expression: str) -> dict:
    """Evaluate a plain arithmetic expression, e.g. '249.00 * 0.15'."""
    try:
        value = _safe_eval(ast.parse(expression, mode="eval"))
        return {"expression": expression, "value": round(float(value), 2)}
    except Exception as e:  # noqa: BLE001 - surfaced to the model as data
        return {"error": f"cannot evaluate '{expression}': {e}"}


def write_back(record_type: str, record_id: str, field: str, value: str, reason: str) -> dict:
    """Update one whitelisted field on a record and log the change. Refuses anything outside the whitelist."""
    table = {"customer": "customers", "order": "orders"}.get(record_type)
    if not table:
        return {"error": f"unknown record_type '{record_type}'"}
    if field not in ALLOWED_WRITE_FIELDS[table]:
        return {"error": f"field '{field}' is not writable on {record_type}; allowed: {sorted(ALLOWED_WRITE_FIELDS[table])}"}
    if table == "orders" and field == "status" and value not in ALLOWED_STATUS:
        return {"error": f"invalid status '{value}'; allowed: {sorted(ALLOWED_STATUS)}"}
    with _conn() as conn:
        row = conn.execute(f"SELECT {field} FROM {table} WHERE id=?", (record_id,)).fetchone()
        if not row:
            return {"error": f"{record_type} '{record_id}' not found"}
        old = row[0]
        conn.execute(f"UPDATE {table} SET {field}=? WHERE id=?", (value, record_id))
        conn.execute("INSERT INTO writeback_log (record_id, field, old_value, new_value, reason) VALUES (?,?,?,?,?)",
                     (record_id, field, str(old), str(value), reason))
    return {"ok": True, "record_id": record_id, "field": field, "old": old, "new": value}


TOOL_FUNCS = {"lookup_record": lookup_record, "calculate": calculate, "write_back": write_back}

TOOL_DEFS = [
    {
        "name": "lookup_record",
        "description": "Look up a customer (by id or email) or an order by id. Read-only. Returns the record, and for customers their orders.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "enum": ["customer", "order"]},
                "record_id": {"type": "string", "description": "Customer id like C1001, customer email, or order id like O-5001"},
            },
            "required": ["record_type", "record_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate a plain arithmetic expression (numbers and + - * / ** only). Use it for every refund, discount or total instead of doing arithmetic in your head.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_back",
        "description": "Update one field on a record (orders.status, customers.tier, customers.email). Only call this when the operating policy allows the change without human approval; every write is logged.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "record_type": {"type": "string", "enum": ["customer", "order"]},
                "record_id": {"type": "string"},
                "field": {"type": "string", "enum": ["status", "tier", "email"]},
                "value": {"type": "string"},
                "reason": {"type": "string", "description": "One sentence, will be stored in the audit log"},
            },
            "required": ["record_type", "record_id", "field", "value", "reason"],
            "additionalProperties": False,
        },
    },
]
