# Infrastructure identity and access

Identity in this repository crosses several layers:

- frontend user sign-in through MSAL,
- backend bearer validation and OBO,
- app-only Graph access,
- managed identities for live infrastructure,
- hosted-agent identities,
- app roles and group-based document access.

This page focuses on the cross-system identity model rather than route-level auth mechanics.

## Frontend and backend app registrations

The backend settings file distinguishes:

- API app registration: `entra_api_client_id`, `entra_api_client_secret`, `entra_tenant_id`
- SPA app registration: `entra_spa_client_id`

The frontend builds tokens for the backend API audience, and the backend validates those tokens. That is the prerequisite for the OBO path.

## OBO prerequisites

The OBO path requires:

- frontend to acquire a token for the backend API scope,
- backend to know the Entra tenant, client ID, and client secret,
- backend to create `OnBehalfOfCredential` from the incoming access token.

The deploy workflow and `main.bicep` both surface these settings because they are part of the runtime identity contract, not a dev-only feature.

## App roles

The repository-level app roles are:

- `Admin`
- `Author`
- `Approver`
- `Reader`

They are used:

- by backend authorization checks,
- by admin UI role assignment flows,
- by tenant connection role thresholds,
- by workflow approval constraints.

The admin APIs manage these assignments through Microsoft Graph app-role assignment endpoints.

## Graph app-only identity

`app/services/graph.py` uses `ClientSecretCredential` and Graph `.default` scope to operate with the backend app's own identity.

This identity is separate from the end-user OBO path. It exists because user lifecycle and app-role assignment are administrative control-plane actions, not delegated data-plane calls.

## Managed identities and Azure resources

Infrastructure outputs in `infra/main.bicep` show that the deployment provisions an application identity used by the runtime stack.

That identity is passed into `containerapps.bicep` so backend and web deployments can use the right Azure-connected resources.

The deploy workflow also depends on Azure OIDC and role assignments matching the deployer's principal type.

## Search and document access

Per-document access does not primarily come from app roles. It comes from Search-side ACL trimming using end-user identity and document group metadata.

That model involves:

- Search RBAC for the service identity making retrieve calls,
- OBO-acquired search token for the end user,
- `x-ms-query-source-authorization` on ACL-aware domains,
- ACL group maps and stamped group IDs in ingested content.

So the repository has two complementary access systems:

1. **application roles** for feature and action authorization,
2. **source-following document access** for retrieval authorization.

## Hosted-agent identity

Hosted agent containers use `DefaultAzureCredential()` with platform-injected identity. They do not inherit the live backend's per-request OBO behavior.

That means hosted agents are identity-distinct from live AG-UI paths and must be documented and tested separately.

## App users group

`APP_USERS_GROUP_ID` is surfaced through provisioning and deployment because it doubles as:

- the group granted Foundry user access,
- the selfwiki audience group for ACL-aware retrieval.

It is injected into the backend container app as the `APP_USERS_GROUP_ID` environment variable in `infra/containerapps.bicep`. Backend domain construction then uses it to build selfwiki's `acl_group_map`. The deploy workflow comments explicitly call out that leaving it unset causes selfwiki retrieval to fail closed and return zero docs in deployed environments.

## Dedicated mode delegation

In dedicated mode, cross-tenant operations are achieved through Lighthouse delegation rather than by moving resources into the publisher's tenant. This preserves the customer ownership boundary while letting the operator observe and manage the environment with a least-privilege role set.

## Validation

Identity wiring is validated indirectly through:

- auth and tenant tests in `apps/backend/eval/`,
- deploy workflow behavior,
- runtime sign-in and OBO-backed domain requests,
- Graph-backed admin operations,
- security gate workflows for ACL enforcement.

## Related pages

- Backend auth and tenancy
- Admin and tenant APIs
- Infrastructure deployment
- Dedicated mode infrastructure
