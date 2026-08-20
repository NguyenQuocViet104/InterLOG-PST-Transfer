"""Purview connector guardrail.

Real export is intentionally disabled until certificate permissions and a test
mailbox are verified. No username or password is accepted by this module.
"""
from __future__ import annotations

import os


def configuration() -> dict[str, str | bool]:
    tenant = os.getenv("INTERLOG_TENANT_ID", "")
    client = os.getenv("INTERLOG_CLIENT_ID", "")
    certificate = os.getenv("INTERLOG_CERTIFICATE_THUMBPRINT", "")
    return {
        "tenant_id": tenant,
        "client_id": client,
        "certificate_configured": bool(certificate),
        "ready": bool(tenant and client and certificate),
    }


def start_export(*_: object, **__: object) -> None:
    if os.getenv("INTERLOG_TEST_MODE", "1") != "0":
        raise RuntimeError("Purview export is locked while INTERLOG_TEST_MODE is enabled")
    if not configuration()["ready"]:
        raise RuntimeError("Purview certificate configuration is incomplete")
    raise NotImplementedError("Production Purview execution has not been enabled")
