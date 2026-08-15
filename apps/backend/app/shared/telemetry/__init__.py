"""Telemetry bootstrap for the serving path (spec Phase 5.5a).

Before this, OpenTelemetry existed only inside `wiki_builder` as an opt-in for one CLI run:
the serving path — FastAPI, the workflow, grounded, platform — exported nothing, even though
`azure-monitor-opentelemetry` was already a dependency. That is why this lands BEFORE the
module refactor rather than after it: the refactor's own success criteria (route snapshot,
AG-UI fixtures) are structural and cannot see a latency, cost or error-rate regression.

Three exporter choices, in order, decided once at boot:
  1. `APPLICATIONINSIGHTS_CONNECTION_STRING` → Azure Monitor (the pattern already proven in
     `wiki_builder._maybe_setup_observability`, including the Foundry-project fallback).
  2. `OTEL_EXPORTER_OTLP_ENDPOINT` → generic OTLP over HTTP. Only the HTTP exporter is
     installed here; gRPC is deliberately not attempted.
  3. Neither → **no-op**. No provider, no exporter, no overhead. This is the default, and it
     is what keeps I-1 true: without configuration the app behaves exactly as it did.

Signatures verified against the installed packages, not assumed (Rule #1):
    enable_instrumentation(*, enable_sensitive_data: bool | None = None, force: bool = False)
    configure_azure_monitor(**kwargs)
"""

from __future__ import annotations

import logging
import os

from app.shared.settings import settings
from app.shared.telemetry import conventions
from app.shared.telemetry.content_policy import capture_enabled

logger = logging.getLogger(__name__)

_configured = False


# NOTE (ADR-017): `wiki_builder` also falls back to asking the Foundry project for the
# connection string, which needs `tenant_config()` — a business module. The shared kernel is
# not allowed to reach for that, and import-linter says so. So the fallback stays with the
# caller: `setup_telemetry(connection_string=...)` accepts a resolved string, and the
# composition root (which may import anything) is free to obtain it however it likes.
# In production the environment variable is what the infrastructure sets anyway.


def _resource_attributes() -> dict[str, str]:
    return {
        "service.name": "foundry-assured-backend",
        "deployment.environment": os.environ.get("ENVIRONMENT", "local"),
        conventions.APP_DEPLOYMENT_MODE: settings.deployment_mode,
    }


def setup_telemetry(*, connection_string: str | None = None) -> bool:
    """Configure OTEL export once. Returns True if an exporter was wired, False for no-op.

    `connection_string` overrides `APPLICATIONINSIGHTS_CONNECTION_STRING` and exists so the
    composition root can resolve it from somewhere this package may not reach (see note above).

    Idempotent: the composition root calls it at boot, and calling it again is a no-op rather
    than a second provider (which would double every span).
    """
    global _configured
    if _configured:
        return True

    sensitive = capture_enabled(settings)

    connection = connection_string or os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if connection:
        try:
            from agent_framework.observability import enable_instrumentation
            from azure.monitor.opentelemetry import configure_azure_monitor
        except ImportError:
            logger.warning("telemetry: azure-monitor-opentelemetry not installed — staying off")
            return False
        configure_azure_monitor(
            connection_string=connection,
            resource_attributes=_resource_attributes(),
        )
        enable_instrumentation(enable_sensitive_data=sensitive)
        _configured = True
        logger.info(
            "telemetry: gen_ai spans → Application Insights (content capture=%s)", sensitive
        )
        return True

    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            from agent_framework.observability import enable_instrumentation
        except ImportError:
            logger.warning("telemetry: OTLP HTTP exporter not installed — staying off")
            return False
        provider = TracerProvider(resource=Resource.create(_resource_attributes()))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        enable_instrumentation(enable_sensitive_data=sensitive)
        _configured = True
        logger.info("telemetry: gen_ai spans → OTLP (content capture=%s)", sensitive)
        return True

    logger.debug("telemetry: no exporter configured — no-op")
    return False


def configured() -> bool:
    """Whether an exporter is active. Callers use it to skip work that only feeds telemetry."""
    return _configured
