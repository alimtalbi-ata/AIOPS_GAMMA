"""Offline durable receiver model: atomic receipt and synthetic effect in SQLite."""
import hashlib
import json
import sqlite3
from uuid import uuid4

import pytest


def receive(path, tenant, event, payload, *, interrupt=False):
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    conn = sqlite3.connect(path)
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS receipts (tenant TEXT, event TEXT, digest TEXT NOT NULL, PRIMARY KEY(tenant,event))")
            conn.execute("CREATE TABLE IF NOT EXISTS effects (tenant TEXT, event TEXT, PRIMARY KEY(tenant,event))")
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute("SELECT digest FROM receipts WHERE tenant=? AND event=?", (tenant,event)).fetchone()
            if previous:
                return 200 if previous[0] == digest else 409
            conn.execute("INSERT INTO receipts VALUES (?,?,?)", (tenant,event,digest))
            if interrupt:
                raise RuntimeError("synthetic interruption before effect")
            conn.execute("INSERT INTO effects VALUES (?,?)", (tenant,event))
            return 200
    finally:
        conn.close()


def test_receipt_survives_reopen_and_rejects_changed_payload(tmp_path):
    path = tmp_path / "receiver.sqlite"
    tenant, event = str(uuid4()), str(uuid4())
    assert receive(path, tenant, event, {"value": 1}) == 200
    assert receive(path, tenant, event, {"value": 1}) == 200
    assert receive(path, tenant, event, {"value": 2}) == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM effects").fetchone()[0] == 1


def test_interruption_rolls_back_receipt_and_effect(tmp_path):
    path = tmp_path / "receiver.sqlite"
    tenant, event = str(uuid4()), str(uuid4())
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        receive(path, tenant, event, {"value": 1}, interrupt=True)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM receipts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM effects").fetchone()[0] == 0
    assert receive(path, tenant, event, {"value": 1}) == 200
