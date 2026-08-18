"""O pacote de diligência — o objeto único que responde "me mostre a prova".

POR QUE UM ARQUIVO E NÃO UMA TELA. Uma tela prova para quem já confia no sistema que a desenha.
Auditoria é o caso em que ninguém confia: o pacote sai daqui e é verificado por fora, com
ferramenta de terceiro, sem acesso nenhum à nossa infraestrutura. Se a verificação só funciona
dentro do produto, ela não é verificação — é a nossa palavra com formatação melhor.

O QUE VAI DENTRO:

    trilha/<escopo>.jsonl      os eventos, como estão gravados
    ancoras/<escopo>/*.json    os fechos diários write-once
    verificacao.json           o resultado da reconstrução da cadeia, por escopo
    LEIA-ME.md                 como verificar SEM este produto

O RELATÓRIO DECLARA O QUE FALTA. `tsr: null` e `ledger_receipt: null` viajam no pacote com essa
cara, e o LEIA-ME explica o que a ausência custa. Um pacote que omitisse os campos faria o
auditor supor que a prova temporal existe — e a omissão seria a mentira, não o campo vazio.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime

from app.modules.audit.internal.anchor import list_anchors
from app.modules.audit.internal.anchor import read as read_anchor
from app.modules.audit.internal.trail import trail, verify

#: Os escopos que o pacote cobre. Fechado porque cada um tem significado próprio, e um escopo
#: novo deve entrar por decisão, não por acidente de nome.
ESCOPOS = ("approvals", "access", "redactions")

_LEIAME = """# Pacote de diligência

Este pacote existe para ser verificado **sem** o sistema que o produziu. Nada aqui depende de
acesso à infraestrutura de origem.

## O que tem dentro

- `trilha/<escopo>.jsonl` — os eventos, um JSON por linha, na ordem em que foram gravados.
- `ancoras/<escopo>/<data>.json` — o fecho diário: o hash de cabeça da trilha naquele dia,
  gravado num blob write-once sob política de imutabilidade do Azure.
- `verificacao.json` — o resultado da reconstrução da cadeia, feito no momento da exportação.

## Como verificar a cadeia por conta própria

Cada evento carrega `prev` (o hash do anterior) e `hash`. O hash é:

    sha256(prev + json_canonico_do_evento_sem_o_campo_hash)

onde `json_canonico` usa chaves ordenadas, sem espaços e sem escapar não-ASCII
(`json.dumps(..., sort_keys=True, ensure_ascii=False, separators=(",", ":"))`).

O primeiro evento tem `prev = "genesis"`. Se um evento foi alterado, o hash dele deixa de
corresponder ao conteúdo; se um evento foi removido, o `prev` do seguinte deixa de corresponder ao
hash do anterior. Nos dois casos a verificação aponta o `seq` exato.

## O que este pacote prova, e o que NÃO prova

**Prova** que a trilha não foi alterada desde o fechamento diário: alterá-la exigiria também
alterar as âncoras, que estão sob política de imutabilidade da plataforma.

**Não prova** o instante em que cada evento ocorreu perante terceiros. Isso exigiria um carimbo de
tempo RFC 3161 de uma autoridade credenciada, ou um recibo de ledger com prova criptográfica. Os
campos `tsr` e `ledger_receipt` existem nas âncoras e estão **nulos** — eles são o caminho de
upgrade, e a ausência está declarada aqui de propósito.

**Não contém** conteúdo de conversa, argumento de ferramenta com dado do usuário, nem valor de
documento pessoal. Os eventos registram o que aconteceu, quem fez e quando; quando um dado pessoal
foi barrado antes da gravação, o evento diz o TIPO ("cpf", "email"), nunca o valor.
"""


def build_report() -> dict:
    """A verificação de todos os escopos, com as perdas declaradas."""
    t = trail()
    escopos = {}
    for escopo in ESCOPOS:
        eventos = t.read(escopo)
        v = verify(eventos)
        ancoras = list_anchors(escopo)
        escopos[escopo] = {
            "events": len(eventos),
            "chain": v,
            "anchors": len(ancoras),
            # Uma trilha com eventos e ZERO âncoras é verificável internamente e não tem fecho —
            # dizer isso é a diferença entre um relatório e um selo.
            "unanchored": len(eventos) > 0 and not ancoras,
        }
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scopes": escopos,
        # As duas provas que NÃO temos, nomeadas. Ver LEIA-ME.
        "missing_proofs": ["rfc3161_timestamp", "ledger_receipt"],
    }


def build_package() -> bytes:
    """O ZIP. Devolvido em memória — é um objeto pequeno e efêmero, e gravá-lo em disco criaria
    uma cópia do pacote de auditoria fora do container imutável."""
    t = trail()
    relatorio = build_report()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for escopo in ESCOPOS:
            eventos = t.read(escopo)
            if eventos:
                z.writestr(
                    f"trilha/{escopo}.jsonl",
                    "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eventos),
                )
            for a in list_anchors(escopo):
                ancora = read_anchor(escopo, a["date"])
                if ancora:
                    z.writestr(
                        f"ancoras/{escopo}/{a['date']}.json",
                        json.dumps(ancora, ensure_ascii=False, indent=2),
                    )
        z.writestr("verificacao.json", json.dumps(relatorio, ensure_ascii=False, indent=2))
        z.writestr("LEIA-ME.md", _LEIAME)
    return buffer.getvalue()
