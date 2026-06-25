# Policy: Secrets management

**Applies to:** All engineers handling credentials, tokens, and keys.

## Rules
1. Secrets live in Azure Key Vault or the corp password manager — never in code, env files committed to git, tickets, or chat.
2. Application secrets are injected at runtime via managed identity or mounted Key Vault references. Hardcoded keys are a security violation.
3. Use `DefaultAzureCredential` (Entra ID) for Azure services instead of API keys wherever the service supports it.
4. Rotate shared secrets on a schedule and immediately on suspected exposure (see the credential rotation runbook).

## If a secret leaks
1. Treat it as compromised even if exposure seems limited.
2. Rotate the secret immediately.
3. Open a SEV2 (or SEV1 if it's a production credential) and notify the security team.
4. Purge the secret from any logs or history where it appeared.

## Never
Never share a secret to "unblock" someone faster. Grant scoped, time-boxed access instead.
