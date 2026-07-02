"use client";

// EvidencePanel — the signature of the Assurance Console, and the on-thesis primitive:
// in enterprise RAG, *the citation is the interesting object, not the summary — trust
// routes through the link*. So we surface, beside every answer, the sources it grounded
// in plus the assurance guarantees the mechanism enforces.
//
// v2 (grounded domains): reads STRUCTURED citations off the AG-UI stream. The backend
// (app/services/grounded.py) runs the Responses API with the KB as an inline MCP tool and
// emits the url_citation annotations as a CUSTOM `sources` event {index, source, url}. We
// subscribe to it via agent.subscribe (the same onEvent/CUSTOM pattern TicketApproval uses).
// When no structured citations arrive (older/hosted paths), we fall back to the v1 heuristic
// that derives sources from the answer TEXT, so the panel degrades gracefully.

import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";
import type { Domain } from "@/lib/domains";

// A structured citation from the grounded stream (the CUSTOM `sources` event).
interface Citation {
  index: number;
  source: string; // the document filename (e.g. cockpit-mcp-server-v1.4.0__page-1.md)
  url?: string; // the source URL (private blob — can't be opened directly; kept for reference)
  content?: string; // the retrieved snippet — shown INLINE on click (the storage is private by design)
}

// A heuristic source (v1 fallback) derived from the answer text.
interface TextSource {
  label: string;
  kind: "file" | "component";
}

// File paths (app/…, infra/…, docs/…) and bare code filenames, plus the bundle/component
// identifiers the grounded prompts cite (cockpit-*, foundry-helpdesk-*).
const FILE_RE =
  /\b(?:app|apps|infra|docs|eval|lib|components|frontend|backend)\/[\w./-]+\.(?:py|tsx?|bicep|md|ya?ml|json|css|sh)\b|\b[\w-]+\.(?:py|tsx?|bicep)\b/g;
const COMPONENT_RE = /\b(?:cockpit-[a-z0-9-]+|foundry-helpdesk-[a-z]+)\b/g;

function extractTextSources(text: string): TextSource[] {
  const seen = new Set<string>();
  const out: TextSource[] = [];
  const add = (label: string, kind: TextSource["kind"]) => {
    const key = label.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ label, kind });
  };
  for (const m of text.matchAll(FILE_RE)) add(m[0].replace(/^\.\//, ""), "file");
  for (const m of text.matchAll(COMPONENT_RE)) add(m[0], "component");
  return out;
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
  // Structured citations (grounded stream) take precedence; text-derived sources are the fallback.
  const [citations, setCitations] = useState<Citation[]>([]);
  const [textSources, setTextSources] = useState<TextSource[]>([]);
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  useEffect(() => {
    if (!agent) return;
    const refreshFallback = () => {
      const msgs = agent.messages ?? [];
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const lastAssistant = [...msgs].reverse().find((m: any) => m.role === "assistant" && m.content);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setTextSources(lastAssistant ? extractTextSources((lastAssistant as any).content) : []);
    };
    refreshFallback();
    const sub = agent.subscribe({
      // The AG-UI CUSTOM `sources` event carries the structured citations. RUN_STARTED clears the
      // previous answer's citations so the panel tracks the current turn. (onEvent fires for every
      // event — same pattern as components/chat/TicketApproval.tsx.)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEvent: ({ event }: any) => {
        if (event?.type === "RUN_STARTED") {
          setCitations([]);
          setOpenIdx(null);
        } else if (event?.type === "CUSTOM" && event?.name === "sources") {
          const value = (event.value ?? []) as Citation[];
          setCitations(
            value.map((v) => ({ index: v.index, source: v.source, url: v.url, content: v.content })),
          );
        }
      },
      onMessagesChanged: refreshFallback,
      onRunFinalized: refreshFallback,
    });
    return () => sub.unsubscribe();
  }, [agent]);

  const count = citations.length || textSources.length;

  return (
    <aside className="evidence">
      <div className="evidence-section">
        <div className="evidence-title">Fontes{count > 0 ? ` (${count})` : ""}</div>

        {citations.length > 0 ? (
          // Structured, numbered, clickable citations — click reveals the source (path + link).
          // Blob URLs are private storage, so opening may prompt auth; the identity + link is the
          // reliable v1 (inline document content is a later enhancement — see the grounded spec).
          <ol className="evidence-citations">
            {citations.map((c) => (
              <li key={c.index} className="citation">
                <button
                  type="button"
                  className="citation-btn"
                  aria-expanded={openIdx === c.index}
                  onClick={() => setOpenIdx(openIdx === c.index ? null : c.index)}
                  title="Clique para ver a fonte"
                >
                  <span className="citation-idx" aria-hidden>
                    {c.index}
                  </span>
                  <span className="citation-src">{c.source}</span>
                </button>
                {openIdx === c.index && (
                  <div className="citation-detail">
                    {c.content ? (
                      // Show the retrieved snippet inline — the blob is private (can't be opened).
                      <p className="citation-content">{c.content}</p>
                    ) : (
                      <span className="muted">
                        {c.source} — documento interno (recuperação segura; sem prévia)
                      </span>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ol>
        ) : textSources.length > 0 ? (
          <div className="evidence-sources">
            {textSources.map((s) => (
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
