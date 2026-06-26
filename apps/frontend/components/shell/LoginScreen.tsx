"use client";

// Full-page sign-in wall. Rendered by <AuthGate> whenever Entra is configured and
// the user is not authenticated — it replaces the ENTIRE app (no shell, no nav, no
// route content), so nothing is reachable without signing in. After sign-out
// (logoutRedirect) the user lands back here.

import { useMsal } from "@azure/msal-react";
import { apiScopes } from "@/lib/auth/msal";
import { branding } from "@/lib/branding";

export function LoginScreen() {
  const { instance } = useMsal();

  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)",
        fontFamily: "system-ui, sans-serif",
        padding: 24,
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 380,
          background: "#fff",
          borderRadius: 16,
          padding: "40px 32px",
          boxShadow: "0 20px 60px rgba(0,0,0,0.35)",
          textAlign: "center",
        }}
      >
        <div style={{ fontSize: 40, lineHeight: 1 }}>⚡</div>
        <h1 style={{ margin: "16px 0 4px", fontSize: 22, color: "#0f172a" }}>{branding.product}</h1>
        <p style={{ margin: "0 0 28px", color: "#64748b", fontSize: 14 }}>{branding.description}</p>
        <button
          onClick={() => instance.loginRedirect({ scopes: apiScopes })}
          style={{
            width: "100%",
            padding: "12px 16px",
            borderRadius: 10,
            border: "none",
            background: "#2563eb",
            color: "#fff",
            fontSize: 15,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Sign in with Microsoft
        </button>
        <p style={{ margin: "20px 0 0", color: "#94a3b8", fontSize: 12 }}>
          You must sign in to access the Helpdesk.
        </p>
      </div>
    </div>
  );
}
