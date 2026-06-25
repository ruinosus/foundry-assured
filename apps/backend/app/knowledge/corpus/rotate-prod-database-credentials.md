# Runbook: Rotate production database credentials

**Applies to:** PostgreSQL production clusters managed in Azure Key Vault.

## When to rotate
- Every 90 days (automated reminder).
- Immediately if a credential may be exposed (leaked log, offboarded engineer with prior access).

## Procedure
1. Generate a new password in Key Vault: `az keyvault secret set --vault-name kv-prod --name db-app-password --value <generated>`.
2. Add the new credential as a **secondary** role on the database, do not drop the old one yet:
   `ALTER ROLE app_user WITH PASSWORD '<generated>';`
3. Trigger a rolling restart of the app deployment so pods pick up the new secret:
   `kubectl rollout restart deployment/api -n prod`.
4. Verify all pods are healthy and connected, then confirm the old password is unused in connection logs for 24h.
5. Only after 24h of clean logs, retire the old secret version in Key Vault.

## Important
Never paste the generated password into chat, tickets, or commit messages. Rotation must be logged in the change-management channel with the Key Vault secret version (not the value).
