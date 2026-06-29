"use client";

// The user's app roles come from the backend /me (the `roles` claim lives in the access
// token, not the SPA id token). Used only to show/hide admin UI — the real gate is
// server-side on every admin endpoint.

import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

export function useMyRoles(): string[] | null {
  const [roles, setRoles] = useState<string[] | null>(null); // null = loading
  useEffect(() => {
    let alive = true;
    authedFetch("/api/me")
      .then((r) => r.json())
      .then((d) => alive && setRoles(Array.isArray(d.roles) ? d.roles : []))
      .catch(() => alive && setRoles([]));
    return () => {
      alive = false;
    };
  }, []);
  return roles;
}

export const isAdmin = (roles: string[] | null): boolean => !!roles?.includes("Admin");
