#!/usr/bin/env python3
"""Merkle audit chain integrity tests."""

import json

from src.vigil.merkle_log_store import MerkleLogStore


def test_merkle_chain_valid(tmp_path):
    path = tmp_path / "audit_log.jsonl"
    store = MerkleLogStore(path=str(path))

    store.append({"event": "allow", "id": 1})
    store.append({"event": "block", "id": 2})

    result = store.verify_chain()
    assert result["valid"] is True
    assert result["valid_links"] == 2
    assert result["total"] == 2
    assert result["root_hash"]


def test_merkle_chain_tamper_detected(tmp_path):
    path = tmp_path / "audit_log.jsonl"
    store = MerkleLogStore(path=str(path))

    store.append({"event": "allow", "id": 1})
    store.append({"event": "block", "id": 2})

    # Tamper with the second entry's hash on disk
    lines = path.read_text().splitlines()
    tampered = []
    for idx, line in enumerate(lines):
        record = json.loads(line)
        if idx == 1:
            record["hash"] = "deadbeef" + record["hash"][8:]
        tampered.append(json.dumps(record))
    path.write_text("\n".join(tampered) + "\n")

    # Re-open and verify tampering is detected
    store_tampered = MerkleLogStore(path=str(path))
    result = store_tampered.verify_chain()
    assert result["valid"] is False
    assert result["broken_at"] == 1
