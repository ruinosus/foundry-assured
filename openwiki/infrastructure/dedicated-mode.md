---
type: infrastructure-page
title: Dedicated mode infrastructure
description: Managed Application and Lighthouse packaging for dedicated customer deployments, including customer-subscription boundaries and cross-tenant operations.
tags: [infrastructure, dedicated, managed-app, lighthouse]
---

# Dedicated mode infrastructure

Dedicated mode is the repository's enterprise packaging path for running a single-tenant stamp in the customer's cloud while the publisher operates it. The relevant artifacts live in:

<!-- openwiki: broken internal link [../../infra/managed-app] file "../../infra/managed-app" does not exist. Fix the href or restore the target, then delete this comment. -->
- [`infra/managed-app`](../../infra/managed-app)
<!-- openwiki: broken internal link [../../infra/lighthouse] file "../../infra/lighthouse" does not exist. Fix the href or restore the target, then delete this comment. -->
- [`infra/lighthouse`](../../infra/lighthouse)

The README treats this as a first-class deployment mode, not an afterthought.

## Managed Application package

Main artifact:

- [`infra/managed-app/managedApp.bicep`](../../infra/managed-app/managedApp.bicep)

Supporting artifacts:

- `mainTemplate.json`
- `createUiDefinition.json`
- `build.sh`

### Scope and intent

`managedApp.bicep` is `targetScope = 'resourceGroup'`, not subscription scope. The source comments explain why:

- in a Managed Application, Azure creates the managed resource group,
- the main template deploys *into* that managed RG,
- so this template must not create its own resource group.

This is a re-parameterization of the shared modules `../resources.bicep` and `../containerapps.bicep`, not a duplicate infrastructure model.

### Packaging semantics

The source comments document a critical deployment caveat:

- both composed modules declare the same Log Analytics workspace name,
- this converges safely under **Incremental** mode,
- it is fragile under **Complete** mode,
- therefore Managed Application updates for this template must use **Incremental** mode.

That warning is operationally significant. A deployment-mode change that ignores it could create unsafe reconciliation behavior.

### Operator boundary

The comments also explain the operator model:

- resources are still in the customer's subscription,
- the managed resource group is controlled through the managed-application model,
- publisher-side operation does not imply publisher ownership of the customer's data.

## Lighthouse delegation

Main artifact:

- [`infra/lighthouse/lighthouse.bicep`](../../infra/lighthouse/lighthouse.bicep)

### Purpose

Lighthouse is the cross-tenant operations mechanism for the dedicated/shared-operations model.

The source comments emphasize that the delegation is:

- **revocable** by the customer,
- **auditable** in the customer's activity log,
- scoped with a **least-privilege** role set.

### Scope

This template is `targetScope = 'subscription'` and is deployed by the customer into **their** subscription.

It creates:

- `Microsoft.ManagedServices/registrationDefinitions`
- `Microsoft.ManagedServices/registrationAssignments`

### Delegated roles

The bicep file hard-codes a least-privilege set of built-in roles:

- `Reader`
- `Monitoring Contributor`
- `Log Analytics Reader`

The comments explicitly call out that it does **not** assign broad `Owner` or `Contributor`.

## How dedicated mode fits the product model

Dedicated mode keeps the runtime behavior closer to self-hosted than shared mode does:

- backend code still uses `SingleTenantConfigProvider`,
- each deployment still represents one tenant's resources,
- the main difference is packaging and operational delegation rather than request-time multi-tenancy.

So the dedicated mode seam is mostly an **infrastructure and operations** seam, not a deep runtime branching seam.

## Relationship to D-packaging runbook

The source comments in `managedApp.bicep` mention `docs/D-PACKAGING-RUNBOOK.md` for publisher post-deploy wiring such as hosted agent and toolbox steps. That runbook is part of the dedicated deployment story and should be read alongside the infrastructure code when making operational changes.

## Validation

Compile validation:

```bash
bicep build infra/managed-app/managedApp.bicep --stdout > /dev/null
bicep build infra/lighthouse/lighthouse.bicep --stdout > /dev/null
```

For packaging artifacts, also inspect `infra/managed-app/build.sh` and regenerated `mainTemplate.json` when changing the bicep source.

## Related pages

- [Infrastructure deployment](deployment.md)
- [Infrastructure identity and access](identity-and-access.md)
- [Architecture overview](../architecture/overview.md)
