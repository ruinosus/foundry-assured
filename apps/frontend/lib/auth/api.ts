"use client";

// Fetch wrapper that attaches the Entra access token when auth is configured.
// Uses the msalInstance singleton directly (no React hook), so it works from any
// client component without needing to be inside a provider's render tree. In local
// dev (authConfigured=false) it degrades to a plain fetch — the backend's auth
// dependency is a no-op there too.

import { apiScopes, authConfigured, msalInstance } from "@/lib/auth/msal";
import { selectedAreaId } from "@/lib/area-selection";
import { LOCALE_COOKIE } from "@/lib/locale";

/** A escolha de idioma da interface, do cookie — vazio quando a pessoa está em "automático". */
function chosenLocale(): string | null {
  if (typeof document === "undefined") return null;
  const hit = document.cookie.split("; ").find((c) => c.startsWith(`${LOCALE_COOKIE}=`));
  return hit ? decodeURIComponent(hit.split("=")[1]) : null;
}

export function claimsFromChallenge(header: string | null): string | null {
  if (!header || !/^Bearer\s/i.test(header) || !/error="insufficient_claims"/i.test(header))
    return null;
  const match = header.match(/(?:^|,\s*)claims=("(?:\\.|[^"\\])*")/i);
  if (!match) return null;
  try {
    const claims = JSON.parse(match[1]);
    return typeof claims === "string" && claims.length <= 8192 ? claims : null;
  } catch {
    return null;
  }
}

async function tokenWithClaims(claims: string): Promise<string | null> {
  if (!authConfigured || !msalInstance) return null;
  const account = msalInstance.getAllAccounts()[0];
  if (!account) return null;
  const request = { scopes: apiScopes, account, claims };
  try {
    return (await msalInstance.acquireTokenSilent(request)).accessToken;
  } catch {
    try {
      return (await msalInstance.acquireTokenPopup(request)).accessToken;
    } catch {
      return null;
    }
  }
}

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
  // O MESMO idioma da interface vai ao backend, que o repassa ao agente como preferência de
  // resposta. Sem isto, a interface em inglês conversaria com um agente em português — que é
  // exatamente a mistura que a tradução veio corrigir.
  //
  // Só quando há escolha explícita: em "automático" o navegador já envia o seu Accept-Language,
  // e sobrescrevê-lo aqui apagaria a preferência real da pessoa.
  const locale = chosenLocale();
  if (locale && !headers.has("Accept-Language")) headers.set("Accept-Language", locale);
  const areaId = selectedAreaId();
  if (areaId && !headers.has("X-Area-ID")) headers.set("X-Area-ID", areaId);

  const response = await fetch(input, { ...init, headers });
  if (response.status !== 401) return response;

  const claims = claimsFromChallenge(response.headers.get("WWW-Authenticate"));
  if (!claims) return response;
  const steppedUpToken = await tokenWithClaims(claims);
  if (!steppedUpToken) return response;
  headers.set("Authorization", `Bearer ${steppedUpToken}`);
  return fetch(input, { ...init, headers });
}
