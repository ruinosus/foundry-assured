"""Leitura efêmera de credencial de uma Foundry project connection."""

from __future__ import annotations


class ConnectionCredentialUnavailable(RuntimeError):
    """A connection não pode autenticar o endpoint solicitado."""


def resolve_connection_bearer(
    connection_id: str, expected_target: str | None = None
) -> str:
    """Resolve uma ApiKey em memória usando a identidade da aplicação."""
    from azure.ai.projects import AIProjectClient
    from azure.core.exceptions import AzureError
    from azure.identity import DefaultAzureCredential

    from app.modules.tenancy.public import tenant_config

    client = AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
    )
    try:
        connection = client.connections.get(connection_id, include_credentials=True)
    except AzureError:
        raise ConnectionCredentialUnavailable(
            "MCP_CONNECTION_AUTH_UNAVAILABLE"
        ) from None
    target = getattr(connection, "target", None)
    if expected_target is not None and target != expected_target:
        raise ConnectionCredentialUnavailable("MCP_CONNECTION_AUTH_UNAVAILABLE")
    bearer = getattr(getattr(connection, "credentials", None), "api_key", None)
    if not isinstance(bearer, str) or not bearer:
        raise ConnectionCredentialUnavailable("MCP_CONNECTION_AUTH_UNAVAILABLE")
    return bearer
