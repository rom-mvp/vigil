import json
import hashlib
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import psycopg2
    from psycopg2.extras import Json
    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False

class MerkleLogStore:
    """Append-only tamper-evident log using hash chaining.
    Supports both local file storage and PostgreSQL.
    """
    def __init__(self, path: str = 'logs_append_only.jsonl'):
        self.path = path
        self.db_url = os.environ.get('DATABASE_URL')
        self._last_hash = None
        self._use_db = False
        
        if self.db_url and _PG_AVAILABLE:
            try:
                self._init_db()
                self._use_db = True
                print("MerkleLogStore: Using PostgreSQL backend")
            except Exception as e:
                print(f"MerkleLogStore: Database initialization failed, falling back to file. Error: {e}")
                self._init_file()
        else:
            self._init_file()

    def _init_file(self):
        """Initialize file-based storage."""
        if os.path.exists(self.path):
            try:
                with open(self.path, 'rb') as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    # read tail safely to find last hash
                    f.seek(max(0, size - 8192), os.SEEK_SET)
                    lines = f.read().splitlines()
                    if lines:
                        last = json.loads(lines[-1].decode('utf-8'))
                        self._last_hash = last.get('hash')
            except Exception:
                self._last_hash = None

    def _init_db(self):
        """Initialize PostgreSQL storage."""
        conn = psycopg2.connect(self.db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            # Create table if not exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    hash TEXT NOT NULL,
                    prev_hash TEXT,
                    entry JSONB NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_logs_hash ON audit_logs(hash);
                CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);
            """)
            
            # Get last hash
            cur.execute("SELECT hash FROM audit_logs ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                self._last_hash = row[0]
            else:
                self._last_hash = None
        conn.close()

    def _digest(self, entry: dict, prev_hash: str | None) -> str:
        m = hashlib.sha256()
        # Ensure deterministic JSON serialization for hashing
        m.update(json.dumps(entry, sort_keys=True).encode('utf-8'))
        if prev_hash:
            m.update(prev_hash.encode('utf-8'))
        return m.hexdigest()

    def append(self, entry: dict) -> dict:
        prev = self._last_hash
        ts_iso = datetime.utcnow().isoformat()
        
        # Calculate new hash
        h = self._digest(entry, prev)
        
        entry_with_meta = {
            "entry": entry,
            "prev_hash": prev,
            "hash": h,
            "ts": ts_iso
        }

        if self._use_db:
            try:
                conn = psycopg2.connect(self.db_url)
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO audit_logs (timestamp, hash, prev_hash, entry) VALUES (%s, %s, %s, %s)",
                            (ts_iso, h, prev, Json(entry))
                        )
                conn.close()
                self._last_hash = h
                return entry_with_meta
            except Exception as e:
                print(f"MerkleLogStore: DB append failed ({e}), falling back to file")
                # Fallback to file on DB failure
        
        # File append (default or fallback)
        with open(self.path, 'ab') as f:
            f.write((json.dumps(entry_with_meta) + "\n").encode('utf-8'))
        
        self._last_hash = h
        return entry_with_meta

    def get_logs(self, limit: int = 100, offset: int = 0) -> list:
        """Retrieve logs from the active storage backend."""
        if self._use_db:
            try:
                conn = psycopg2.connect(self.db_url)
                logs = []
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT timestamp, hash, prev_hash, entry 
                            FROM audit_logs 
                            ORDER BY id DESC 
                            LIMIT %s OFFSET %s
                        """, (limit, offset))
                        rows = cur.fetchall()
                        for row in rows:
                            # reconstruct entry_with_meta format
                            logs.append({
                                "ts": row[0].isoformat() if row[0] else None,
                                "hash": row[1],
                                "prev_hash": row[2],
                                "entry": row[3]
                            })
                conn.close()
                return logs[::-1] # Return in chronological order if desired, or keep DESC
            except Exception as e:
                print(f"MerkleLogStore: DB read failed: {e}")
                return []

        # File reader implementation
        logs = []
        try:
            with open(self.path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                # This is a naive implementation for file reading; 
                # for production file reading we'd need a better approach than reading all
                # or guessing bytes. For now, we rely on the DB path mostly.
                # Just reading the last N lines roughly
                f.seek(max(0, f.tell() - (limit * 1000)), 0) 
                lines = f.read().splitlines()
                for line in lines[-limit:]:
                    try:
                        logs.append(json.loads(line))
                    except:
                        pass
        except FileNotFoundError:
            pass
        return logs

    def verify_chain(self, logs: Optional[list] = None) -> Dict[str, Any]:
        """Verify Merkle chain integrity for the provided logs (or stored logs)."""
        if logs is None:
            logs = self.get_logs(limit=10000)

        if not logs:
            return {"valid": True, "valid_links": 0, "total": 0, "root_hash": None}

        valid_links = 0
        prev_hash = None

        for idx, entry in enumerate(logs):
            # Tolerate both file and DB shapes: either top-level keys or nested under 'entry'
            entry_payload = entry.get("entry") if "entry" in entry else entry
            stored_prev = entry.get("prev_hash")
            stored_hash = entry.get("hash")

            expected_hash = self._digest(entry_payload, stored_prev)
            if stored_hash != expected_hash or stored_prev != prev_hash:
                return {
                    "valid": False,
                    "valid_links": valid_links,
                    "total": len(logs),
                    "broken_at": idx,
                }

            valid_links += 1
            prev_hash = stored_hash

        return {
            "valid": True,
            "valid_links": valid_links,
            "total": len(logs),
            "root_hash": prev_hash,
        }
