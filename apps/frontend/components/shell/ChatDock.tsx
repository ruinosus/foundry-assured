"use client";

// Chat lateral nas telas de gestão — um padrão de projeto anterior, com uma diferença de escopo.
//
// POR QUE UM CHAT AQUI. As telas de agentes, conhecimento e skills mostram catálogo e formulário;
// nenhuma delas responde "qual base eu uso para isso?" ou "como escrevo essa instrução?". O chat
// ao lado é onde essas perguntas cabem, sem tirar a pessoa do que ela estava fazendo.
//
// QUAL AGENTE ATENDE. Reusa os domínios que já existem, em vez de inventar um: o `selfwiki`
// conhece este repositório e responde sobre como as peças se encaixam. Criar um agente novo só
// para isto seria mais um recurso a manter, e a pergunta "o que este produto faz" já tem dono.
//
// A escolha fica com a pessoa: o seletor lista os domínios do registry. Fixar um deles decidiria
// por ela num contexto em que a pergunta varia — quem está montando um agente de plataforma quer
// o `platform`, não o `selfwiki`.

import { CopilotChat } from "@copilotkit/react-core/v2";
import { useTranslations } from "next-intl";
import { useChatDock } from "@/lib/chat-dock";
import { DOMAINS } from "@/lib/domains";

export function ChatDock() {
  const t = useTranslations("chatDock");
  const td = useTranslations("domains");
  const { open, hide, agentId, setAgentId } = useChatDock();

  // SEM `threadId` controlado, de propósito. Cada agente já tem a sua própria instância e as
  // suas próprias mensagens no core, então não há histórico vazando de um para o outro — era o
  // que o antigo `key={agentId}` (que remontava o provider) protegia, e o que eu havia trocado
  // por thread fixa. Controlar a thread aqui acrescentava uma variável a um caminho que o
  // o projeto de origem resolvia sem ela, e caminho com peça a menos é caminho com bug a menos.

  // FICA MONTADO MESMO FECHADO, escondido por CSS. Não é preferência de estilo: o
  // `<CopilotChat>` só CONECTA o agente quando monta, e enquanto ele nunca montou um pedido vindo
  // de um campo do wizard rodava sem ninguém conectado — a resposta acontecia e não aparecia.
  // Era o "só funciona depois de abrir o chat uma vez".
  //
  // A alternativa seria esperar a conexão antes de enviar, e foi o que eu tentei três vezes:
  // esperar `open`, esperar um quadro, tentar de novo. Toda tentativa acertava o TEMPO de uma
  // corrida que não precisava existir. Montado sempre, não há corrida — há um agente conectado.
  //
  // `hidden` de verdade (via CSS), não `display:none` inline: o React continua montado, os
  // efeitos rodam, a conexão acontece, e nada disso aparece nem entra na ordem de tabulação.
  return (
    <aside
      className={`chat-dock${open ? "" : " chat-dock-hidden"}`}
      aria-label={t("title")}
      aria-hidden={!open}
      // `inert` como BOOLEANO. Eu havia passado string vazia com cast — o jeito antigo, de
      // quando o React não conhecia o atributo. Ele conhece desde a 19, e a string vazia é lida
      // como FALSE: o dock fechado continuaria alcançável por teclado, que é o oposto do que a
      // linha pretendia.
      inert={!open}
    >
      <header className="chat-dock-head">
        <select
          className="acct-btn"
          value={agentId}
          onChange={(e) => setAgentId(e.target.value)}
          aria-label={t("agentLabel")}
        >
          {DOMAINS.map((d) => (
            <option key={d.id} value={d.id}>
              {td(`${d.id}.label`)}
            </option>
          ))}
        </select>
        <button type="button" className="acct-btn" onClick={hide} aria-label={t("close")}>
          ✕
        </button>
      </header>

      {/* Sem provider próprio: quem provê é o shell (DockProvider), para que uma tool registrada
          por uma TELA seja visível ao agente daqui. */}
      <div className="chat-dock-body copilotkit-chat-host">
        <CopilotChat agentId={agentId} />
      </div>
    </aside>
  );
}
