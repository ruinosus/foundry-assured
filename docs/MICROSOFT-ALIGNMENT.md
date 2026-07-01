# Microsoft alignment — conformance matrix

**Purpose.** This project follows many patterns that Microsoft indicates for Foundry, Agent
Framework, CopilotKit/AG-UI and azd. This file is the **living, auditable record of *which*
patterns we follow, *where*, and the *proof* (the Microsoft doc link)** — the artifact that answers
"how do we know / prove we're aligned with Microsoft?".

**Relation to ADRs.** [`docs/adr/`](./adr/) records *decisions* ("we chose X because Y"). This file
records *conformance* ("Microsoft indicates X → here's where we do it → here's the doc"). They are
complementary: an ADR should link the Microsoft guidance it rests on; this matrix aggregates all such
guidance into one place.

**How to maintain.** When you follow (or verify, per CLAUDE.md rule #1) a Microsoft-indicated pattern,
add a row: the pattern, the file/path where it lives, and the doc URL. The doc URL **is** the proof.
Prefer `learn.microsoft.com` canonical pages; a Q&A / repo / blog is acceptable when it's the most
specific source. Keep it honest — if we *deviate* from a pattern, say so in the Notes.

> Legend: ✅ follows · ⚠️ partial / deviation noted · 🔎 verified in-session against the installed SDK/docs

---

## 1. Authentication & identity

| Pattern (Microsoft indicates) | Where we do it | Proof |
|---|---|---|
| ✅ Keyless auth via **Microsoft Entra ID / `DefaultAzureCredential`** (no API keys) — the project rule #2 | all backend Azure calls; enforced (API keys blocked) | [Authentication & authorization in Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/authentication-authorization-foundry) |
| ✅ Token scope for the Foundry data plane = **`https://ai.azure.com/.default`** | `azure-ai-projects` `get_openai_client`; the auth scheme | [Authentication & authorization in Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/authentication-authorization-foundry) |
| ✅ **User-assigned managed identity** for the Azure-hosted backend (Container Apps) | `infra/resources.bicep` (`id-assured-app`), `containerapps.bicep` `AZURE_CLIENT_ID` | [Managed identity for Azure resources](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/overview) |
| ✅ **On-Behalf-Of (OBO)** for downstream calls as the signed-in user | `app/core/auth.py`, `app/agents/secure_search.py` | [OBO flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow) |
| ✅ API app manifest **`requestedAccessTokenVersion: 2`** (else v1 token → invalid claims) | `scripts/setup-entra.sh` | [Access token version](https://learn.microsoft.com/en-us/entra/identity-platform/access-tokens) |
| ✅ **Multi-tenant bearer** (`MultiTenantAzureAuthorizationCodeBearer`) in shared mode; single-tenant otherwise | `app/core/auth.py` | [fastapi-azure-auth](https://intility.github.io/fastapi-azure-auth/) |

## 2. Models, agents & retrieval

| Pattern (Microsoft indicates) | Where we do it | Proof |
|---|---|---|
| ✅ **Service identity calls models via a hosted agent**, not raw inference — the MI is authorized for `/agents/…`, but the Foundry data plane 403s a service principal on raw `/openai/v1/responses` (verified in-session; matches the [known Q&A](https://learn.microsoft.com/en-us/answers/questions/5779747/azure-ai-foundry-agent-returns-403-rbac-access-den)) 🔎 | `apps/hosted-{agent,cockpit,selfwiki,platform}` + the Live/Hosted toggle | [Hosted agents (preview)](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) |
| ✅ **`FoundryChatClient` + `DefaultAzureCredential`** for KB-grounded agents | `app/agents/*.py`, `apps/hosted-*/main.py` | [Agent types (agent-framework)](https://learn.microsoft.com/en-us/agent-framework/user-guide/agents/agent-types/azure-ai-foundry-agent) |
| ✅ **Responses API** is the path for gpt-5 models (the SDK routes gpt-5 through `/responses`) 🔎 | verified via `OPENAI_LOG=debug` | [Use the Responses API](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses) |
| ✅ **Foundry IQ knowledge base + agentic retrieval** (`AzureAISearchContextProvider`, `mode="agentic"`) | `app/agents/cockpit.py`, `selfwiki.py`, ingest scripts | [Connect agents to Foundry IQ KBs](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/knowledge-retrieval?view=foundry) |
| ✅ Deploy hosted agents via **`azd ai agent` / `host: azure.ai.agent`** (remote build) | `azure.yaml`, the `apps/hosted-*` services | [Foundry Agent Service overview](https://learn.microsoft.com/en-us/azure/foundry/agents/overview) |
| ⚠️ **Structured citations/annotations** — the Microsoft way is to attach the KB as the **`knowledge_base_retrieve` MCP tool** (`{search}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview`, `require_approval="never"`), which yields a `References:` list + inline `【message_idx:search_idx†source_name】` annotations. **We deviate (tracked)**: our agents use `FoundryChatClient + AzureAISearchContextProvider` (docs injected as *context* → prose citations, empty `annotations`, verified in-session). The `EvidencePanel` derives sources from the answer text (v1). **Migration designed + Microsoft-pattern verified 🔎** in [`specs/2026-07-01-grounded-obo-citations-design.md`](./superpowers/specs/2026-07-01-grounded-obo-citations-design.md) (Responses-API-as-the-user path, §8 quotes the docs); STEP 0 gates the preview shapes. Note: search-index KBs return a citation URL that **falls back to the MCP endpoint** (no doc URL) → click-through shows retrieved *content*. | `app/agents/*.py`, `apps/hosted-*/main.py`, `components/console/EvidencePanel.tsx` | [Connect agents to Foundry IQ KBs](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect) |
| ✅ **Per-user auth for MCP-tool retrieval = the Azure OpenAI Responses API**, NOT the Agent Service — verbatim: *"Foundry Agent Service doesn't support per-request headers for MCP tools… For per-user authorization, use the Azure OpenAI Responses API instead."* 🔎 | design: `specs/2026-07-01-grounded-obo-citations-design.md` (Approach A); impl pending STEP 0 | [Connect agents to Foundry IQ KBs](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect) |
| ✅ **Query-time document ACL** via `x-ms-query-source-authorization` (user search token) — permission metadata in `filterable` fields; needs **both** the app's **Search Index Data Reader** role **and** the user header; **fail-closed** (5xx on ACL-eval failure); *"if the user token is omitted, only public documents are returned."* 🔎 | design: same spec (Cockpit `acl=True`); today's app-side trim in `app/agents/secure_search.py` | [Query-time ACL & RBAC enforcement](https://learn.microsoft.com/en-us/azure/search/search-query-access-control-rbac-enforcement) |

## 3. Frontend — AG-UI / CopilotKit

| Pattern (Microsoft indicates) | Where we do it | Proof |
|---|---|---|
| ✅ **AG-UI ↔ Agent Framework** over SSE (workflow-as-agent, intermediate steps) | `app/main.py` `add_agent_framework_fastapi_endpoint`; the `/helpdesk` endpoint | [AG-UI integration](https://learn.microsoft.com/agent-framework/integrations/ag-ui/) |
| ✅ CopilotKit **v2 multi-route** runtime handler (`createCopilotRuntimeHandler`), not the legacy single-route endpoint — the v2 client drives `/agent/:id/run` + `/info` sub-paths 🔎 | `apps/frontend/app/api/copilotkit/[[...slug]]/route.ts` | [CopilotKit runtime](https://docs.copilotkit.ai/built-in-agent/copilot-runtime) |
| ✅ **MSAL** for the SPA (loginRedirect, `apiScopes`) | `apps/frontend/lib/auth/msal.ts` | [MSAL React](https://learn.microsoft.com/en-us/entra/identity-platform/tutorial-single-page-app-react-sign-in) |

## 4. Infrastructure & deployment (azd / Bicep)

| Pattern (Microsoft indicates) | Where we do it | Proof |
|---|---|---|
| ✅ **azd lifecycle hooks** (postprovision/postdeploy) for env-push + RBAC reconciliation | `azure.yaml` hooks, `scripts/hook-*.sh` | [azd hooks](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/azd-extensibility) |
| ✅ **Bicep = control plane; data plane via scripts** (KB/memory not in Bicep) | `infra/*.bicep` vs `app/knowledge/*`, `cli/*` | [Control plane vs data plane](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/control-plane-and-data-plane) |
| ✅ **Foundry region can differ from Search/Storage region** (project independent of enterprise services) 🔎 | current: eastus2 Foundry, eastus Search (an option we researched) | [Multi-region Foundry pattern](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/a-multi-region-microsoft-foundry-pattern-for-enterprise-private-networking/4525696) |
| ✅ Hosted-agent **session quota is per-subscription/region, requestable** (the 429 `regional_session_quota_exceeded`) 🔎 | operational | [Agent Service limits/quotas/regions](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions) |
| ✅ **Managed Application + Lighthouse** for the dedicated stamp (multi-tenant SaaS) | `infra/managed-app/`, `infra/lighthouse/` (ADR-002) | [Azure Managed Applications](https://learn.microsoft.com/en-us/azure/azure-resource-manager/managed-applications/overview) · [Lighthouse](https://learn.microsoft.com/en-us/azure/lighthouse/overview) |

## 5. Access control (RBAC)

| Pattern (Microsoft indicates) | Where we do it | Proof |
|---|---|---|
| ✅ **Foundry User** (`53ca6127…`, ex-"Azure AI User") for data-plane inference — **NOT** Cognitive Services / Azure AI Developer roles ("don't assign those in Foundry") 🔎 | `infra/resources.bicep` `appToFoundry`; the postdeploy hook grants agent identities | [RBAC for Microsoft Foundry](https://learn.microsoft.com/en-us/azure/foundry/concepts/rbac-foundry) |
| ✅ **App Roles** (Admin/Author/Approver/Reader) in the token `roles` claim for app authorization | `app/core/auth.py` `require_role`, `scripts/setup-app-roles.sh` | [App roles](https://learn.microsoft.com/en-us/entra/identity-platform/howto-add-app-roles-in-apps) |
| ✅ **Microsoft Graph app-only** for user + app-role management (no parallel user store) | `app/services/graph.py`, `app/api/admin.py` | [Graph application permissions](https://learn.microsoft.com/en-us/graph/permissions-overview) |

## 6. Evaluation & quality

| Pattern (Microsoft indicates) | Where we do it | Proof |
|---|---|---|
| ✅ **agent-framework native eval** (`LocalEvaluator` gate + `FoundryEvals` hosted judges) | `apps/backend/eval/run_eval.py` | [aka.ms/assert](https://aka.ms/assert) |
| ✅ **RAG-triad** judges (groundedness / relevance / coherence) | `eval/run_eval.py` (`FoundryEvals`) | [Evaluation in Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/develop/evaluate-sdk) |
| ✅ **`microsoft/ai-agent-evals`** GitHub Action (pairwise vs baseline) | `.github/workflows/agent-evals.yml` | [ai-agent-evals action](https://github.com/microsoft/ai-agent-evals) |

## 7. Testing

| Pattern (Microsoft indicates) | Where we do it | Proof |
|---|---|---|
| ✅ **Playwright** (Microsoft) for browser E2E | `e2e/` | [Playwright](https://playwright.dev/docs/intro) |
| ✅ **MSAL storageState / TOTP** for authenticated E2E (no interactive login per run) | `e2e/entra-mfa.ts` (software-OATH TOTP) | [Testing MSAL apps with Playwright](https://dev.to/yahyaalshwaily/testing-msal-protected-single-page-applications-in-playwright-2f35) |

---

*Add a row whenever you follow (or verify) a Microsoft-indicated pattern. The doc link is the proof.
Rows marked 🔎 were verified in-session against the installed SDK / live behavior, not just docs.*
