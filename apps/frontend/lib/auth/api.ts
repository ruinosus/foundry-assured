"use client";

// Fetch wrapper that attaches the Entra access token when auth is configured.
// Uses the msalInstance singleton directly (no React hook), so it works from any
// client component without needing to be inside a provider's render tree. In local
// dev (authConfigured=false) it degrades to a plain fetch — the backend's auth
// dependency is a no-op there too.

import { apiScopes, authConfigured, msalInstance } from "@/lib/auth/msal";

export async function authedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (authConfigured && msalInstance) {
    const account = msalInstance.getAllAccounts()[0];
    if (account) {
      try {
        const r = await msalInstance.acquireTokenSilent({ scopes: apiScopes, account });
        headers.set("Authorization", `Bearer ${r.accessToken}`);
      } catch {
        // No silent token (expired/interaction required) → send unauthenticated;
        // the caller surfaces the resulting 401 rather than forcing a redirect here.
      }
    }
  }
  return fetch(input, { ...init, headers });
}
