"""Lightweight VM heartbeat agent. It never opens Outlook or a mailbox."""
from __future__ import annotations

import json
import os
import platform
import time
import urllib.request

URL = os.getenv("INTERLOG_DASHBOARD_URL", "http://127.0.0.1:8080").rstrip("/")
WORKER_ID = os.getenv("INTERLOG_WORKER_ID", "vm-worker-01")


def heartbeat() -> None:
    payload = json.dumps({
        "id": WORKER_ID,
        "display_name": "VM Export Worker",
        "machine_name": platform.node(),
        "role": "export",
        "status": "ONLINE",
        "version": "0.2.0",
        "detail": "Heartbeat only — no mailbox access",
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{URL}/api/workers/heartbeat", data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


if __name__ == "__main__":
    print(f"InterLOG VM Worker heartbeat -> {URL} ({WORKER_ID})")
    while True:
        try:
            heartbeat()
        except Exception as exc:
            print(f"Heartbeat failed: {exc}")
        time.sleep(15)
