// Foundry Helpdesk — Azure Lighthouse delegation (shared-model data-plane management).
//
// ADR-001/ADR-002: in the shared model the customer delegates specific scopes to
// OUR managing tenant so we can operate their data-plane resources cross-tenant —
// without ever owning the customer's data. The delegation is REVOCABLE (the
// customer can remove the registration assignment at any time) and AUDITABLE
// (every managing-tenant action is attributed in the customer's activity log).
//
// The customer deploys this template into THEIR subscription (subscription scope)
// — it does not run from our tenant. It registers our tenant as a managed-service
// provider and assigns the delegation at the subscription scope with a
// LEAST-PRIVILEGE set of built-in roles (no Owner, no broad Contributor).
//
// Schema/types verified against the Azure Lighthouse Bicep reference
// (learn.microsoft.com/azure/lighthouse) — Microsoft.ManagedServices
// registrationDefinitions + registrationAssignments. Built-in role definition
// GUIDs are stable Azure identifiers (cross-checked against `az role definition
// list`), not invented (CLAUDE.md rule #1).

targetScope = 'subscription'

@description('The tenant ID of the MANAGING tenant (ours) that will operate the delegated scopes.')
param managedByTenantId string

@description('Display name shown to the customer for this Lighthouse offer.')
param mspOfferName string = 'Foundry Helpdesk — managed data-plane operations'

@description('Description shown to the customer for this Lighthouse offer.')
param mspOfferDescription string = 'Least-privilege, revocable cross-tenant management of the Foundry Helpdesk data-plane resources by the publisher.'

@description('Object ID (in the MANAGING tenant) of the user/group/service principal granted the delegated roles. For a group, set principalIdDisplayName accordingly.')
param principalId string

@description('Friendly name of the principal above (shown in the customer activity log).')
param principalIdDisplayName string = 'Foundry Helpdesk Operations'

// Built-in role definition GUIDs (stable; verified via `az role definition list`).
// Least-privilege set for operating the Container Apps stamp + observing it:
//  - Reader: full read visibility across delegated scope.
//  - Monitoring Contributor: read/operate diagnostics, metrics, alerts (support).
//  - Log Analytics Reader: read application logs in the workspace for triage.
// No Owner / Contributor — the publisher operates and observes, it does not own.
var roleReader = 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
var roleMonitoringContributor = '749f88d5-cbae-40b8-bcfc-e573ddc772fa'
var roleLogAnalyticsReader = '73c42c96-874c-492b-b04d-ab87d138a893'

var authorizations = [
  {
    principalId: principalId
    principalIdDisplayName: principalIdDisplayName
    roleDefinitionId: roleReader
  }
  {
    principalId: principalId
    principalIdDisplayName: principalIdDisplayName
    roleDefinitionId: roleMonitoringContributor
  }
  {
    principalId: principalId
    principalIdDisplayName: principalIdDisplayName
    roleDefinitionId: roleLogAnalyticsReader
  }
]

// Stable, deterministic GUID for the registration so re-deploys are idempotent.
var registrationName = guid(mspOfferName, managedByTenantId, subscription().subscriptionId)

resource registrationDefinition 'Microsoft.ManagedServices/registrationDefinitions@2022-10-01' = {
  name: registrationName
  properties: {
    registrationDefinitionName: mspOfferName
    description: mspOfferDescription
    managedByTenantId: managedByTenantId
    authorizations: authorizations
  }
}

resource registrationAssignment 'Microsoft.ManagedServices/registrationAssignments@2022-10-01' = {
  name: guid(registrationName, subscription().subscriptionId)
  properties: {
    registrationDefinitionId: registrationDefinition.id
  }
}

output registrationDefinitionId string = registrationDefinition.id
output registrationAssignmentId string = registrationAssignment.id
