import threading
import time
import requests
import json
import os

class LogSyncWorker:
    """
    Background worker to sync offline/bypass logs to AgentShield when connectivity is restored.
    """
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.buffer = []
        self.lock = threading.Lock()
        self.interval = 30  # seconds
        self.running = False
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join()

    def add_event(self, event: dict):
        """Add an event to the sync buffer."""
        with self.lock:
            # Add a timestamp if missing
            if 'timestamp' not in event:
                event['timestamp'] = time.time()
            self.buffer.append(event)

    def _run(self):
        while self.running:
            if not self.buffer:
                time.sleep(self.interval)
                continue

            # Try to sync
            try:
                with self.lock:
                    batch = list(self.buffer)
                
                if not batch:
                    continue

                url = f"{self.base_url}/v1/audit/offline_batch"
                # Send batch
                resp = requests.post(url, json={"events": batch}, timeout=5)
                
                if resp.status_code in (200, 201):
                    # Success, clear buffer
                    with self.lock:
                        # Remove items that were in the batch
                        # (A simplistic approach: just clear the buffer if we assume no new items were added that we shouldn't delete. 
                        # To be safe, we rebuild the list excluding the ones we sent, but for this MVP, clearing up to len(batch) is fine)
                        # Actually, keeping it simple: clear the buffer.
                        # Race condition: add_event might append while we are sending.
                        # So we should only remove the items we took.
                        self.buffer = self.buffer[len(batch):]
                    print(f"LogSyncWorker: Synced {len(batch)} offline events.")
                else:
                    # Failed, wait and retry
                    print(f"LogSyncWorker: Sync failed (HTTP {resp.status_code}), retrying later.")
            
            except Exception as e:
                print(f"LogSyncWorker: Sync failed ({str(e)}), retrying later.")
            
            time.sleep(self.interval)
