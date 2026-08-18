"use client";

// O que o agente está fazendo AGORA — uma linha por chamada de tool.
//
// O BURACO QUE ISTO FECHA. O console registrava renderizador só para a aprovação (`TicketApproval`,
// `GraphApproval`) e para os passos do workflow. Toda OUTRA chamada de tool caía num renderizador
// ausente e virava spinner: no domínio `platform`, que é tool-driven sobre os MCP da Microsoft,
// uma consulta de 20 segundos ao Azure ou ao Learn mostrava uma bolinha girando e nada mais — nem
// qual servidor, nem qual operação. O mesmo nos dois domínios de plantão.
//
// Não era falta de padrão: o AG-UI transmite TOOL_CALL_START/END/RESULT e o CopilotKit expõe
// `useDefaultRenderTool`, um renderizador CORINGA para toda tool sem registro próprio. A
// capacidade estava pronta e sem porta.
//
// ── O que mostra, e o que NÃO mostra ────────────────────────────────────────────────────────
//
// Mostra o **nome real** da tool, e é aqui que esta linha encontra a observabilidade: é o mesmo
// nome que sai no span `gen_ai` que `shared/telemetry` exporta para o Application Insights. Um
// rótulo bonito ("Consultando a documentação") seria mais simpático e IMPOSSÍVEL de procurar no
// trace quando algo dá errado. Uma tool sem rótulo humano aparece CRUA em vez de sumir — tool
// nova tem de ser visível no dia em que nasce, não no dia em que alguém lembra de traduzi-la.
//
// NÃO mostra os argumentos. Eles carregam o que o usuário digitou e o que a tool vai escrever;
// despejá-los na tela é ruído e, num fluxo com dado sensível, exposição desnecessária. Quem
// precisa do argumento tem o trace — que é o lugar com controle de acesso, não o chat.
//
// Esta linha NÃO substitui telemetria. Ela é a vista do usuário sobre o que já é registrado; o
// registro continua sendo o span. Por isso ela não persiste nada e não numera nada.

import { useTranslations } from "next-intl";
import { useDefaultRenderTool } from "@copilotkit/react-core/v2";

/** Tools que JÁ TÊM renderizador próprio e não devem aparecer duas vezes.
 *
 *  `request_info` é o par do card de aprovação: o backend já suprime os eventos dele no stream
 *  (`helpdesk/internal/stream_fix.py`, onde eles viravam um spinner que nunca resolvia), e listar
 *  aqui protege contra o dia em que essa supressão sair. */
const COM_RENDERIZADOR_PROPRIO = new Set(["request_info", "create_ticket"]);

export function ToolActivity() {
  const t = useTranslations("toolActivity");

  useDefaultRenderTool({
    render: ({ name, status, result }) => {
      if (COM_RENDERIZADOR_PROPRIO.has(name)) return <></>;

      const rodando = status !== "complete";
      return (
        <div className={`tool-line${rodando ? " running" : ""}`} aria-live="polite">
          <span className="tool-pip" aria-hidden />
          <span className="tool-name t-mono">{name}</span>
          <span className="tool-status t-xs muted-line">
            {rodando ? t("running") : t("done")}
          </span>
          {/* O RESULTADO aparece resumido: um trecho basta para saber que voltou conteúdo, e o
              inteiro pode ser uma página de documentação. Sem reticências mentirosas — o corte
              é explícito. */}
          {!rodando && result && (
            <span className="tool-result t-xs muted-line" title={t("resultTruncated")}>
              {result.slice(0, 90)}
              {result.length > 90 ? "…" : ""}
            </span>
          )}
        </div>
      );
    },
  });

  return null;
}
