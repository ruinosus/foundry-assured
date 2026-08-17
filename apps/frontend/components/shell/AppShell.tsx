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
import { DOMAINS } from "@/lib/domains";
import { authedFetch } from "@/lib/auth/api";
import { useMyRoles, isAdmin } from "@/lib/auth/roles";
import { useTranslations } from "next-intl";
import { LanguageToggle } from "@/components/shell/LanguageToggle";
import { ThemeToggle } from "@/components/shell/ThemeToggle";
import { ChatDock } from "@/components/shell/ChatDock";
import { ChatDockProvider, useChatDock } from "@/lib/chat-dock";

// The domain agents are config-driven from the registry → /d/<id>. Workspace pages are
// static. Two sections so the sidebar reads as "tools" + "agents".
//
// Os rótulos saem do dicionário; as listas guardam só o que NÃO é texto (rota e ícone). Antes o
// nome vivia aqui como constante, o que tornava a navegação intraduzível por construção.
const WORKSPACE_NAV = [
  { href: "/", key: "overview", icon: "▦" },
  { href: "/usecases", key: "usecases", icon: "◎" },
  { href: "/agents", key: "agents", icon: "◆" },
  { href: "/knowledge", key: "knowledge", icon: "▤" },
  { href: "/skills", key: "skills", icon: "✦" },
  { href: "/tickets", key: "tickets", icon: "🎫" },
  { href: "/evals", key: "evals", icon: "✓" },
];

const ADMIN_NAV = [
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

/** O chat lateral e o botão que o alterna. O token é adquirido aqui pelo mesmo caminho do
 *  console: silencioso, com refresh antes da expiração de ~1h. Sem auth configurada não há token
 *  e o chat sobe sem Authorization — que é o modo local. */
function DockHost() {
  const { open, toggle } = useChatDock();
  const t = useTranslations("chatDock");
  const { instance, accounts } = useMsal();
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    if (!authConfigured || !accounts[0]) return;
    let alive = true;
    const acquire = () =>
      instance
        .acquireTokenSilent({ scopes: apiScopes, account: accounts[0] })
        .then((r) => alive && setToken(r.accessToken))
        .catch(() => {});
    void acquire();
    const id = setInterval(acquire, 4 * 60 * 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [instance, accounts]);

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
      <ChatDock authorization={token ? `Bearer ${token}` : undefined} />
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

  // Construídos no componente, não no módulo: rótulo é texto, e texto depende do idioma
  // escolhido — uma constante avaliada no import nasce numa língua só e nunca mais muda.
  const agentNav = DOMAINS.map((d) => ({
    href: `/d/${d.id}`,
    label: td(`${d.id}.label`),
    icon: d.icon,
  }));
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
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">⚡</span>
          <span>
            {branding.product}
            <small>{tb("tagline")}</small>
          </span>
        </div>

        {[
          { section: t("workspace"), items: workspace },
          { section: t("aiAgents"), items: agentNav },
        ].map(({ section, items }) => (
          <div key={section}>
            <div className="nav-section">{section}</div>
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
                  {"key" in item ? t(item.key as string) : item.label}
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
    </ChatDockProvider>
  );
}
