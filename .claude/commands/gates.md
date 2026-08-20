---
description: Roda os gates que o CI exige e tria só o que falhou
argument-hint: "[--all] [-k <regex>]"
allowed-tools: Bash(uv run --project apps/backend --no-sync python scripts/gates.py:*), Read, Grep, Glob
---

Rode os gates do CI localmente e **tria o resultado** — não repasse a saída bruta.

```
!`uv run --project apps/backend --no-sync python scripts/gates.py $ARGUMENTS 2>&1 | grep -v '^warning: `VIRTUAL_ENV'`
```

A lista de gates é **derivada de `.github/workflows/ci.yml`** por `scripts/gates.py` — nunca
mantenha uma cópia dela em lugar nenhum (foi assim que o `CLAUDE.md` passou a listar 35 dos
42 gates que o CI rodava). Sem argumento roda o job `backend`, que é offline e determinístico;
`--all` inclui frontend e infra, que precisam de `npm install` e do `bicep` no PATH.

Com a saída acima:

- **Tudo verde** → diga isso em uma linha e pare. Não resuma gate por gate.
- **Algo vermelho** → para cada falha, dê:
  1. o gate e o que ele protege (leia a docstring do módulo — ela diz *por que* o gate existe);
  2. a causa provável, ancorada em `arquivo:linha`;
  3. a correção mínima.

  Depois pare e apresente as correções. **Não corrija sem o dev decidir** — um gate vermelho às
  vezes está certo e a mudança é que está errada.

Se um gate falhar por ambiente (dependência faltando, credencial ausente, porta ocupada) e não
por código, diga isso explicitamente em vez de propor mudança de código.
