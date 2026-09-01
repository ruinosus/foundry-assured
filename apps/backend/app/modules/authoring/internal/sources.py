"""Adapters de leitura para as fontes donas; nenhuma lista operacional é persistida aqui."""

from __future__ import annotations

from dataclasses import asdict

from app.modules.authoring.internal.catalog import CatalogSource


def _connections() -> list[dict]:
    from app.modules.tenancy.public import current_tenant_id, tenant_store

    store = tenant_store()
    record = store.get(current_tenant_id()) if store is not None else None
    if record is None:
        return []
    return [
        {
            "id": connection.id,
            "name": connection.label,
            "state": "available" if connection.enabled else "unavailable",
            "kind": connection.kind,
        }
        for connection in record.connections
    ]


def _connection(resource_id: str) -> dict:
    from app.modules.tenancy.public import current_connection

    connection = current_connection(resource_id)
    if connection is None:
        raise KeyError(resource_id)
    projected = asdict(connection)
    projected.pop("keyvault_ref", None)
    return projected


def default_sources() -> tuple[CatalogSource, ...]:
    from app.modules.formflow.public import (
        list_copilots,
        list_flows,
        load_copilot,
        load_flow,
    )
    from app.modules.foundry.public import (
        get_agent,
        get_knowledge,
        get_skill,
        get_toolbox,
        list_agents,
        list_knowledge,
        list_skills,
        list_toolboxes,
    )
    from app.modules.usecases.public import get_use_case, list_use_cases

    def knowledge() -> list[dict]:
        return list_knowledge(100).get("bases", [])

    def named(names: list[str]) -> list[dict]:
        return [{"id": name, "name": name, "state": "available"} for name in names]

    return (
        CatalogSource("agent", "Microsoft Foundry Agents", lambda: list_agents(100), get_agent),
        CatalogSource("knowledge", "Azure AI Search", knowledge, get_knowledge),
        CatalogSource("skill", "Microsoft Foundry Skills", lambda: list_skills(100), get_skill),
        CatalogSource("toolbox", "Microsoft Foundry Toolboxes", lambda: list_toolboxes(100), get_toolbox),
        CatalogSource("connection", "Microsoft Foundry Connections", _connections, _connection),
        CatalogSource("usecase", "Foundry agent metadata", list_use_cases, get_use_case),
        CatalogSource("formflow", "Authoring FormFlow documents", lambda: named(list_flows()), load_flow),
        CatalogSource("copilot", "Authoring copilot documents", lambda: named(list_copilots()), load_copilot),
    )
