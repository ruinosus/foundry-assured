"use client";

// Importar skill de um catálogo público — Microsoft, Anthropic, ou qualquer repositório no
// formato agentskills.io.
//
// POR QUE ESTA TELA TEM UM PASSO DE LEITURA. Importar publica um documento escrito por terceiros
// no Foundry da empresa. A lista mostra 198 nomes; o que decide é o SKILL.md, e ele aparece
// INTEIRO antes do botão de publicar — sem resumo nosso, que seria uma leitura a menos para quem
// está aprovando. É a mesma propriedade do `assist.py`: a máquina propõe, a pessoa decide.
//
// A lista custa UMA chamada ao GitHub (a árvore); a descrição de cada skill custaria uma chamada
// por skill, e o limite sem token é 60 por hora. Por isso o preview é sob demanda.

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";
import { authedFetch } from "@/lib/auth/api";

type CatalogRef = { id: string; repo: string; label: string };
type Entry = {
  id: string; name: string; group: string; subpath: string;
  path: string; repo: string; bytes: number;
};
type Preview = {
  name: string; description: string; license: string;
  author: string; version: string; body: string; path: string; repo: string;
  chars: number; max_chars: number; too_large: boolean;
};

export function SkillCatalog({ onImported }: { onImported: () => void }) {
  const t = useTranslations("skillCatalog");
  const tc = useTranslations("common");

  const [catalogs, setCatalogs] = useState<CatalogRef[]>([]);
  const [repo, setRepo] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [busca, setBusca] = useState("");
  const [sel, setSel] = useState<Entry | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [importando, setImportando] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const r = await authedFetch("/api/foundry/skill-catalog?op=catalogs", { cache: "no-store" });
        const b = await r.json().catch(() => ({}));
        if (r.ok) {
          setCatalogs(b.catalogs ?? []);
          if (b.catalogs?.[0]) setRepo(b.catalogs[0].repo);
        }
      } catch {
        setErro(tc("backendUnreachable"));
      }
    })();
  }, [tc]);

  const listar = useCallback(async (alvo: string) => {
    if (!alvo) return;
    setCarregando(true);
    setErro(null);
    setSel(null);
    setPreview(null);
    try {
      const r = await authedFetch(`/api/foundry/skill-catalog?repo=${encodeURIComponent(alvo)}`, {
        cache: "no-store",
      });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(b?.error ?? `HTTP ${r.status}`);
        setEntries([]);
        return;
      }
      setEntries(b.skills ?? []);
    } catch {
      setErro(tc("backendUnreachable"));
    } finally {
      setCarregando(false);
    }
  }, [tc]);

  useEffect(() => {
    if (repo) void listar(repo);
  }, [repo, listar]);

  const abrir = async (e: Entry) => {
    setSel(e);
    setPreview(null);
    setErro(null);
    try {
      const r = await authedFetch(
        `/api/foundry/skill-catalog?op=preview&repo=${encodeURIComponent(e.repo)}&path=${encodeURIComponent(e.path)}`,
        { cache: "no-store" },
      );
      const b = await r.json().catch(() => ({}));
      if (!r.ok) {
        setErro(b?.error ?? `HTTP ${r.status}`);
        return;
      }
      setPreview(b);
    } catch {
      setErro(tc("backendUnreachable"));
    }
  };

  const importar = async () => {
    if (!sel) return;
    setImportando(true);
    setAviso(null);
    try {
      const r = await authedFetch("/api/foundry/skill-catalog", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: sel.repo, path: sel.path }),
      });
      const b = await r.json().catch(() => ({}));
      if (!r.ok) {
        setAviso(b?.error ?? `HTTP ${r.status}`);
        return;
      }
      // O que ficou de fora do bundle é dito. Uma skill publicada sem o arquivo que ela
      // referencia parece completa e não é.
      setAviso(
        b.skipped?.length
          ? t("importedPartial", { name: b.name, files: b.files, skipped: b.skipped.length })
          : t("imported", { name: b.name, files: b.files }),
      );
      onImported();
    } catch {
      setAviso(tc("backendUnreachable"));
    } finally {
      setImportando(false);
    }
  };

  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.group.toLowerCase().includes(q) ||
        e.subpath.toLowerCase().includes(q),
    );
  }, [entries, busca]);

  return (
    <section className="stack-sm">
      <div className="row-tight">
        <select className="acct-btn" value={repo} onChange={(e) => setRepo(e.target.value)}>
          {catalogs.map((c) => (
            <option key={c.id} value={c.repo}>
              {c.label} — {c.repo}
            </option>
          ))}
        </select>
        <input
          className="acct-btn"
          placeholder={t("searchPlaceholder")}
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
        />
        <span className="muted t-xs">
          {t("count", { shown: filtradas.length, total: entries.length })}
        </span>
      </div>

      {erro && (
        <div className="notice notice-block">
          <p className="notice-body">{erro}</p>
        </div>
      )}
      {aviso && (
        <div className="notice">
          <p className="notice-body">{aviso}</p>
        </div>
      )}

      <div className="cat-split">
        <ul className="cat-list">
          {carregando && <li className="muted t-xs">{tc("loading")}</li>}
          {filtradas.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                className={`cat-item${sel?.id === e.id ? " on" : ""}`}
                onClick={() => void abrir(e)}
              >
                <span className="cat-name">{e.name}</span>
                {(e.group || e.subpath) && (
                  <span className="cat-path t-xs muted-line">
                    {[e.group, e.subpath].filter(Boolean).join(" / ")}
                  </span>
                )}
                {/* Aviso, não veredito: o tamanho vem em BYTES da árvore e o teto do serviço é
                    em CARACTERES — num arquivo com acentos os dois divergem. A recusa exata
                    acontece no preview, onde o texto está em mãos. */}
                {e.bytes > 65536 && <span className="t-xs bad-line">{t("maybeTooLarge")}</span>}
              </button>
            </li>
          ))}
        </ul>

        <div className="cat-preview">
          {!sel && <p className="muted t-sm">{t("pickOne")}</p>}
          {sel && !preview && !erro && <p className="muted t-sm">{tc("loading")}</p>}
          {preview && (
            <>
              <h4 className="section-title">{preview.name}</h4>
              {preview.description && <p className="t-sm">{preview.description}</p>}
              <p className="t-xs muted-line">
                {[preview.author, preview.version && `v${preview.version}`, preview.license]
                  .filter(Boolean)
                  .join(" · ") || "—"}
              </p>
              {/* O documento INTEIRO. Quem publica um texto de terceiro na empresa precisa
                  poder ler o texto de terceiro. */}
              <pre className="doc-preview">{preview.body}</pre>

              {/* O teto é do SERVIÇO, não nosso: `Skill instructions exceed the maximum length
                  of 65536 characters`. Dizer isso aqui evita subir o bundle inteiro para
                  receber a recusa depois — e explica o que fazer, que a mensagem da plataforma
                  não explica. */}
              {preview.too_large ? (
                <div className="notice notice-block">
                  <p className="notice-body">
                    {t("tooLarge", { chars: preview.chars, max: preview.max_chars })}
                  </p>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn btn-solid"
                  disabled={importando}
                  onClick={() => void importar()}
                >
                  {importando ? t("importing") : t("import")}
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
