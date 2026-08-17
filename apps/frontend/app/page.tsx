import Link from "next/link";
import { useTranslations } from "next-intl";
import { AppShell } from "@/components/shell/AppShell";
import { DOMAINS } from "@/lib/domains";

// Public landing — self-explanatory for anyone who opens the repo. Tells the story
// (Foundry showcase + the assurance mechanism), then offers the domains as role-cards
// (config-driven from the registry) and the three guarantees the mechanism enforces.

// Só o ícone e a chave: o texto de cada garantia vem do dicionário. Um array de dados é
// exatamente onde a tradução costuma passar batido — não é texto entre tags, então nenhum
// grep de JSX o encontra, e a tela fica numa língua só sem ninguém notar.
const GUARANTEES = [
  { icon: "🏗️", key: "g1" },
  { icon: "🔒", key: "g2" },
  { icon: "✓", key: "g3" },
] as const;

export default function Page() {
  const t = useTranslations("overview");
  const td = useTranslations("domains");
  return (
    <AppShell>
      <section className="hero">
        <h1>{t("tagline")}</h1>
        <p>{t("lede")}</p>
        <div className="hero-cta">
          <Link href={`/d/${DOMAINS[0].id}`} className="btn btn-primary">
            <span aria-hidden>💬</span> {t("ctaOpen")}
          </Link>
          <Link href="/evals" className="btn btn-ghost">
            <span aria-hidden>✓</span> {t("ctaEvals")}
          </Link>
        </div>
      </section>

      <div className="section-title">{t("agents")}</div>
      <div className="grid">
        {DOMAINS.map((d) => (
          <Link key={d.id} href={`/d/${d.id}`} className="card domain-card">
            <div className="domain-card-head">
              <span className="domain-card-icon" aria-hidden>
                {d.icon}
              </span>
              <h3>{td(`${d.id}.label`)}</h3>
            </div>
            <p>{td(`${d.id}.blurb`)}</p>
            <span className={`tag ${d.kind === "workflow" ? "tag-neutral" : ""}`}>
              {t(d.kind === "workflow" ? "kindWorkflow" : "kindGrounded")}
            </span>
          </Link>
        ))}
      </div>

      <div className="section-title">{t("guarantees")}</div>
      <div className="grid">
        {GUARANTEES.map((g) => (
          <div key={g.key} className="card">
            <div className="domain-card-head">
              <span className="domain-card-icon" aria-hidden>
                {g.icon}
              </span>
              <h3>{t(`${g.key}Title`)}</h3>
            </div>
            <p>{t(`${g.key}Body`)}</p>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
