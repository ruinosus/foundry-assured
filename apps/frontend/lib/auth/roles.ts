"use client";

// The user's app roles come from the backend /me (the `roles` claim lives in the access
// token, not the SPA id token). Used only to show/hide admin UI — the real gate is
// server-side on every admin endpoint.

import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import { authConfigured } from "@/lib/auth/msal";

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

/** Pode ver e usar a interface de administração?
 *
 * `isAdmin` sozinho não bastava, e o efeito era invisível: em desenvolvimento local o Entra não
 * está configurado, então `/me` responde "Not authenticated", `roles` vira `[]` e todo botão de
 * criar/apagar desaparece — enquanto o backend, com auth desligada, deixa a chamada passar
 * (`require_role` é no-op nesse modo). Frontend e backend discordavam, e quem abria o app
 * localmente concluía que a tela de criação não tinha sido feita.
 *
 * Espelhar a decisão do backend é o que corrige: sem auth configurada, não há papéis a checar.
 * Isto NÃO afrouxa nada em produção — lá `authConfigured` é true e o papel volta a valer, e a
 * checagem que importa continua sendo a do servidor em cada endpoint.
 */
export const canAdmin = (roles: string[] | null): boolean => !authConfigured || isAdmin(roles);
