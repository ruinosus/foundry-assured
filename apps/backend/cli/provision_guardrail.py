"""Attach a Content Safety guardrail to the deployed hosted agent (Phase: safety).

Adds a Responsible AI guardrail so Foundry screens every prompt + response against
a policy at runtime. `agent.yaml` (the azd deploy config) doesn't carry guardrails —
they live in `agent.manifest.yaml` (azd) or are set via the SDK `RaiConfig`. Since
our deploy uses agent.yaml, this data-plane script applies the guardrail with the
SDK: it reads the deployed version's image/config and creates a new version that
adds `rai_config` (default policy `Microsoft.DefaultV2`; pass --policy <ARM id> for
a custom one).

  uv run python -m app.guardrail_provision                 # default policy
  uv run python -m app.guardrail_provision --policy <id>   # custom RAI policy

Run after `azd deploy helpdesk-concierge`. Note: a later `azd deploy` creates a new
version from agent.yaml and would drop the guardrail — re-run this, or move the
deploy to an agent.manifest.yaml with a `policies` entry. APIs verified against
azure-ai-projects 2.2.0 (RaiConfig, HostedAgentDefinition, agents.create_version).
"""

from __future__ import annotations

import argparse
import sys
import time

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentProtocol,
    ContainerConfiguration,
    HostedAgentDefinition,
    ProtocolVersionRecord,
    RaiConfig,
)
from azure.identity import DefaultAzureCredential

from app.core.settings import settings
from app.core.tenant import tenant_config


def _as_dict(obj) -> dict:
    return obj if isinstance(obj, dict) else obj.as_dict()


def _latest(project: AIProjectClient, agent: str) -> dict:
    versions = [_as_dict(v) for v in project.agents.list_versions(agent_name=agent)]
    if not versions:
        raise SystemExit(f"Agent '{agent}' has no versions — deploy it first (azd deploy).")
    return max(versions, key=lambda v: int(v.get("version", 0)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a content-safety guardrail to the hosted agent.")
    parser.add_argument(
        "--policy",
        required=True,
        help="full ARM resource id of the RAI policy — the service requires it. The built-in "
        "default is `.../accounts/<account>/raiPolicies/Microsoft.DefaultV2`.",
    )
    args = parser.parse_args()

    agent = tenant_config().hosted_agent_name
    project = AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )

    current = _as_dict(_latest(project, agent))
    definition = current["definition"]
    image = definition["image"]
    # The deployed definition stores env as a {name: value} dict already.
    env = dict(definition.get("environment_variables") or {})

    print(f"Adding content-safety guardrail to '{agent}' (from v{current['version']}, image {image}) …")
    new_version = project.agents.create_version(
        agent_name=agent,
        definition=HostedAgentDefinition(
            container_configuration=ContainerConfiguration(image=image),
            cpu=definition.get("cpu", "0.5"),
            memory=definition.get("memory", "1Gi"),
            protocol_versions=[ProtocolVersionRecord(protocol=AgentProtocol.RESPONSES, version="1.0.0")],
            environment_variables=env,
            rai_config=RaiConfig(rai_policy_name=args.policy),
        ),
    )
    version = _as_dict(new_version)["version"]
    print(f"Created v{version}; waiting for it to become active …")

    while True:
        status = _as_dict(project.agents.get_version(agent_name=agent, agent_version=version))["status"]
        print(f"  status: {status}")
        if status == "active":
            print(f"✅ Guardrail applied — '{agent}' v{version} screens prompts + responses.")
            return
        if status == "failed":
            print("❌ Provisioning failed.")
            sys.exit(1)
        time.sleep(5)


if __name__ == "__main__":
    main()
