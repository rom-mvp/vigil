import json
import hashlib
import os
from datetime import datetime

class MerkleLogStore:
    """Append-only tamper-evident log using hash chaining (Merkle-ish digest).
    Each record stores: {entry, prev_hash, hash}.
    """
    def __init__(self, path: str = 'logs_append_only.jsonl'):
        self.path = path
        self._last_hash = None
        if os.path.exists(self.path):
            # recover last hash
            try:
                with open(self.path, 'rb') as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    # read tail safely
                    f.seek(max(0, size - 8192), os.SEEK_SET)
                    lines = f.read().splitlines()
                    if lines:
                        last = json.loads(lines[-1].decode('utf-8'))
                        self._last_hash = last.get('hash')
            except Exception:
                self._last_hash = None

    def _digest(self, entry: dict, prev_hash: str | None) -> str:
        m = hashlib.sha256()
        m.update(json.dumps(entry, sort_keys=True).encode('utf-8'))
        if prev_hash:
            m.update(prev_hash.encode('utf-8'))
        return m.hexdigest()

    def append(self, entry: dict) -> dict:
        prev = self._last_hash
        entry_with_meta = {
            "entry": entry,
            "prev_hash": prev,
            "hash": None,
            "ts": datetime.utcnow().isoformat()
        }
        h = self._digest(entry_with_meta["entry"], prev)
        entry_with_meta["hash"] = h
        with open(self.path, 'ab') as f:
            f.write((json.dumps(entry_with_meta) + "\n").encode('utf-8'))
        self._last_hash = h
        return entry_with_meta
