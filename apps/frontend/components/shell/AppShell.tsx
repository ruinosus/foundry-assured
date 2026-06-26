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

const NAV = [
  { href: "/", label: "Overview", icon: "▦" },
  { href: "/chat", label: branding.assistant, icon: "💬" },
  { href: "/cockpit", label: "Cockpit expert", icon: "🛰️" },
  { href: "/tickets", label: "Tickets", icon: "🎫" },
  { href: "/evals", label: "Evaluations", icon: "✓" },
];

const TITLES: Record<string, string> = {
  "/": "Overview",
  "/chat": branding.assistant,
  "/cockpit": "Cockpit expert",
  "/tickets": "Tickets",
  "/evals": "Evaluations",
};

function BackendStatus() {
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
  const label = ok === null ? "checking…" : ok ? "backend online" : "backend offline";
  return (
    <div className="sidebar-foot">
      <span className={`dot ${cls}`} /> {label}
    </div>
  );
}

// Account chip + sign in/out. Only rendered when Entra is configured (so MsalProvider
// exists), so the MSAL hooks are always inside a provider.
function AccountChip() {
  const { instance, accounts } = useMsal();
  const isAuthenticated = useIsAuthenticated();

  if (!isAuthenticated) {
    return (
      <button className="acct-btn" onClick={() => instance.loginRedirect({ scopes: apiScopes })}>
        Sign in with Microsoft
      </button>
    );
  }

  const account = accounts[0];
  const name = account?.name || account?.username || "Signed in";
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
        Sign out
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
  const pathname = usePathname() || "/";
  const title = TITLES[pathname] ?? "";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">⚡</span>
          <span>
            {branding.product}
            <small>{branding.tagline}</small>
          </span>
        </div>

        <div className="nav-section">Workspace</div>
        {NAV.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={`nav-item ${active ? "active" : ""}`}>
              <span className="ico">{item.icon}</span>
              {item.label}
            </Link>
          );
        })}

        <div className="sidebar-foot-group">
          {authConfigured && <AccountChip />}
          <BackendStatus />
        </div>
      </aside>

      <div className="content">
        <header className="topbar">
          <nav className="crumbs">
            <Link href="/">Home</Link>
            {title && title !== "Overview" && (
              <>
                <span className="sep">/</span>
                <b>{title}</b>
              </>
            )}
          </nav>
        </header>
        <main className={`page${flush ? " flush" : ""}`}>{children}</main>
      </div>
    </div>
  );
}
