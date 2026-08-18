# ADR-023 — The evidence layer: Azure owns immutability, we own the event

- **Status:** Proposed
- **Date:** 2026-08-18
- **Context:** [`apps/backend/app/modules/hitl/public.py`](../../apps/backend/app/modules/hitl/public.py),
  [`apps/backend/app/modules/helpdesk/internal/escalation.py`](../../apps/backend/app/modules/helpdesk/internal/escalation.py),
  [`apps/backend/app/modules/tickets/internal/tickets.py`](../../apps/backend/app/modules/tickets/internal/tickets.py),
  [`apps/backend/app/shared/telemetry/content_policy.py`](../../apps/backend/app/shared/telemetry/content_policy.py),
  [`infra/containerapps.bicep`](../../infra/containerapps.bicep)
- **Related:** [ADR-005](./ADR-005-never-store-secrets.md) — never store customer secrets;
  [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md) — write governance;
  [ADR-021](./ADR-021-canvas-flows-as-foundry-datasets.md) — the ephemeral-disk failure mode

## Context

This repository has a mature **assurance** layer — deterministic gates, ACL trimming, fail-closed
approval — and no **evidence** layer. Stated plainly: *it decides well and proves nothing.*

The gap was found by comparing against a compliance product built for CFM 2.454/2026, whose bar is
not "did you log it" but "is what you logged still provable". Measured against this codebase:

**Nothing records who approved.** `hitl.public` computes `decision.approver_roles`
(`public.py:113`) and `escalation.py` reads only `.type` and `.args` — the field is discarded.
`create_ticket` takes no approver, no approval timestamp, no decision type. RULE #5 says the tool
fires only after an Approver approves; there is no artifact that shows it did.

**The code refers five times to an audit log that was never built.**
`content_policy.py:13` leaves the approver's identity out of telemetry because *"the person belongs
in the application's audit log"*. There is no audit log. There is no `sha256` anywhere in the
backend.

**Telemetry cannot stand in for it, by design.** With no exporter configured `setup_telemetry` is a
no-op, and that is the default; content capture is off by default; retention is 30 days. A record
that is off unless someone turns it on is not evidence.

## What was measured, before deciding to write anything

Two first-party primitives cover the part that must not be hand-rolled.

**Azure Storage immutable blobs — WORM, on the storage account this project already has.** A
container-level *time-based retention policy* with **`allowProtectedAppendWrites`** exists
specifically for this shape: new blocks may be appended to an append blob, while modification and
deletion of existing blocks are refused by the platform. Once the policy is **locked**, the
settings cannot be changed, and the container keeps its own policy audit log (user id, command,
timestamps, retention interval) retained per **SEC 17a-4(f)**.

This matters because the current conversation store is already an append blob — append-only *by
the API we happen to call*, not by policy. Nothing stops `delete_blob` from anyone holding storage
RBAC. The same bytes, under a locked policy, become immutable **because Azure refuses**, not
because our code is polite.

**Azure Confidential Ledger — cryptographic receipts.** Append-only ledger running in a hardware
enclave, recording a Merkle tree over transactions, from which a client can obtain a **receipt**
proving a specific entry was committed. Python SDK, Entra auth.

The two are not competitors; they answer different questions. WORM answers *"was this store
altered?"* — with Azure as the authority. The ledger answers *"can I prove this exact record was
committed at that time?"* — with a receipt that survives leaving Azure.

## Decision

**Azure owns immutability. We own the event.**

**1 — The record is an append-only, hash-chained event stream, written to a WORM container.**
The chain is ours; it is assurance, which is this project's stated exception to the MÁXIMA MAIOR.
It is not redundant with WORM: WORM protects the *store*, the chain protects the *record*, and only
the chain travels — an exported audit bundle can be verified by someone who has no access to our
storage account. Each event carries `seq`, `at`, `actor`, `kind`, `summary`, `ref`, `prev`, `hash`,
where `hash = sha256(prev + payload)`.

**2 — Immutability is a container policy in `infra/`, not a promise in a docstring.** Time-based
retention with `allowProtectedAppendWrites`. Unlocked in non-production so the environment stays
disposable; locking is a deliberate act with its own consequences, and this ADR does not pretend
otherwise.

**3 — Confidential Ledger is the upgrade, swappable behind the same writer.** Tenants who need a
receipt get one; the rest pay nothing for a capability they will not use. The writer is one
interface with two implementations — the same shape as the tenant store (ADR-006).

**4 — The HITL decision becomes the first event, because it is the one RULE #5 depends on.**
`who` (object id + roles), `what` (tool and arguments), `when`, `decision` (approve / edit /
reject), and, on edit, both the original and the correction. This is data that is *already
computed and thrown away*; making it durable is a small change with the largest single effect on
the audit posture.

**5 — Personal data is stopped before persistence, at one structural point.** Conversation
transcripts are currently written whole and unfiltered, and the ticket summary is model text with
no filter. A single write path applies a deterministic redactor, findings are stored **masked
only**, and the redaction itself becomes an event. One point, verified by a gate — a redactor that
can be bypassed by calling a different function is decoration.

Two limits stated on purpose. The redactor is **deterministic** (structural patterns: government
IDs, card-shaped numbers, dates of birth, e-mail, phone) and therefore incomplete; it is a barrier,
not a guarantee, and the product still must not be pointed at patient data. And redaction happens
**before the write**, never as a cleanup pass — a cleanup pass means the raw value already existed
somewhere durable, which is the thing being prevented.

## Consequences

**Gained.** "An Approver approved this at this time" stops being a claim and becomes an artifact.
Integrity is enforced by Azure rather than by our restraint. The export needed to answer *"show me
the proof"* becomes possible, because there is finally something to export.

**Accepted.** A locked retention policy makes data genuinely undeletable for its term — including
data written by mistake. That is the point, and it is also a real operational cost: the redactor
in decision 5 is what keeps that cost from becoming a liability. Non-production stays unlocked.

**Refused.** Reusing OpenTelemetry as the audit trail. It is sampled, off by default, retained 30
days, and deliberately excludes the approver's identity. Bending it into evidence would make both
jobs worse.

**What would revisit this.** A first-party audit-trail service for Foundry agent actions. Today the
platform ships the *storage* primitives (WORM, ledger) and no opinion about *what an agent action
event contains* — that opinion is the part this ADR keeps.

**Sources:**
[Immutable storage overview](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview) ·
[Container-level WORM policies](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-container-level-worm-policies) ·
[About Azure confidential ledger](https://learn.microsoft.com/en-us/azure/confidential-ledger/overview)
