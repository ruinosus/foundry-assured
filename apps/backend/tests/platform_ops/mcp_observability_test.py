"""F07: discovery emite somente telemetria agregada e content-free."""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

from app.modules.audit.public import InMemoryEvidenceStore
from app.modules.platform_ops.internal.mcp_discovery import DiscoveryTelemetry
from app.modules.platform_ops.public import (
    DiscoveryRejected,
    InMemoryMcpSourceStore,
    discover_toolbox,
    get_mcp_source,
)

_CANARY = "F07-CANARY-REMOTE-SECRET"
_ALLOWED = {
    "tenant_hash",
    "source_hash",
    "snapshot_id",
    "outcome",
    "duration_seconds",
    "tool_count",
    "drift_count",
    "code",
}


class _Logger:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def info(self, _message: str, *, extra: dict) -> None:
        self.events.append(extra["mcp_discovery"])


class _Span:
    def __init__(self) -> None:
        self.attributes: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def set_attribute(self, key: str, value) -> None:
        self.attributes[key.removeprefix("app.mcp.discovery.")] = value


class _Tracer:
    def __init__(self) -> None:
        self.spans: list[_Span] = []

    def start_as_current_span(self, _name: str) -> _Span:
        span = _Span()
        self.spans.append(span)
        return span


class _Instrument:
    def __init__(self) -> None:
        self.records: list[tuple[float, dict]] = []

    def add(self, value: float, attributes: dict) -> None:
        self.records.append((value, attributes))

    def record(self, value: float, attributes: dict) -> None:
        self.records.append((value, attributes))


class _Meter:
    def __init__(self) -> None:
        self.counter = _Instrument()
        self.histogram = _Instrument()

    def create_counter(self, _name: str) -> _Instrument:
        return self.counter

    def create_histogram(self, _name: str, *, unit: str) -> _Instrument:
        assert unit == "s"
        return self.histogram


class _Recorder:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, attributes: dict) -> None:
        self.events.append(attributes)


class _Mcp:
    def __init__(self, **_kwargs) -> None:
        self.session = SimpleNamespace(_protocol_version="2025-06-18")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def load_tools(self) -> None:
        await self.session.list_tools(params=None)


class _Session:
    _protocol_version = "2025-06-18"

    async def list_tools(self, *, params=None):
        del params
        return SimpleNamespace(
            tools=[
                {
                    "name": "malicious",
                    "description": f"Authorization: Bearer {_CANARY}",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                    },
                }
            ],
            nextCursor=None,
        )


def _factory(**kwargs):
    tool = _Mcp(**kwargs)
    tool.session = _Session()
    return tool


def _source(_name: str, _version: str) -> dict:
    return {
        "id": "tb-observability",
        "name": "observability",
        "version": "1",
        "url": "https://example.test/secret-path/mcp",
    }


async def _malicious_discovery() -> tuple[list[dict], str]:
    evidence = InMemoryEvidenceStore()
    source_store = InMemoryMcpSourceStore()
    recorder = _Recorder()
    audits: list[dict] = []
    try:
        await discover_toolbox(
            "observability",
            "1",
            toolbox_resolver=_source,
            mcp_factory=_factory,
            evidence_store=evidence,
            source_store=source_store,
            audit_recorder=lambda **event: audits.append(event),
            telemetry_recorder=recorder,
        )
    except DiscoveryRejected:
        pass
    durable = json.dumps(
        {
            "blob": list(evidence._items.items()),
            "table": get_mcp_source("tb-observability", store=source_store),
            "audit": audits,
        },
        default=str,
    )
    return recorder.events, durable


def main() -> int:
    attributes = {
        "tenant_hash": "a" * 16,
        "source_hash": "b" * 16,
        "snapshot_id": "msnap_safe",
        "outcome": "success",
        "duration_seconds": 1.25,
        "tool_count": 2,
        "drift_count": 1,
        "code": "OK",
    }
    logger = _Logger()
    tracer = _Tracer()
    meter = _Meter()
    DiscoveryTelemetry(tracer=tracer, meter=meter, logger=logger).record(attributes)
    metric_attributes = {key: value for key, value in attributes.items() if key != "duration_seconds"}
    events, durable = asyncio.run(_malicious_discovery())
    serialized_events = json.dumps(events)

    checks = {
        "log recebe somente atributos permitidos": logger.events == [attributes],
        "span recebe somente atributos permitidos": tracer.spans[0].attributes == attributes,
        "contador recebe agregados sem duração": meter.counter.records == [(1, metric_attributes)],
        "histograma recebe duração e agregados": meter.histogram.records == [(1.25, metric_attributes)],
        "falha emite somente chaves permitidas": len(events) == 1 and set(events[0]) == _ALLOWED,
        "falha registra código e outcome": events[0]["code"] == "MCP_PROTOCOL_INVALID" and events[0]["outcome"] == "failure",
        "canário ausente de log, trace e métricas": _CANARY not in serialized_events,
        "canário ausente de Table, Blob e audit": _CANARY not in durable,
        "URL remota ausente da telemetria": "example.test" not in serialized_events,
    }
    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
