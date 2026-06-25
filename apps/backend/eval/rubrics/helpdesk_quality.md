# Rubric: helpdesk answer quality

The cloud-side quality bar for the Helpdesk Concierge, scored by Microsoft
Foundry's hosted LLM-as-judge evaluators (`FoundryEvals`) over the golden set.
These are the Foundry evaluator dimensions the harness runs (`eval/run_eval.py
--cloud`), mapped to what they mean for this app:

| Dimension (Foundry evaluator) | What it judges here | Bar |
| --- | --- | --- |
| **groundedness** | Is every claim supported by the retrieved runbook context? No invented steps. | high — this is the core promise |
| **relevance** | Does the answer actually address the developer's question? | high |
| **coherence** | Is the answer well-structured and readable? | medium |

Groundedness is the one that matters most: the concierge must answer **from the
runbooks** and cite them, or decline. The deterministic citation/secret policies
in `eval/assertions.py` are the hard CI gate; these rubric scores are the
graded quality signal, viewable per-run in the Foundry portal.

> Foundry evaluator names are verified against the installed `agent_framework`
> (`FoundryEvals.GROUNDEDNESS == "groundedness"`, etc.). The catalogue also
> offers relevance, fluency, similarity, response_completeness and safety
> evaluators (violence/sexual/self_harm/hate_unfairness) if we want to widen it.
