"use client";

// Carrega um manifesto do backend.
//
// SEM CÓPIA EMBUTIDA NO FRONTEND, de propósito. Um fallback local pareceria robustez e seria uma
// segunda fonte do mesmo formulário: no dia em que o documento mudasse, a tela continuaria
// renderizando a cópia antiga sem erro nenhum — a divergência silenciosa que a SEGUNDA MÁXIMA
// descreve. Sem manifesto, a tela DIZ que não conseguiu carregar.

import { useEffect, useState } from "react";
import { authedFetch } from "@/lib/auth/api";
import type { FormFlowManifest } from "@/lib/formflow/types";

export type EstadoManifesto =
  | { estado: "carregando" }
  | { estado: "ok"; manifest: FormFlowManifest }
  /** `motivo` distingue as três falhas que pedem ações diferentes: o formulário não existe, o
   *  documento está torto, ou o backend não respondeu. */
  | { estado: "erro"; motivo: "ausente" | "invalido" | "indisponivel"; detalhe: string };

export function useManifest(nome: string): EstadoManifesto {
  const [r, setR] = useState<EstadoManifesto>({ estado: "carregando" });
  useEffect(() => {
    let vivo = true;
    void (async () => {
      try {
        const resp = await authedFetch(`/api/flows/${encodeURIComponent(nome)}`, { cache: "no-store" });
        const body = await resp.json().catch(() => ({}));
        if (!vivo) return;
        if (resp.ok) return setR({ estado: "ok", manifest: body as FormFlowManifest });
        const motivo = resp.status === 404 ? "ausente" : resp.status === 422 ? "invalido" : "indisponivel";
        setR({ estado: "erro", motivo, detalhe: String(body?.detail ?? body?.error ?? resp.status) });
      } catch (e) {
        if (vivo) setR({ estado: "erro", motivo: "indisponivel", detalhe: String(e) });
      }
    })();
    return () => {
      vivo = false;
    };
  }, [nome]);
  return r;
}
