"use client";

// Market-standard app shell: fixed left sidebar with nav + a topbar with
// breadcrumbs, wrapping each route's content. Active state and breadcrumbs are
// derived from the current path.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { apiScopes, authConfigured } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";
import { CHAT_DOMAINS, DOMAINS } from "@/lib/domains";
import { authedFetch } from "@/lib/auth/api";
import { useMyRoles, isAdmin } from "@/lib/auth/roles";
import { useTranslations } from "next-intl";
import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { ChatDock } from "@/components/shell/ChatDock";
import { DockProvider } from "@/components/shell/DockProvider";
import { useApiToken } from "@/lib/auth/useApiToken";
import { ChatDockProvider, useChatDock } from "@/lib/chat-dock";

// The domain agents are config-driven from the registry → /d/<id>. Workspace pages are
// static. Two sections so the sidebar reads as "tools" + "agents".
//
// Os rótulos saem do dicionário; as listas guardam só o que NÃO é texto (rota e ícone). Antes o
// nome vivia aqui como constante, o que tornava a navegação intraduzível por construção.
// Casos de uso ABRE a lista: o público é de negócio, e "que problema isto resolve" é a pergunta
// que essa pessoa faz primeiro. Visão geral desce — ela é resumo de sistema, não porta de entrada.
const WORKSPACE_NAV = [
  { href: "/usecases", key: "usecases", icon: "◎" },
  // UM item para os assistentes, não seis. Os seis viraram o seletor no topo do console — mas
  // sem esta linha não haveria caminho até uma conversa a partir das telas de gestão, e o
  // redesenho teria escondido o produto.
  { href: `/d/${CHAT_DOMAINS[0].id}`, key: "assistants", icon: "💬" },
  { href: "/agents", key: "agents", icon: "◆" },
  { href: "/knowledge", key: "knowledge", icon: "▤" },
  { href: "/skills", key: "skills", icon: "✦" },
  { href: "/tickets", key: "tickets", icon: "🎫" },
  { href: "/evals", key: "evals", icon: "✓" },
  { href: "/", key: "overview", icon: "▦" },
];

const ADMIN_NAV = [
  { href: "/audit", key: "audit", icon: "🔗" },
  { href: "/admin/users", key: "admin", icon: "🛡️" },
  { href: "/admin/connections", key: "connections", icon: "🔌" },
];

// O título da barra superior repetia o rótulo da navegação numa tabela paralela — e em três
// línguas ao mesmo tempo ("Overview", "Agentes", "Tickets"). Agora deriva das mesmas chaves,
// então nav e título não podem mais divergir.
const TITLE_KEYS: Record<string, string> = {
  "/": "overview",
  "/usecases": "usecases",
  "/agents": "agents",
  "/knowledge": "knowledge",
  "/skills": "skills",
  "/tickets": "tickets",
  "/evals": "evals",
  "/admin/users": "admin",
  "/admin/connections": "connections",
};

function ProjectBadge() {
  const t = useTranslations("common");
  const [project, setProject] = useState<{ name: string | null } | null>(null);
  useEffect(() => {
    let alive = true;
    authedFetch("/api/foundry/project")
      .then((r) => r.json())
      .then((d) => alive && setProject(d))
      .catch(() => alive && setProject(null));
    return () => {
      alive = false;
    };
  }, []);

  // Sem project resolvido não há o que mostrar — e um rótulo vazio seria pior que nenhum.
  if (!project?.name) return null;
  return (
    <div className="project-badge" title={t("projectHint")}>
      <span className="project-label">{t("project")}</span>
      <span className="project-name">{project.name}</span>
    </div>
  );
}

/** O chat lateral e o botão que o alterna. O token NÃO é adquirido aqui desde que o provider do
 *  CopilotKit subiu para o shell (`DockProvider`): quem carrega `Authorization` é o provider, e
 *  ele está acima deste componente. Ver `lib/auth/useApiToken`. */
function DockHost() {
  const { open, toggle } = useChatDock();
  const t = useTranslations("chatDock");

  return (
    <>
      <button
        type="button"
        className={`dock-toggle${open ? " on" : ""}`}
        onClick={toggle}
        aria-expanded={open}
        title={open ? t("close") : t("open")}
      >
        <span aria-hidden>💬</span>
        <span className="sr-only">{open ? t("close") : t("open")}</span>
      </button>
      <ChatDock />
    </>
  );
}

function BackendStatus() {
  const t = useTranslations("common");
  const [ok, setOk] = useState<boolean | null>(null);
  useEffect(() => {
    let alive = true;
    fetch("/api/health")
      .then((r) => alive && setOk(r.ok))
      .catch(() => alive && setOk(false));
    return () => {
      alive = false;
    };
  }, []);
  const cls = ok === null ? "" : ok ? "ok" : "bad";
  const label =
    ok === null ? t("checking") : ok ? t("backendOnline") : t("backendOffline");
  return (
    <div className="sidebar-foot">
      <span className={`dot ${cls}`} /> {label}
    </div>
  );
}

// Account chip + sign in/out. Only rendered when Entra is configured (so MsalProvider
// exists), so the MSAL hooks are always inside a provider.
function AccountChip() {
  const tc = useTranslations("common");
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();

  if (!isAuthenticated) {
    return (
      <button className="acct-btn" onClick={() => instance.loginRedirect({ scopes: apiScopes })}>
        {tc("signIn")}
      </button>
    );
  }

  const account = accounts[0];
  const name = account?.name || account?.username || tc("signedIn");
  return (
    <div className="acct">
      <div className="acct-id" title={account?.username}>
        <span className="acct-avatar">{(name[0] || "?").toUpperCase()}</span>
        <div className="acct-meta">
          <div className="acct-name">{name}</div>
          {account?.username && <div className="acct-mail">{account.username}</div>}
        </div>
      </div>
      <button className="acct-btn" onClick={() => instance.logoutRedirect()}>
        {tc("signOut")}
      </button>
    </div>
  );
}

export function AppShell({
  children,
  flush,
}: {
  children: React.ReactNode;
  flush?: boolean;
}) {
  const t = useTranslations("nav");
  const td = useTranslations("domains");
  const tc = useTranslations("common");
  const tb = useTranslations("branding");
  const pathname = usePathname() || "/";
  const roles = useMyRoles();
  const apiToken = useApiToken();

  // Construídos no componente, não no módulo: rótulo é texto, e texto depende do idioma
  // escolhido — uma constante avaliada no import nasce numa língua só e nunca mais muda.
  const domainTitle = DOMAINS.find((d) => pathname.startsWith(`/d/${d.id}`));
  const title = domainTitle
    ? td(`${domainTitle.id}.label`)
    : TITLE_KEYS[pathname]
      ? t(TITLE_KEYS[pathname])
      : "";
  // Show Admin in the nav only to Admins (the page + every endpoint re-check server-side).
  const workspace = isAdmin(roles) ? [...WORKSPACE_NAV, ...ADMIN_NAV] : WORKSPACE_NAV;

  return (
    <ChatDockProvider>
    {/* O provider do CopilotKit envolve o dock E o conteúdo: é o que permite a uma tela
        registrar uma tool que o agente do dock consegue chamar. Ver DockProvider. */}
    <DockProvider authorization={apiToken ? `Bearer ${apiToken}` : undefined}>
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">⚡</span>
          <span>
            {branding.product}
            <small>{tb("tagline")}</small>
          </span>
        </div>

        {/* UMA lista, sem rótulo de grupo. Antes eram duas — "Workspace" e "Exemplos do
            produto" —, 14 links no total, misturando ONDE SE CONFIGURA com ONDE SE USA. Os
            assistentes viraram o seletor no topo do console: trocar de assistente é ação de
            dentro da conversa, não navegação de aplicação. E o rótulo "Exemplos do produto"
            dizia ao usuário que aqueles assistentes eram demonstração. */}
        {[{ section: "", items: workspace }].map(({ section, items }) => (
          <div key={section || "nav"}>
            {items.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`nav-item ${active ? "active" : ""}`}
                >
                  <span className="ico">{item.icon}</span>
                  {t(item.key)}
                </Link>
              );
            })}
          </div>
        ))}

        <div className="sidebar-foot-group">
          {authConfigured && <AccountChip />}
          <BackendStatus />
          <ThemeToggle />
          <LanguageToggle />
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <nav className="crumbs">
            <Link href="/">{t("overview")}</Link>
            {title && pathname !== "/" && (
              <>
                <span className="sep">/</span>
                <b>{title}</b>
              </>
            )}
          </nav>
          <DockHost />
        </header>
        <main className={`page${flush ? " flush" : ""}`}>{children}</main>
      </div>
    </div>
    </DockProvider>
    </ChatDockProvider>
  );
}
