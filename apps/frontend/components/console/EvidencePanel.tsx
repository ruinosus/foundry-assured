"use client";

// EvidencePanel — the signature of the Assurance Console, and the on-thesis primitive:
// in enterprise RAG, *the citation is the interesting object, not the summary — trust
// routes through the link*. So we surface, beside every answer, the sources it grounded
// in plus the assurance guarantees the mechanism enforces.
//
// v1 derives sources from the answer TEXT (the prompts already make the agent cite real
// file paths + component/document names). It degrades gracefully when nothing is cited.
// It can later be upgraded to read the raw retrieval context off the AG-UI stream.

import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";
import type { Domain } from "@/lib/domains";

interface Source {
  label: string;
  kind: "file" | "component";
}

// File paths (app/…, infra/…, docs/…) and bare code filenames, plus the bundle/component
// identifiers the grounded prompts cite (cockpit-*, foundry-helpdesk-*).
const FILE_RE =
  /\b(?:app|apps|infra|docs|eval|lib|components|frontend|backend)\/[\w./-]+\.(?:py|tsx?|bicep|md|ya?ml|json|css|sh)\b|\b[\w-]+\.(?:py|tsx?|bicep)\b/g;
const COMPONENT_RE = /\b(?:cockpit-[a-z0-9-]+|foundry-helpdesk-[a-z]+)\b/g;

function extractSources(text: string): Source[] {
  const seen = new Set<string>();
  const out: Source[] = [];
  const add = (label: string, kind: Source["kind"]) => {
    const key = label.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ label, kind });
  };
  for (const m of text.matchAll(FILE_RE)) add(m[0].replace(/^\.\//, ""), "file");
  for (const m of text.matchAll(COMPONENT_RE)) add(m[0], "component");
  return out.slice(0, 10);
}

const GUARANTEES = [
  {
    icon: "✓",
    title: "Fidelidade",
    body: "A wiki foi gerada do código real; ≥80% das citações resolvem para um arquivo existente (gate de build).",
  },
  {
    icon: "✓",
    title: "Acesso",
    body: "Recuperação aparada por documento — o acesso segue a fonte (groups), à prova de injeção.",
  },
  {
    icon: "✓",
    title: "Avaliação",
    body: "Toda resposta cita a fonte ou declina; gate determinístico + juízes de groundedness.",
  },
];

export function EvidencePanel({ domain }: { domain: Domain }) {
  const { agent } = useAgent({ agentId: domain.id });
  const [sources, setSources] = useState<Source[]>([]);

  useEffect(() => {
    if (!agent) return;
    const refresh = () => {
      const msgs = agent.messages ?? [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const lastAssistant = [...msgs].reverse().find((m: any) => m.role === "assistant" && m.content);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setSources(lastAssistant ? extractSources((lastAssistant as any).content) : []);
    };
    refresh();
    const sub = agent.subscribe({
      onMessagesChanged: refresh,
      onRunFinalized: refresh,
    });
    return () => sub.unsubscribe();
  }, [agent]);

  return (
    <aside className="evidence">
      <div className="evidence-section">
        <div className="evidence-title">Fontes</div>
        {sources.length > 0 ? (
          <div className="evidence-sources">
            {sources.map((s) => (
              <span key={s.label} className={`source-chip ${s.kind}`} title={`Fonte ${s.kind === "file" ? "(arquivo)" : "(componente)"}`}>
                <span className="source-ico" aria-hidden>
                  {s.kind === "file" ? "📄" : "📦"}
                </span>
                {s.label}
              </span>
            ))}
          </div>
        ) : (
          <p className="evidence-empty muted">
            As fontes que a resposta citar aparecem aqui — cada afirmação fundamentada na
            base, não em suposição.
          </p>
        )}
      </div>

      <div className="evidence-section">
        <div className="evidence-title">Garantias</div>
        <ul className="evidence-guarantees">
          {GUARANTEES.map((g) => (
            <li key={g.title}>
              <span className="guarantee-icon" aria-hidden>
                {g.icon}
              </span>
              <div>
                <b>{g.title}</b>
                <p className="muted">{g.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
