// Phase 4 — Entra security groups for document-level access control on the KB.
//
// Enterprise pattern (least-privilege, classification-tiered): instead of a group per
// artifact, documents are classified by sensitivity and each tier is one cloud-only,
// security-enabled group. A multinational maps these to its own existing tiers; the
// component→tier mapping lives in the ingest pipeline, so the scheme adapts without
// changing identities. Naming follows the common enterprise convention: `SEC-` prefix,
// kebab-case, scope-qualified.
//
// Self-installable via the Microsoft Graph Bicep extension (GA). The deploying identity
// needs directory rights to create groups (e.g. Groups Administrator). Deploy at tenant
// scope:
//
//   az deployment tenant create \
//     --name techdocs-entra --location <loc> \
//     --template-file infra/entra/entra.bicep
//
// Outputs are the group object-IDs — feed them to the ingest ACL mapping
// (ACL_GROUPS) and the backend, so docs get stamped and queries get trimmed.
// Test users + memberships are created by ./create-test-users.sh (users with passwords
// don't belong in IaC).

targetScope = 'tenant'

extension microsoftGraphV1

resource gPublic 'Microsoft.Graph/groups@v1.0' = {
  displayName: 'SEC-techdocs-kb-public'
  description: 'TechDocs KB — public/general documents (all employees).'
  uniqueName: 'sec-techdocs-kb-public'
  mailEnabled: false
  mailNickname: 'sec-techdocs-kb-public'
  securityEnabled: true
}

resource gInternal 'Microsoft.Graph/groups@v1.0' = {
  displayName: 'SEC-techdocs-kb-internal'
  description: 'TechDocs KB — internal platform/component documents.'
  uniqueName: 'sec-techdocs-kb-internal'
  mailEnabled: false
  mailNickname: 'sec-techdocs-kb-internal'
  securityEnabled: true
}

resource gConfidential 'Microsoft.Graph/groups@v1.0' = {
  displayName: 'SEC-techdocs-kb-confidential'
  description: 'TechDocs KB — confidential (security/architecture internals).'
  uniqueName: 'sec-techdocs-kb-confidential'
  mailEnabled: false
  mailNickname: 'sec-techdocs-kb-confidential'
  securityEnabled: true
}

output publicGroupId string = gPublic.id
output internalGroupId string = gInternal.id
output confidentialGroupId string = gConfidential.id
