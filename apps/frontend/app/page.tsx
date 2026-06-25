import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";

const PILLARS = [
  {
    title: "Knowledge base",
    body: "Foundry IQ agentic retrieval over the runbook corpus — answers cite their source or decline.",
    tag: "Phase 1",
  },
  {
    title: "Multi-agent workflow",
    body: "triage → retrieve → resolve → escalate, streamed step-by-step to the UI over AG-UI.",
    tag: "Phase 2",
  },
  {
    title: "Memory + Entra OBO",
    body: "Per-user memory, called on-behalf-of the signed-in developer via delegated tokens.",
    tag: "Phase 3",
  },
  {
    title: "Human-in-the-loop",
    body: "Ticket escalation pauses for explicit approval before create_ticket ever fires.",
    tag: "Phase 4",
  },
  {
    title: "Evaluation",
    body: "Deterministic policy gate + Foundry groundedness/relevance/coherence judges, linked to the portal.",
    tag: "Phase 5",
  },
];

export default function Page() {
  return (
    <AppShell>
      <section className="hero">
        <h1>Microsoft Foundry, end to end.</h1>
        <p>
          An internal engineering support concierge that triages, grounds answers in
          runbooks, remembers the developer, escalates with human approval — and is
          continuously evaluated. Every Foundry pillar, validated hands-on.
        </p>
        <div className="hero-cta">
          <Link href="/chat" className="btn btn-primary">
            💬 Open the concierge
          </Link>
          <Link href="/evals" className="btn btn-ghost">
            ✓ View evaluations
          </Link>
        </div>
      </section>

      <div className="section-title">Capabilities</div>
      <div className="grid">
        {PILLARS.map((p) => (
          <div key={p.title} className="card">
            <h3>{p.title}</h3>
            <p>{p.body}</p>
            <span className="tag">{p.tag} · green</span>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
