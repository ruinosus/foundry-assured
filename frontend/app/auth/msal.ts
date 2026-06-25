"use client";

// MSAL (Entra ID) config. Reads NEXT_PUBLIC_ vars; when they're absent the app
// runs without auth (matching the backend's DefaultAzureCredential fallback).

import { PublicClientApplication, type Configuration } from "@azure/msal-browser";

const tenantId = process.env.NEXT_PUBLIC_ENTRA_TENANT_ID;
const spaClientId = process.env.NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID;
const apiClientId = process.env.NEXT_PUBLIC_ENTRA_API_CLIENT_ID;

export const authConfigured = Boolean(tenantId && spaClientId && apiClientId);

// The backend API scope the user consents to (OBO is then done server-side).
export const apiScopes = apiClientId ? [`api://${apiClientId}/access_as_user`] : [];

const config: Configuration | null = authConfigured
  ? {
      auth: {
        clientId: spaClientId as string,
        authority: `https://login.microsoftonline.com/${tenantId}`,
        redirectUri:
          typeof window !== "undefined"
            ? window.location.origin
            : "http://localhost:3000",
      },
      cache: { cacheLocation: "sessionStorage" },
    }
  : null;

export const msalInstance = config ? new PublicClientApplication(config) : null;
