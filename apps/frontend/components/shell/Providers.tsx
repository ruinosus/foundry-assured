"use client";

// Root client providers. Hoists MSAL to the whole app so the Entra redirect is
// handled on whatever page the user lands on after login (the redirect URI is the
// origin, "/", which is the Overview — it has no chat but must still consume the
// auth response). The token-acquisition gate stays in the chat (HelpdeskApp).
//
// When Entra isn't configured, this is a pass-through. The first-render output is
// identical on server and client (children when unauth'd, a loader when auth'd),
// so there's no hydration mismatch; msalInstance is null during SSR by design.

import { MsalProvider } from "@azure/msal-react";
import { useEffect, useState } from "react";
import { authConfigured, msalInstance } from "@/lib/auth/msal";

const loader: React.CSSProperties = {
  display: "flex",
  height: "100vh",
  alignItems: "center",
  justifyContent: "center",
  fontFamily: "system-ui",
  color: "#64748b",
};

export function Providers({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (msalInstance) {
      msalInstance.initialize().then(() => setReady(true)).catch(() => setReady(true));
    } else {
      setReady(true);
    }
  }, []);

  // No Entra configured → render directly (stable across SSR/CSR).
  if (!authConfigured) return <>{children}</>;
  // Configured but MSAL not yet initialized (also the SSR state) → brief splash.
  if (!ready || !msalInstance) return <div style={loader}>Loading…</div>;
  return <MsalProvider instance={msalInstance}>{children}</MsalProvider>;
}
