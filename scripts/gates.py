#!/usr/bin/env python3
"""Roda localmente os gates que o CI exige, DERIVANDO a lista de `.github/workflows/ci.yml`.

POR QUE DERIVAR, e não manter a lista aqui: ela já existe uma vez, no `ci.yml` — que é quem
de fato barra o merge. Uma segunda cópia diverge no primeiro gate novo, e divergência de
lista não dá erro: só faz o dev achar que rodou tudo. Quando este arquivo foi escrito o
`ci.yml` rodava 42 gates e o `CLAUDE.md` listava 35 — 21 deles nunca tinham aparecido fora
do workflow. É a mesma falha que a SEGUNDA MÁXIMA descreve para recursos do Foundry, só que
aplicada aos próprios gates.

O `working-directory` de cada gate também vem do workflow (`defaults.run` do job), pelo mesmo
motivo: onde o comando roda faz parte da definição dele.

Uso — o pyyaml vem do venv do backend, daí o `--project`:

    uv run --project apps/backend --no-sync python scripts/gates.py           # job backend
    uv run --project apps/backend --no-sync python scripts/gates.py --all     # + frontend + infra
    uv run --project apps/backend --no-sync python scripts/gates.py --list    # só lista, não roda
    uv run --project apps/backend --no-sync python scripts/gates.py -k citation

Sai com código != 0 se qualquer gate falhar, e imprime a saída completa SÓ dos que falharam.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys
import time

import yaml

REPO = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"

#: Steps que instalam dependência ou baixam binário — pré-requisito do runner, não gate.
#: O dev local já tem o ambiente; rodá-los aqui gastaria minutos sem verificar nada.
SETUP_PREFIXES = ("uv sync", "npm ci", "npm install", "curl", "chmod", "sudo")

#: Sem `--all` rodam só estes jobs: são os inteiramente offline e determinísticos.
#:
#: `mcp-app` entrou junto com `apps/mcp` (ADR-027) porque satisfaz o mesmo critério — nenhum
#: passo dele toca a rede. Deixá-lo fora faria o comando padrão passar enquanto o CI barrava,
#: que é exatamente a divergência entre duas listas que este script existe para não ter.
#:
#: Ele roda no venv de `apps/mcp` (o `working-directory` do job), que precisa estar sincronizado:
#: `cd apps/mcp && uv sync`. Sem isso os passos saem como SKIP alto no resumo, não como verde.
DEFAULT_JOBS = ("backend", "mcp-app")


def gates(only_jobs: tuple[str, ...] | None, pattern: str | None) -> list[tuple[str, str, str]]:
    """(job:workdir, nome do step, comando) para cada step executável do workflow."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    found: list[tuple[str, str, str]] = []
    for job_name, job in workflow.get("jobs", {}).items():
        if only_jobs and job_name not in only_jobs:
            continue
        workdir = job.get("defaults", {}).get("run", {}).get("working-directory", ".")
        for step in job.get("steps", []):
            command = step.get("run")
            if not command or "\n" in command.strip():
                continue  # sem `run:` (uma action), ou script multi-linha de setup
            command = command.strip()
            if command.startswith(SETUP_PREFIXES):
                continue
            name = step.get("name", command)
            if pattern and not re.search(pattern, f"{name} {command}", re.IGNORECASE):
                continue
            found.append((f"{job_name}:{workdir}", name, command))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Roda os gates do ci.yml localmente.")
    parser.add_argument("--all", action="store_true", help="inclui frontend e infra")
    parser.add_argument("--list", action="store_true", help="lista os gates sem rodar")
    parser.add_argument("-k", dest="pattern", help="regex sobre o nome/comando do gate")
    args = parser.parse_args()

    selected = gates(None if args.all else DEFAULT_JOBS, args.pattern)
    if not selected:
        print("nenhum gate casou com o filtro", file=sys.stderr)
        return 1

    if args.list:
        for scope, name, command in selected:
            print(f"{scope.split(':')[0]:>9}  {name}\n           $ {command}")
        print(f"\n{len(selected)} gates")
        return 0

    failures: list[tuple[str, str, str]] = []
    #: Ferramenta ausente na máquina (rc 127) não é gate vermelho — o CI instala num step de
    #: setup que este script pula de propósito. Mas fica ALTO no resumo: um skip silencioso
    #: foi o que deixou os security gates sem rodar por semanas (ver CONTRIBUTING.md).
    skipped: list[tuple[str, str]] = []
    for index, (scope, name, command) in enumerate(selected, 1):
        _, workdir = scope.split(":", 1)
        started = time.monotonic()
        done = subprocess.run(
            command, shell=True, cwd=REPO / workdir, capture_output=True, text=True
        )
        elapsed = time.monotonic() - started
        output = f"{done.stdout}{done.stderr}".strip()
        if done.returncode == 127 or "command not found" in output:
            mark = "\033[33mSKIP\033[0m"
            skipped.append((name, output.splitlines()[-1] if output else "comando ausente"))
        elif done.returncode == 0:
            mark = "\033[32m OK \033[0m"
        else:
            mark = "\033[31mFAIL\033[0m"
            failures.append((name, command, output))
        print(f"{mark} [{index:>2}/{len(selected)}] {name}  ({elapsed:.1f}s)", flush=True)

    print()
    for name, output in skipped:
        print(f"\033[33mNAO RODOU\033[0m {name} — {output}")
    if skipped:
        print(f"\033[33m{len(skipped)} gate(s) NAO foram verificados nesta maquina.\033[0m\n")

    for name, command, output in failures:
        print(f"\033[31m--- {name}\033[0m\n$ {command}\n{output}\n")
    if failures:
        print(f"\033[31m{len(failures)} de {len(selected)} gates falharam.\033[0m")
        return 1

    print(f"\033[32m{len(selected) - len(skipped)} gates verdes.\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
