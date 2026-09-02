# ADR-035 — Machine verification is recorded in the bundle; human sign-off is not

- **Status:** Accepted
- **Date:** 2026-09-02
- **Context:** [`apps/backend/app/modules/knowledge/internal/wiki_builder.py`](../../apps/backend/app/modules/knowledge/internal/wiki_builder.py)
  (`render_page`, `stamp_verified`), [`apps/backend/tests/foundry/provenance_okf_test.py`](../../apps/backend/tests/foundry/provenance_okf_test.py),
  [`apps/backend/eval/assurance.yaml`](../../apps/backend/eval/assurance.yaml)
- **Related:** [ADR-023](./ADR-023-evidence-layer.md) — the HITL approval evidence layer,
  where human sign-off is recorded and stays recorded; this ADR does not amend it

## Context

OKF v0.2 §5.2 makes `generated` and `verified` first-class frontmatter keys: `generated`
names the producer of a page, `verified` is a list of independent verification events, and
their absence or presence is what a consumer derives a trust tier from (`SPEC.md:401-407`).
Before this pair of tasks, `wiki_builder.py`'s verifier pass re-grounded a page's claims and
rewrote it in place, leaving only a run log line (`" (verificada)"`) — no trace survived in
the artifact itself. A page that had been through the second model pass was
indistinguishable from one that had not, to any OKF consumer. That is audit gap G3.

The gap was going to close one way or another regardless of what this repository decided.
The external generator this repository builds on already writes machine `verified` events
into `openwiki/` on its own: `synchronizeClaimsVerification` in
`src/okf/claims-verification.ts:26-28` (clone `64903f9`) reconciles OpenWiki-owned OKF
verification events into page frontmatter as a matter of course, retaining human, process,
and other producer events alongside them. Declining to record our own verifier's pass would
not have kept `verified` out of the pipeline — it would only have kept our pass invisible
next to one the upstream tool already records.

## Decision

Machine verification performed by this repository's own pipeline is recorded in concept
frontmatter as a `process:<name>/<version>` actor — concretely, `stamp_verified` appends
`process:wiki-verifier/<model deployment>` to the page's `verified` list
(`wiki_builder.py:129-141`). It appends rather than replaces, because `verified` is a list
of independent events (`SPEC.md:388-391`), and a `--no-verify` run emits no `verified` key
at all rather than an empty list — absence stays meaningful.

Human sign-off is out of scope of this decision and stays exactly where it already is: the
HITL approval evidence layer of ADR-023. Nothing here creates, moves, or duplicates that
record.

## Rationale

There are two threat models here, and only one of them is a document problem.

**Client-supplied `verified` is self-attestation by a party we do not control.** That is the
case `provenance_okf_test.py:21-23` refuses, and it refuses it structurally: even if the
screen sends a `verified` value, the backend never trusts it — identity is stamped with
`actor()`, not read off the request. The docstring names the risk precisely: *"a identidade
não vem do documento: mesmo que a tela mande um `verified`, quem decide é `actor()`. Um
documento que pudesse declarar quem o verificou seria um documento capaz de forjar a própria
revisão."* A document that could declare its own reviewer would be a document that could
forge its own review — and the subject of that sentence is the screen, an untrusted client
in the loop between a person and the record.

**A server-side record that our own verifier ran is our tool's own output**, with no client
in the loop to forge anything. There is nothing to attest to beyond "this pipeline executed
this pass" — a fact the pipeline itself is the sole source of, the same way `generated`
already records which producer wrote a page. What that record is worth is not a question of
trust in an external claim; it is a question of how good the pass is, and that question
already has an answer: the fidelity gate that runs over the bundle
(`eval/assurance.yaml:20`, `build.fidelity_min: 0.80`). A `verified` event from
`wiki-verifier` is worth exactly what that floor is worth, and no more.

Nothing about this decision changes the first case. Approval identity for HITL actions
continues to come from `actor()`, never from a document, and no screen gains the ability to
assert its own review.

## Consequences

- OKF consumers derive `machine-confirmed` rather than `unverified` (`SPEC.md:405`) for
  pages that went through the verifier pass; a `--no-verify` run stays `unverified` because
  it carries no `verified` key at all.
- No trust field is read for any authorization decision (`SPEC.md:410`), and none may become
  one. The access path stays `groups:` → `permissionFilter` (ADR-031), untouched by this
  decision.
- ADR-023 is unamended: human approval evidence keeps living in the append-only event stream
  it already lives in, not in document frontmatter.
- A future client-supplied verification claim — from a screen, an API caller, or any party
  outside this pipeline — is still refused by the same reasoning `provenance_okf_test.py`
  encodes today. This ADR narrows nothing already decided there.
