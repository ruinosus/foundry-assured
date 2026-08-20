---
description: Prepara o PR — branch, Conventional Commits, template preenchido e gates verdes
argument-hint: "[resumo curto do que mudou]"
allowed-tools: Bash(git:*), Bash(gh:*), Bash(uv run --project apps/backend --no-sync python scripts/gates.py:*), Read, Grep, Glob
---

Prepare o PR desta branch. Estado atual:

- branch / status: !`git status -sb | head -20`
- commits desde `main`: !`git log --oneline main..HEAD 2>/dev/null | head -20`
- diff resumido: !`git diff --stat main...HEAD 2>/dev/null | tail -20`

## Ordem, sem pular

1. **Gates verdes primeiro.** `CI passed` é o único check obrigatório e um PR vermelho gasta o
   tempo do revisor:
   ```bash
   uv run --project apps/backend --no-sync python scripts/gates.py
   ```
   Vermelho → pare e apresente. Não abra o PR.

2. **Branch.** `main` é protegida. Se `git status` mostrar `main`, crie
   `feat|fix|chore|docs|ci/<descrição-curta>` antes de qualquer commit.

3. **Título em Conventional Commits**, no estilo do repo — frase declarativa em português,
   descrevendo o efeito, não a mecânica:
   ```
   feat(eval): o gate de citação passa a provar a resolubilidade, não só a presença
   ```
   Tipos: `feat` `fix` `chore` `docs` `refactor` `test` `ci` `build` `perf`.
   Escopos: `backend` `frontend` `hosted-agent` `infra` `eval` `auth` `deps` `tooling`.
   Confira contra `git log --oneline -10` antes de decidir.

4. **Corpo do commit e do PR: o PORQUÊ.** Este repo documenta a cicatriz, não a mudança — leia
   qualquer commit recente ou docstring de gate para calibrar o tom. Se a mudança conserta algo
   que falhou em silêncio, diga qual era o silêncio.

5. **Template.** Preencha `.github/pull_request_template.md` de verdade — marque só o que você
   verificou. Item não verificado fica desmarcado; marcar sem conferir é pior que deixar vazio.

6. **Board DNA**, se houver story ativa: `dna sdlc story pr <slug> --base main`
   (`DNA_BASE_DIR=$PWD/.dna`). É dev-time, não bloqueia.

## Antes de abrir, confira

- Um PR = uma preocupação. Se o diff faz duas coisas, diga isso e proponha separar.
- Nenhum segredo, chave ou valor de `.env` no diff.
- Mudou prompt? O eval-case correspondente mudou no mesmo PR (a skill `prompt-change` cobre).
- Mudou comportamento ou setup? `README.md` / `docs/DEPLOYMENT.md` acompanham.

**Não faça push nem abra o PR sem o dev confirmar** — mostre o título, o corpo e o template
preenchidos, e espere.
