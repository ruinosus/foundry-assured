import Link from "next/link";
import { AppShell } from "@/components/shell/AppShell";
import { DOMAINS } from "@/lib/domains";

// Public landing — self-explanatory for anyone who opens the repo. Tells the story
// (Foundry showcase + the assurance mechanism), then offers the domains as role-cards
// (config-driven from the registry) and the three guarantees the mechanism enforces.

const GUARANTEES = [
  {
    icon: "🏗️",
    title: "Construída com fidelidade",
    body: "A base de conhecimento é gerada do código real e bloqueada por um gate: ≥80% das citações têm que resolver para um arquivo que existe.",
  },
  {
    icon: "🔒",
    title: "Acesso que segue a fonte",
    body: "A recuperação é aparada por documento pelos grupos de leitura da origem — sem classificação no código, à prova de injeção.",
  },
  {
    icon: "✓",
    title: "Continuamente avaliada",
    body: "Toda resposta cita a fonte ou declina. Gate determinístico no CI + juízes de groundedness do Foundry, ligados aos traces.",
  },
];

export default function Page() {
  return (
    <AppShell>
      <section className="hero">
        <h1>Um mecanismo de garantia sobre o Microsoft Foundry.</h1>
        <p>
          Aponte para um repositório ou base de conhecimento e ganhe três garantias: a KB é
          construída da melhor forma, o agente responde com citações fundamentadas, e o
          acesso é seguro por documento. O domínio é trocável — aqui estão três.
        </p>
        <div className="hero-cta">
          <Link href={`/d/${DOMAINS[0].id}`} className="btn btn-primary">
            💬 Abrir um agente
          </Link>
          <Link href="/evals" className="btn btn-ghost">
            ✓ Ver avaliações
          </Link>
        </div>
      </section>

      <div className="section-title">Agentes</div>
      <div className="grid">
        {DOMAINS.map((d) => (
          <Link key={d.id} href={`/d/${d.id}`} className="card domain-card">
            <div className="domain-card-head">
              <span className="domain-card-icon" aria-hidden>
                {d.icon}
              </span>
              <h3>{d.label}</h3>
            </div>
            <p>{d.blurb}</p>
            <span className={`tag ${d.kind === "workflow" ? "tag-neutral" : ""}`}>
              {d.kind === "workflow" ? "workflow + aprovação humana" : "Q&A fundamentado"}
            </span>
          </Link>
        ))}
      </div>

      <div className="section-title">Garantias</div>
      <div className="grid">
        {GUARANTEES.map((g) => (
          <div key={g.title} className="card">
            <div className="domain-card-head">
              <span className="domain-card-icon" aria-hidden>
                {g.icon}
              </span>
              <h3>{g.title}</h3>
            </div>
            <p>{g.body}</p>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
