#!/usr/bin/env python3
"""Gate: um clone novo, SEM sign-in configurado, precisa conseguir subir.

O `entraApiClientSecret` é opcional por desenho — `up-all.sh` sem `--with-auth` não cria as app
registrations, e o repositório suporta rodar com identidade única, sem Entra. Mas a Azure recusa
um Container App secret sem valor:

    ContainerAppSecretInvalid: value or keyVaultUrl and identity should be provided

e recusar o secret derruba o container app INTEIRO. O sintoma não se parece com o problema: o
`web`, que não declara segredo, sobe normal, e o resource group fica com toda a infraestrutura no
lugar e um buraco em forma de backend. Foi assim que o backend passou dias sem existir.

Duas coisas têm que andar JUNTAS, e é isso que este gate trava:

  1. o `secrets` só declara `entra-api-secret` quando o parâmetro tem valor;
  2. a env var `ENTRA_API_CLIENT_SECRET` (um `secretRef` para ele) obedece à MESMA condição.

Quebrar o par nos dois sentidos falha igual: secret sem quem use é inofensivo, mas `secretRef`
apontando para segredo não declarado é o mesmo erro de deployment que o item 1 evita.

DOIS APPS DECLARAM SEGREDO OPCIONAL DESDE A FASE 3 (T3), e por isso este gate deixou de olhar
um só. O container app `mcp` ganhou `MCP_REQUEST_STATE_KEY` — a chave que assina a decisão
humana da escrita —, que é opcional pelo mesmo desenho: sem ela o servidor sobe e só a tool de
escrita se declara indisponível. Vigiar apenas o backend deixaria a MESMA falha nascer no
vizinho, e ela é exatamente do tipo que não se parece com o problema: o `mcp` simplesmente não
existiria no resource group.
"""

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

#: Um por container app que declara segredo OPCIONAL: (rótulo, tag do azd, parâmetro, nome do
#: secret). A lista é a fonte; acrescentar um app aqui é o passo que faz o gate enxergá-lo.
OPCIONAIS = (
    ("backend", "backend", "entraApiClientSecret", "entra-api-secret"),
    ("mcp", "mcp", "mcpRequestStateKey", "mcp-request-state-key"),
)


def main() -> int:
    alvo = str(RAIZ / "infra" / "containerapps.bicep")
    # O CI instala o binário `bicep` solto; a máquina de dev normalmente só tem `az bicep`.
    # Tentar os dois evita um gate que só roda num dos dois lugares — que é meio gate.
    for cmd in (["bicep", "build", alvo, "--stdout"],
                ["az", "bicep", "build", "--file", alvo, "--stdout"]):
        try:
            arm = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            continue
        if arm.returncode == 0:
            break
    else:
        print("✖ nem `bicep` nem `az bicep` disponíveis", file=sys.stderr)
        return 1
    if arm.returncode != 0:
        print(f"✖ bicep build falhou:\n{arm.stderr}", file=sys.stderr)
        return 1

    recursos = [
        r for r in json.loads(arm.stdout).get("resources", [])
        if r.get("type") == "Microsoft.App/containerApps"
    ]

    falhas = []
    for rotulo, tag, parametro, segredo in OPCIONAIS:
        apps = [r for r in recursos if tag in json.dumps(r.get("tags", {}))]
        if len(apps) != 1:
            falhas.append(f"esperava exatamente 1 container app `{rotulo}`, achei {len(apps)}")
            continue

        teste = f"empty(parameters('{parametro}'))"
        props = apps[0]["properties"]
        secrets = json.dumps(props["configuration"].get("secrets"))
        env = json.dumps(props["template"]["containers"][0]["env"])

        if teste not in secrets:
            falhas.append(
                f"{rotulo}: o `secrets` declara `{segredo}` SEM condição — provision sem o "
                f"valor morre com ContainerAppSecretInvalid e o app não é criado"
            )
        elif segredo not in env:
            # O ARM compilado guarda o env como EXPRESSÃO (`concat(createArray(...), if(...))`),
            # então o que se procura é o nome do segredo dentro dela — não a sintaxe `secretRef:`
            # do bicep, que não sobrevive à compilação.
            falhas.append(
                f"{rotulo}: `{segredo}` é declarado e ninguém o consome — um segredo que não "
                "chega ao container é configuração que parece feita e não está"
            )
        elif teste not in env:
            falhas.append(
                f"{rotulo}: a env var usa `secretRef: {segredo}` sem a MESMA condição do "
                "`secrets` — referência a segredo não declarado falha o deployment igual"
            )
        if not [f for f in falhas if f.startswith(f"{rotulo}:")]:
            print(f"  ✓ {rotulo}: `{segredo}` só é declarado quando existe, e a env var o segue")

    for f in falhas:
        print(f"  ✗ {f}")
    if falhas:
        print("\n✖ um provision sem os segredos opcionais não subiria todos os apps.", file=sys.stderr)
        return 1

    print("\n✅ provision sem os segredos opcionais cria os dois apps — clone novo sobe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
