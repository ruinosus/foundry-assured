# SPIKE — DNA vs agent-framework (decision, NOT for merge)

Adversarial decision spike. Same agent (the grounded helpdesk concierge:
persona + citation guardrail), implemented **both ways**, compared by evidence.
Steelmans the competitor. Verdict + `comparison.html` are the deliverable.

## Layout

    af_native/                     (A) the cleanest agent-framework path
      concierge-grounded.agent.yaml    PromptAgent YAML (declarative, native AF)
      concierge-ungrounded.agent.yaml  sibling — note the DUPLICATED persona line
    dna_side/                      (B) points at apps/backend/.dna/helpdesk (real)
    emitter/
      dna_to_af.py                 (C) DE-PARA: DNA definition -> AF PromptAgent YAML
    compare.py                     runs A + B + C and proves the emitter round-trips

## Run

    DOTNET_ROLL_FORWARD=Major \
    AZURE_OPENAI_ENDPOINT="https://spike.invalid/" \
    AZURE_OPENAI_API_KEY="sk-spike-dummy" \
    <backend .venv>/bin/python spike/compare.py

- `DOTNET_ROLL_FORWARD=Major` — agent-framework-declarative loads .NET 8 at import
  (via pythonnet + powerfx); this box has .NET 9, so roll-forward lets it run.
- The dummy Azure env only lets AF construct its chat client offline — no network
  call is made; we assert on the composed agent object + instructions, not a live
  completion (that would need real creds on BOTH sides, so it is out of scope and
  equal for both).

## What the run proves

1. AF-native declarative works and is genuinely clean for a single agent.
2. DNA composes Soul + Guardrail + delta (the real backend scope).
3. The DNA->AF emitter materializes the exact PromptAgent YAML AF consumes, and
   the emitted `instructions` are **byte-equal** to the DNA-composed prompt.

See `comparison.html` for the per-axis scorecard and the verdict.
