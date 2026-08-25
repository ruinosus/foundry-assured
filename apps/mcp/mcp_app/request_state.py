"""A chave que assina o estado entre as rodadas da decisão — e o que acontece sem ela.

A decisão humana do MCP atravessa DUAS chamadas de `tools/call` (SEP-2322): na primeira o
servidor devolve a pergunta e um `request_state`; na segunda o cliente devolve a resposta do
aprovador junto com esse mesmo `request_state`. O estado volta pelo fio, e o fio é do cliente —
então o SDK o trata como controlado pelo atacante: o `RequestStateBoundary` SELA todo estado que
sai e VERIFICA todo estado que volta, antes de qualquer handler rodar
(`mcp/server/request_state.py`).

O QUE O SELO AMARRA, medido na fonte instalada e não deduzido: além da integridade (AES-256-GCM
com chave derivada por HKDF-SHA256), o envelope carrega expiração (TTL 600s), o PRINCIPAL
autenticado (`authenticated_principal`, o mesmo trio cliente/emissor/subject que a sessão usa) e
a IDENTIDADE DA REQUISIÇÃO (nome da tool + digest dos argumentos). Na prática: o estado de uma
aprovação não pode ser reaproveitado por outra pessoa, nem em outra tool, nem com outros
argumentos, nem depois do prazo. É o que torna "o servidor PERGUNTOU" uma propriedade
verificável em vez de uma promessa — ver `mcp_app.tools_tickets`.

═══ A CHAVE É SEGREDO NOVO PARA OPERAR (ADR-005) ═══

Ela vem de `MCP_REQUEST_STATE_KEY`, e no ambiente publicado vem do cofre para a variável. Não
há — e não pode haver — valor de exemplo que funcione no repositório, no `.env.example` ou em
teste: um segredo que funciona commitado é um segredo vazado, mesmo que só valha em dev. Os
gates deste app geram uma chave na hora (`secrets.token_bytes(32)`).

═══ SEM A CHAVE, O QUE ACONTECE — E POR QUE ESTA ESCOLHA ═══

**A escrita fica indisponível com erro claro; o servidor sobe normalmente.** As alternativas
foram pesadas, e as duas perdem:

1. *Recusar subir (fail-closed no boot).* Derrubaria QUATRO superfícies de leitura — a tool de
   busca, os prompts, o resource do documento, a completion — por causa de um segredo que só a
   escrita usa. É indisponibilidade de leitura causada por lacuna de configuração de escrita, e
   não compra segurança nenhuma: a chave ausente nunca torna a escrita insegura, só a torna
   pouco confiável (o `RequestStateBoundary` continua fail-closed dos dois lados).
2. *Deixar a escrita ligada sobre a chave efêmera* (que é o default do FastMCP quando
   `request_state_security` é omitido — `RequestStateSecurity.ephemeral()`, chave gerada no
   processo). Aí o aprovador decide e recebe `Invalid or expired requestState` sempre que a
   segunda rodada cair noutra réplica ou depois de um restart — e este app roda com
   `minReplicas: 0`, isto é, reinicia por ociosidade. Um chamado que abre às vezes é pior que
   uma escrita que se declara indisponível.

A recusa acontece ANTES de perguntar ao humano, não depois: perguntar para descobrir na volta
que a resposta não pode ser aceita gasta a atenção de um aprovador à toa.

**A REGRA É UMA SÓ, e vale também em dev local** — sem ramo por `auth_enabled`. É de propósito:
uma exigência de operação que só aparece em produção é a que ninguém descobre a tempo. Quem for
mexer na escrita localmente gera a sua chave com o comando que a própria biblioteca sugere:

    python -c "import secrets; print(secrets.token_hex(32))"

═══ CHAVE PRESENTE PORÉM CURTA É ERRO, NÃO INDISPONIBILIDADE ═══

`AESGCMRequestStateCodec` exige >= 32 bytes e recusa na construção. Deixamos essa exceção subir
em `build_app()`: o app não sobe, alto e cedo. Vazio significa "não configurado" (modo
suportado); curto significa "configurado errado", e as duas coisas não podem ter o mesmo
desfecho — foi o mesmo raciocínio do `secrets: empty(...) ? [] : [...]` do `containerapps.bicep`.
"""

from __future__ import annotations

from mcp.server.request_state import RequestStateSecurity

from app.shared.settings import settings

#: O mínimo que o codec da biblioteca aceita. Não é escolha nossa: `AESGCMRequestStateCodec`
#: levanta `ValueError` abaixo disto. Fica nomeado porque `indisponivel()` precisa distinguir
#: "vazio" de "curto" ANTES de construir a política.
TAMANHO_MINIMO = 32

#: O texto que o chamador lê quando a escrita está indisponível. Fala de CONFIGURAÇÃO DO
#: SERVIDOR, não da chamada dele — quem lê precisa saber que não adianta tentar de novo com
#: outros argumentos, e que o conserto é do operador.
MOTIVO_SEM_CHAVE = (
    "escrita indisponível: este servidor está sem MCP_REQUEST_STATE_KEY, a chave que assina o "
    "estado entre a pergunta ao aprovador e a resposta dele. Sem ela a decisão não volta "
    "verificável, e a escrita só pode acontecer depois de uma decisão verificada. É "
    "configuração do operador — tentar de novo não resolve."
)


def _chave() -> str:
    return settings.mcp_request_state_key.strip()


def indisponivel() -> str | None:
    """`None` quando a escrita pode rodar; senão o MOTIVO, no vocabulário do chamador.

    Só o caso VAZIO é indisponibilidade. Chave curta demais não passa por aqui como recusa
    educada: ela estoura em `politica()`, no boot, porque é erro de operação e não um modo.
    """
    return None if _chave() else MOTIVO_SEM_CHAVE


def politica() -> RequestStateSecurity | None:
    """A política de selagem para o construtor do `FastMCP`, ou `None` sem chave configurada.

    `None` deixa o FastMCP cair na chave efêmera do processo — o que é inofensivo aqui porque
    nenhuma superfície de LEITURA emite `request_state`, e a única que emitiria (a escrita) já
    se recusou a rodar por `indisponivel()`.

    Sem `audience=` de propósito: o `RequestStateBoundary` usa o NOME DO SERVIDOR como audiência
    padrão (`low_level.py`, `default_audience=self.name`), e este servidor tem nome fixo
    ("Foundry Assured"). Passar uma audiência à mão criaria a segunda fonte de sempre para o
    mesmo valor. O aviso que o FastMCP emite — "request_state_security sem audience num servidor
    SEM NOME" — não nos alcança justamente por isso.
    """
    chave = _chave()
    if not chave:
        return None
    # A validação de tamanho é da biblioteca (>= 32 bytes) e a mensagem dela já ensina a gerar
    # uma chave. Deixar subir é o comportamento desejado: o app não sobe configurado errado.
    return RequestStateSecurity(keys=[chave])
