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
"""

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TESTE = "empty(parameters('entraApiClientSecret'))"


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

    apps = [
        r for r in json.loads(arm.stdout).get("resources", [])
        if r.get("type") == "Microsoft.App/containerApps"
        and "backend" in json.dumps(r.get("tags", {}))
    ]
    if len(apps) != 1:
        print(f"✖ esperava exatamente 1 container app do backend, achei {len(apps)}", file=sys.stderr)
        return 1

    props = apps[0]["properties"]
    secrets = json.dumps(props["configuration"].get("secrets"))
    env = json.dumps(props["template"]["containers"][0]["env"])

    falhas = []
    if TESTE not in secrets:
        falhas.append(
            "o `secrets` declara `entra-api-secret` SEM condição — provision sem sign-in "
            "morre com ContainerAppSecretInvalid e o backend não é criado"
        )
    if "entra-api-secret" in env and TESTE not in env:
        falhas.append(
            "a env var usa `secretRef: entra-api-secret` sem a MESMA condição do `secrets` — "
            "referência a segredo não declarado falha o deployment igual"
        )

    for f in falhas:
        print(f"  ✗ {f}")
    if falhas:
        print("\n✖ um clone novo sem `--with-auth` não conseguiria subir o backend.", file=sys.stderr)
        return 1

    print("  ✓ o segredo do Entra só é declarado quando existe")
    print("  ✓ a env var que o referencia obedece à mesma condição")
    print("\n✅ provision sem sign-in cria o backend — clone novo sobe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
