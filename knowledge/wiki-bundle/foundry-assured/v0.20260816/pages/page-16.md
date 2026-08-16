# Assurance Console

`components/console/AssuranceConsole.tsx` is the canonical frontend chat surface. It is one UI for every domain, with runtime-specific behavior selected from the domain registry. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L3-L13) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L52-L65)

## Runtime-sensitive UI behavior

The console distinguishes runtime kinds explicitly. Domain metadata decides agent identity and runtime selection: `activeAgentId` is either the live domain id or the hosted twin id, so AG-UI routing and hosted/live selection are metadata-driven rather than per-page hardcoded. Agent Framework approvals and LangGraph approvals intentionally use different plumbing: workflow/tool domains rely on the `request_info` custom-event subscription path implemented by `TicketApproval`, while graph domains rely on CopilotKit’s `useInterrupt` path implemented by `GraphApproval`.

- `workflow` → renders workflow steps and Agent Framework approval card.
- `tool` → renders Agent Framework approval card without workflow steps.
- `graph` → renders `GraphApproval` because LangGraph interrupts are different.
- `grounded` → no HITL component at all. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L33-L50) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L81-L87)

This is not cosmetic branching. The code comments explain that Agent Framework and LangGraph emit different interrupt shapes, so the approval components cannot be merged safely.

## Hosted/live toggles

If a domain declares `hostedAgentId`, the console shows a live/hosted toggle and switches `activeAgentId` accordingly. The toggle is therefore registry-driven rather than domain-hardcoded. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L53-L59) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L89-L108)

That is the main extension seam for adding a hosted twin to another domain.

## Evidence side panel

The console always renders `EvidencePanel` beside the chat. That is the UI embodiment of the repository’s assurance promise: answer content and evidence/citations are a two-pane experience, not a hidden debug view. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L24-L27) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L110-L117)

## Auth lifecycle

Like the older dedicated chat components, the console acquires tokens silently, refreshes them every four minutes, and degrades to direct rendering when auth is not configured. This avoids mid-session silent 401 failures on long-lived live chats. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L132-L180)

## Validation

The main validation for console changes is browser-level:

- `/d/helpdesk` for workflow + approval + hosted toggle
- `/d/platform` for tool approval paths
- `/d/oncall` for graph approval
- `/d/selfwiki` or `/d/techdocs` for grounded evidence rendering

The Playwright smoke suite exercises several of those paths together.
