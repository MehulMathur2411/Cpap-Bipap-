

import json
import os
import queue
import threading
import time
from datetime import datetime
from typing import Callable, Optional, Any

class OfflineQueue:
   
    def __init__(
        self,
        queue_file: str,
        on_send_success: Optional[Callable[[str], None]] = None,
        on_send_fail: Optional[Callable[[str], None]] = None,
        max_retries: int = 3,
        ack_timeout: float = 10.0
    ):
        self.queue_file = queue_file
        self.on_send_success = on_send_success
        self.on_send_fail = on_send_fail
        self.max_retries = max_retries
        self.ack_timeout = ack_timeout

        self._queue = queue.Queue()           
        self._pending = []                   
        self._ack_received = threading.Event()
        self._ack_received.set()         
        self._lock = threading.Lock()

        self._load_from_disk()
        self._start_worker()


    # Public API
    
    def put(self, payload: dict):
        """Add a new payload from UI (thread-safe)"""
        payload_str = json.dumps(payload, separators=(',', ':'))
        self._queue.put(payload_str)

    def acknowledge(self):
        """Call this when ACK is received from device"""
        self._ack_received.set()

    def is_connected(self) -> bool:
        """For external use – check if AWS thread is alive"""
        return self._worker.is_alive()
        

    # Internal: disk persistence
   
    def _load_from_disk(self):
        if not os.path.exists(self.queue_file):
            self._pending = []
            return
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._pending = data if isinstance(data, list) else []
            print(f"[OfflineQueue] Loaded {len(self._pending)} pending payload(s)")
        except Exception as e:
            print(f"[OfflineQueue] Failed to load queue: {e}")
            self._pending = []
            self.pending (),
            
    def _save_to_disk(self):
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(self._pending, f, indent=2)
        except Exception as e:
            print(f"[OfflineQueue] Failed to save queue: {e}")

    
    # Internal: worker thread
    
    def _start_worker(self):
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def _worker_loop(self):
        while True:
        
            try:
                payload_str = self._queue.get(timeout=1)
                if payload_str in self._pending:
                    print("[OfflineQueue] Duplicate ignored")
                    continue
                self._try_send(payload_str)
            except queue.Empty:
                pass

            # 2. Retry pending if ready
            if self._ack_received.is_set() and self._pending:
                self._try_send(self._pending[0])

            time.sleep(0.5)

    def _try_send(self, payload_str: str):
        print(f"[OfflineQueue] Sending: {payload_str[:80]}...")

        # Simulate network send
        success = self._simulate_publish(payload_str)

        if success:
            self._ack_received.clear()
            if self._wait_for_ack():
                with self._lock:
                    if self._pending and self._pending[0] == payload_str:
                        self._pending.pop(0)
                    self._save_to_disk()
                if self.on_send_success:
                    self.on_send_success(payload_str)
                print("[OfflineQueue] ACK received → removed from queue")
            else:
                self._handle_no_ack(payload_str)
        else:
            self._handle_send_fail(payload_str)

    def _simulate_publish(self, payload_str: str) -> bool:
    
    
        import random
        return random.random() < 0.8

    def _wait_for_ack(self) -> bool:
        return self._ack_received.wait(timeout=self.ack_timeout)

    def _handle_no_ack(self, payload_str: str):
        print("[OfflineQueue] No ACK in time → keeping in queue")
        if payload_str not in self._pending:
            self._pending.append(payload_str)
            self._save_to_disk()

    def _handle_send_fail(self, payload_str: str):
        print("[OfflineQueue] Send failed → storing offline")
        if payload_str not in self._pending:
            self._pending.append(payload_str)
            self._save_to_disk()
        if self.on_send_fail:
            self.on_send_fail(payload_str)

 
    # Utility

    def clear(self):
        """Clear all pending data (use with caution)"""
        with self._lock:
            self._pending = []
            if os.path.exists(self.queue_file):
                os.remove(self.queue_file)
        print("[OfflineQueue] Queue cleared")

    def get_pending_count(self) -> int:
        return len(self._pending)

    def get_pending(self) -> list:
        return self._pending.copy()