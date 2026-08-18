"use client";

// O seletor de assistente — agrupado por FRAMEWORK.
//
// POR QUE AGRUPADO ASSIM, e não por tipo ou alfabeticamente: quem avalia o produto reconhece
// "Agent Framework", "LangGraph", "deepagents". A lista deixa de ser "cinco assistentes de
// exemplo" e passa a ser a prova de que o mesmo produto, com as mesmas garantias, roda em
// runtimes diferentes — que é o argumento da ADR-020 virando interface.
//
// Resolve também os gêmeos de plantão: `oncall` e `deepcall` param de parecer duplicata e passam
// a ser visivelmente a MESMA triagem em dois harnesses, que é o que eles são.
//
// Dropdown e não pílulas: cabe a agrupação, escala para o próximo framework, e libera a barra de
// topo para o resto.

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { CHAT_DOMAINS, FRAMEWORK_ORDER, type Domain } from "@/lib/domains";

export function DomainPicker({
  current,
  onPick,
}: {
  current: Domain;
  onPick: (id: string) => void;
}) {
  const td = useTranslations("domains");
  const tf = useTranslations("frameworks");
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (!caixa.current?.contains(e.target as Node)) setAberto(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberto(false);
    };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  return (
    <div className="dom-picker" ref={caixa}>
      <button
        type="button"
        className="dom-trigger"
        aria-haspopup="listbox"
        aria-expanded={aberto}
        onClick={() => setAberto((v) => !v)}
      >
        <span aria-hidden>{current.icon}</span>
        <b>{td(`${current.id}.label`)}</b>
        <span className="caret" aria-hidden>▾</span>
      </button>

      {aberto && (
        <div className="dom-menu" role="listbox">
          {FRAMEWORK_ORDER.map((fw) => {
            const doFw = CHAT_DOMAINS.filter((d) => d.framework === fw);
            if (!doFw.length) return null;
            return (
              <div key={fw}>
                <div className="dom-group">
                  {tf(`${fw}.name`)}
                  <span className="dom-by">{tf(`${fw}.vendor`)}</span>
                </div>
                {doFw.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    role="option"
                    aria-selected={d.id === current.id}
                    className={`dom-opt${d.id === current.id ? " on" : ""}`}
                    onClick={() => {
                      setAberto(false);
                      onPick(d.id);
                    }}
                  >
                    <span aria-hidden>{d.icon}</span>
                    <span>
                      <b>{td(`${d.id}.label`)}</b>
                      <i>{td(`${d.id}.blurb`)}</i>
                    </span>
                  </button>
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
