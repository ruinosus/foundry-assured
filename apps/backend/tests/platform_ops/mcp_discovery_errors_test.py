"""F07: falhas de discovery têm envelope estável e content-free."""

from __future__ import annotations

import json
import sys

from app.modules.platform_ops.api import _discovery_error
from app.modules.platform_ops.internal.mcp_discovery import (
    CONNECT_TIMEOUT_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    TOTAL_TIMEOUT_SECONDS,
)
from app.modules.platform_ops.public import (
    DiscoveryBusy,
    DiscoveryLimitExceeded,
    DiscoveryRejected,
    EgressDenied,
)

_CANARY = "CANARY-REMOTE-SECRET-8472"


def _body(exc: Exception) -> tuple[int, dict]:
    response = _discovery_error(exc)
    return response.status_code, json.loads(response.body)["error"]


def main() -> int:
    cases = [
        (EgressDenied("MCP_SOURCE_NOT_FOUND"), 404, "MCP_SOURCE_NOT_FOUND", False),
        (EgressDenied("MCP_ENDPOINT_NOT_APPROVED"), 409, "MCP_ENDPOINT_NOT_APPROVED", False),
        (
            DiscoveryLimitExceeded(f"oversized {_CANARY}"),
            413,
            "MCP_DISCOVERY_LIMIT_EXCEEDED",
            False,
        ),
        (EgressDenied("MCP_EGRESS_DENIED"), 422, "MCP_EGRESS_DENIED", False),
        (DiscoveryRejected(f"invalid {_CANARY}"), 422, "MCP_PROTOCOL_INVALID", False),
        (EgressDenied("MCP_AUTH_NOT_AVAILABLE"), 424, "MCP_AUTH_FAILED", False),
        (DiscoveryBusy(f"busy {_CANARY}"), 429, "MCP_DISCOVERY_BUSY", True),
        (RuntimeError(f"upstream {_CANARY}"), 502, "MCP_SOURCE_UNAVAILABLE", True),
        (TimeoutError(f"slow {_CANARY}"), 504, "MCP_DISCOVERY_TIMEOUT", True),
    ]
    checks: dict[str, bool] = {}
    checks["timeouts connect/request/total são 5/10/15 s"] = (
        CONNECT_TIMEOUT_SECONDS,
        REQUEST_TIMEOUT_SECONDS,
        TOTAL_TIMEOUT_SECONDS,
    ) == (5, 10, 15)
    correlation_ids: set[str] = set()
    for exc, expected_status, expected_code, retryable in cases:
        status, error = _body(exc)
        correlation_id = error.get("correlationId", "")
        correlation_ids.add(correlation_id)
        checks[f"{expected_code}: status e envelope"] = (
            status == expected_status
            and error.get("code") == expected_code
            and error.get("retryable") is retryable
            and set(error) == {"code", "message", "correlationId", "retryable"}
            and len(correlation_id) == 32
        )
        checks[f"{expected_code}: sem conteúdo remoto"] = (
            _CANARY not in json.dumps(error) and "Traceback" not in json.dumps(error)
        )

    checks["correlationId é único por falha"] = len(correlation_ids) == len(cases)
    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
