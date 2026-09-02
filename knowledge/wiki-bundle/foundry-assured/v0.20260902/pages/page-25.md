---
type: infrastructure
title: Infrastructure and Deployment
description: "Azure deployment topology, azd service map, Bicep composition, managed application assets, and the environment outputs that wire runtime services together."
tags: [infrastructure, azd, bicep, deployment]
---
# Infrastructure and deployment

The repository’s infrastructure entrypoint is `azure.yaml`, which defines six deployable services: backend, web frontend, and four Azure AI hosted agents. It also wires postprovision and postdeploy hooks into the deployment lifecycle. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/azure.yaml#L6-L23) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/azure.yaml#L24-L68) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/azure.yaml#L73-L81)

## Bicep entrypoint

`infra/main.bicep` is subscription-scoped. It creates the resource group, invokes `resources.bicep` for the data-plane/resources stack, then invokes `containerapps.bicep` for backend and web deployment. It exports the key runtime outputs consumed later by scripts and services: Foundry endpoint/model ids, Search endpoint/KB, storage ids, and web/backend URLs. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/infra/main.bicep#L10-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/infra/main.bicep#L55-L76) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/infra/main.bicep#L78-L126)

## Deployment-mode signals

Even though deployment mode is mostly runtime behavior, infrastructure already reflects some mode-sensitive concerns:

- Search deployment can be disabled to support model-driven-only environments.
- Entra client ids/secrets and app-users group id are surfaced into Container Apps outputs.
- Hosted agents are provisioned as first-class deployable services. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/infra/main.bicep#L32-L49) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/infra/main.bicep#L90-L101)

## Managed app and Lighthouse assets

The `infra/managed-app/` and `infra/lighthouse/` directories are the dedicated-stamp assets referenced by the README’s deployment-mode story. They are the infrastructure counterpart to the “customer cloud, we operate” mode. Source

## Hooks as deployment steps

The hooks configured in `azure.yaml` are part of the real deployment contract, not conveniences:

- `postprovision` → `scripts/hook-postprovision.sh`
- `postdeploy` → `scripts/hook-postdeploy.sh`

Those scripts propagate env values, assign runtime RBAC, and register SPA redirect URIs. If hooks are skipped, deployment may succeed while auth or hosted-agent permissions remain broken. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/azure.yaml#L73-L81) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/scripts/up-all.sh#L11-L16)

## Operational guidance

For infra changes, validate at the narrowest level possible:

- Bicep template review/output expectations
- hook script behavior
- azd service wiring in `azure.yaml`

Only after that should you run full `azd up` style provisioning tests.
