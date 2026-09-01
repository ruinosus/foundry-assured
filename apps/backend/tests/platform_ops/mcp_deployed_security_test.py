"""F08: prova implantada de SSE/WORM e isolamento de egress no Azure.

O teste nao altera configuracao de infraestrutura nem bloqueia policies. Com
``--require-azure``, configuracao ausente e qualquer controle ausente falham alto.
Sem a flag, o modulo faz skip limpo para continuar executavel em suites offline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from uuid import uuid4

from azure.core import MatchConditions
from azure.core.exceptions import (
    HttpResponseError,
    ResourceExistsError,
    ResourceModifiedError,
)
from azure.core.pipeline import Pipeline
from azure.core.pipeline.policies import BearerTokenCredentialPolicy, RetryPolicy
from azure.core.pipeline.transport import RequestsTransport
from azure.core.rest import HttpRequest
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

_ARM_SCOPE = "https://management.azure.com/.default"
_RESOURCE_ID = re.compile(
    r"^/subscriptions/(?P<subscription>[^/]+)/resourceGroups/(?P<group>[^/]+)/"
    r"providers/Microsoft\.Storage/storageAccounts/(?P<account>[^/]+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Deployment:
    storage_id: str
    subscription_id: str
    resource_group: str
    storage_account: str
    resource_token: str

    @classmethod
    def parse(cls, resource_id: str) -> Deployment:
        match = _RESOURCE_ID.fullmatch(resource_id.rstrip("/"))
        if match is None:
            raise ValueError("AZURE_STORAGE_RESOURCE_ID must be a full storage ARM resource id")
        account = match.group("account")
        prefix = "stassured"
        if not account.lower().startswith(prefix) or len(account) == len(prefix):
            raise ValueError("storage account does not follow the deployed stassured<token> contract")
        return cls(
            storage_id=resource_id.rstrip("/"),
            subscription_id=match.group("subscription"),
            resource_group=match.group("group"),
            storage_account=account,
            resource_token=account[len(prefix):],
        )


class ArmClient:
    def __init__(self, credential: DefaultAzureCredential) -> None:
        self._transport = RequestsTransport()
        self._pipeline = Pipeline(
            transport=self._transport,
            policies=[RetryPolicy(), BearerTokenCredentialPolicy(credential, _ARM_SCOPE)],
        )

    def close(self) -> None:
        self._transport.close()

    def get(self, resource_id: str, api_version: str) -> dict:
        request = HttpRequest(
            "GET",
            f"https://management.azure.com{resource_id}?api-version={api_version}",
        )
        response = self._pipeline.run(request).http_response
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("ARM returned a non-object response")
        return payload


class Checks:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, condition: bool) -> None:
        print(f"  {'PASS' if condition else 'FAIL'} {name}")
        if not condition:
            self.failures.append(name)


class DeployedControlMissing(RuntimeError):
    """Um recurso que materializa um controle declarado nao esta implantado."""


def _properties(resource: dict) -> dict:
    properties = resource.get("properties")
    return properties if isinstance(properties, dict) else {}


def _same_resource(left: object, right: object) -> bool:
    return isinstance(left, str) and isinstance(right, str) and left.lower() == right.lower()


def _validate_storage(arm: ArmClient, deployment: Deployment, checks: Checks) -> None:
    storage = arm.get(deployment.storage_id, "2023-05-01")
    storage_properties = _properties(storage)
    encryption = storage_properties.get("encryption") or {}
    services = encryption.get("services") or {}
    blob_encryption = services.get("blob") or {}
    checks.check("Storage accepts HTTPS only", storage_properties.get("supportsHttpsTrafficOnly") is True)
    checks.check("Storage minimum TLS is 1.2", storage_properties.get("minimumTlsVersion") == "TLS1_2")
    checks.check("Blob encryption at rest is enabled", blob_encryption.get("enabled") is True)
    checks.check("Public blob access is disabled", storage_properties.get("allowBlobPublicAccess") is False)

    blob_service_id = f"{deployment.storage_id}/blobServices/default"
    blob_service = arm.get(blob_service_id, "2023-05-01")
    checks.check("Blob versioning is enabled", _properties(blob_service).get("isVersioningEnabled") is True)

    container_id = f"{blob_service_id}/containers/audit"
    container = arm.get(container_id, "2023-05-01")
    immutable = _properties(container).get("immutableStorageWithVersioning") or {}
    checks.check("Audit container has version-level immutability", immutable.get("enabled") is True)

    policy = arm.get(f"{container_id}/immutabilityPolicies/default", "2023-05-01")
    policy_properties = _properties(policy)
    checks.check(
        "WORM retention is at least one day",
        isinstance(policy_properties.get("immutabilityPeriodSinceCreationInDays"), int)
        and policy_properties["immutabilityPeriodSinceCreationInDays"] >= 1,
    )
    checks.check(
        "WORM policy is active",
        str(policy_properties.get("state", "")).lower() in {"locked", "unlocked"},
    )
    checks.check(
        "Protected append writes are enabled",
        policy_properties.get("allowProtectedAppendWrites") is True,
    )
    print(f"  INFO WORM policy state: {policy_properties.get('state', 'unknown')}")


def _validate_egress(arm: ArmClient, deployment: Deployment, checks: Checks) -> None:
    base = (
        f"/subscriptions/{deployment.subscription_id}/resourceGroups/{deployment.resource_group}"
        "/providers"
    )
    token = deployment.resource_token
    nsg_id = f"{base}/Microsoft.Network/networkSecurityGroups/nsg-discovery-{token}"
    vnet_id = f"{base}/Microsoft.Network/virtualNetworks/vnet-discovery-{token}"
    environment_id = f"{base}/Microsoft.App/managedEnvironments/cae-backend-{token}"
    backend_id = f"{base}/Microsoft.App/containerApps/ca-backend-{token}"

    try:
        nsg = arm.get(nsg_id, "2024-05-01")
    except HttpResponseError as exc:
        if exc.status_code == 404:
            raise DeployedControlMissing("discovery egress NSG is not deployed") from exc
        raise
    rules = _properties(nsg).get("securityRules") or []
    deny_rule = next(
        (rule for rule in rules if str(rule.get("name", "")).lower() == "deny-non-public-egress"),
        {},
    )
    deny_properties = _properties(deny_rule)
    denied = {str(prefix).lower() for prefix in deny_properties.get("destinationAddressPrefixes", [])}
    required = {"10.0.0.0/8", "127.0.0.0/8", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10"}
    checks.check(
        "NSG has an outbound deny rule",
        deny_properties.get("direction") == "Outbound" and deny_properties.get("access") == "Deny",
    )
    checks.check("NSG denies private, loopback and metadata ranges", required <= denied)

    vnet = arm.get(vnet_id, "2024-05-01")
    subnets = _properties(vnet).get("subnets") or []
    protected_subnet = next((item for item in subnets if item.get("name") == "container-apps"), {})
    subnet_properties = _properties(protected_subnet)
    subnet_id = protected_subnet.get("id")
    checks.check(
        "Container Apps subnet uses the discovery NSG",
        _same_resource((subnet_properties.get("networkSecurityGroup") or {}).get("id"), nsg_id),
    )

    environment = arm.get(environment_id, "2024-03-01")
    environment_subnet = (_properties(environment).get("vnetConfiguration") or {}).get(
        "infrastructureSubnetId"
    )
    checks.check("Backend environment uses the protected subnet", _same_resource(environment_subnet, subnet_id))

    backend = arm.get(backend_id, "2024-03-01")
    checks.check(
        "Backend app uses the protected environment",
        _same_resource(_properties(backend).get("managedEnvironmentId"), environment_id),
    )


def _validate_worm_data_plane(
    credential: DefaultAzureCredential,
    deployment: Deployment,
    checks: Checks,
) -> None:
    service = BlobServiceClient(
        account_url=f"https://{deployment.storage_account}.blob.core.windows.net",
        credential=credential,
    )
    container = service.get_container_client("audit")
    blob_name = f"mcp-snapshots/deployed-security/{uuid4().hex}.json"
    blob = container.get_blob_client(blob_name)
    body = json.dumps({"kind": "mcp-deployed-security", "nonce": uuid4().hex}).encode()

    try:
        blob.upload_blob(
            body,
            match_condition=MatchConditions.IfMissing,
            content_settings=ContentSettings(content_type="application/json"),
        )
        properties = blob.get_blob_properties()
        checks.check("Evidence blob is encrypted by the service", properties.server_encrypted is True)

        overwrite_denied = False
        try:
            blob.upload_blob(b"{}", match_condition=MatchConditions.IfMissing)
        except (ResourceExistsError, ResourceModifiedError):
            overwrite_denied = True
        checks.check("Create-once evidence cannot be overwritten", overwrite_denied)

        delete_denied = False
        try:
            blob.delete_blob(delete_snapshots="include")
        except HttpResponseError as exc:
            delete_denied = exc.status_code in {409, 412}
        checks.check("Evidence cannot be deleted during WORM retention", delete_denied)
    finally:
        service.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-azure",
        action="store_true",
        help="fail instead of skipping when AZURE_STORAGE_RESOURCE_ID is absent",
    )
    return parser


def _deployment_from_env() -> Deployment | None:
    resource_id = os.environ.get("AZURE_STORAGE_RESOURCE_ID", "").strip()
    if resource_id:
        return Deployment.parse(resource_id)

    subscription_id = os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    resource_group = os.environ.get("AZURE_RESOURCE_GROUP", "").strip()
    storage_account = os.environ.get("AZURE_STORAGE_ACCOUNT", "").strip()
    if not all((subscription_id, resource_group, storage_account)):
        return None
    return Deployment.parse(
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Storage/storageAccounts/{storage_account}"
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        deployment = _deployment_from_env()
    except ValueError as exc:
        print(f"FAIL invalid deployment configuration: {exc}")
        return 2
    if deployment is None:
        message = (
            "AZURE_STORAGE_RESOURCE_ID or AZURE_SUBSCRIPTION_ID + AZURE_RESOURCE_GROUP + "
            "AZURE_STORAGE_ACCOUNT is required for the deployed security proof"
        )
        if args.require_azure:
            print(f"FAIL {message}")
            return 2
        print(f"SKIP {message}")
        return 0

    checks = Checks()
    credential = DefaultAzureCredential()
    arm = ArmClient(credential)
    print(
        "MCP deployed security proof "
        f"(resource_group={deployment.resource_group}, storage={deployment.storage_account})"
    )
    try:
        _validate_storage(arm, deployment, checks)
        _validate_worm_data_plane(credential, deployment, checks)
        _validate_egress(arm, deployment, checks)
    except DeployedControlMissing as exc:
        print(f"FAIL {exc}")
        return 1
    except HttpResponseError as exc:
        print(f"FAIL Azure request rejected (status={exc.status_code}, code={exc.error_code or 'unknown'})")
        return 1
    finally:
        arm.close()
        credential.close()

    print(f"\n{'FAIL' if checks.failures else 'PASS'} {len(checks.failures)} failed control(s)")
    return 1 if checks.failures else 0


if __name__ == "__main__":
    sys.exit(main())
