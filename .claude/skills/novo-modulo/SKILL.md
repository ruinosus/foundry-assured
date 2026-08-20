---
name: novo-modulo
description: Use ao criar um módulo novo em apps/backend/app/modules/, ao mover código entre módulos, ou quando o import-linter reclamar de fronteira. Cobre a estrutura public.py/internal/ da ADR-017 e o contrato no importlinter.toml — incluindo o passo que quase todo mundo esquece.
---

# Módulo novo no backend (ADR-017)

A pergunta que organiza este backend não é "que tipo de arquivo é esse?", é **"de que negócio
esse arquivo é?"**. Código novo entra DENTRO de um módulo existente; só cria módulo novo quando
é um negócio novo.

## Estrutura

```
app/modules/<nome>/
  public.py        a ÚNICA superfície importável de fora
  internal/        tudo o mais
```

Regra de dependência, verificada em CI:

```
composition (main.py, registry.py)  →  o public de qualquer módulo
modules/<m>/                        →  app.shared + o public de outro módulo
shared/                             →  nada de dentro do app
```

## O passo que quase todo mundo esquece

Um módulo novo exige **duas** mudanças no `importlinter.toml`, não uma:

1. **Um contrato novo** — `"<nome> internals are private"`, com `type = "forbidden"`,
   `allow_indirect_imports = true` (sem isso, toda cadeia legítima
   composition → public → internal vira violação), e `source_modules` = **todos os outros
   módulos**.

2. **O módulo novo adicionado ao `source_modules` de TODOS os contratos já existentes.**
   Esquecer isso não dá erro: o gate fica verde e simplesmente não vigia o módulo novo.

Um gate cuida disso desde 2026-08-20 — ele deriva a cobertura esperada de `app/modules/` e
falha nomeando o que ficou de fora:

```bash
cd apps/backend && uv run python -m tests.architecture.importlinter_coverage_test
```

Ele nasceu porque o `import-linter` reportava `22 kept, 0 broken` enquanto `builder` e `pricing`
não tinham contrato nenhum e `oncall -> knowledge.internal` passava batido. Buraco de cobertura
é a AUSÊNCIA de uma linha — não se anuncia sozinho.

## Caminhos de arquivo

Nunca conte `parents[N]` a partir do próprio arquivo (regra 9). Ancore no pacote `app`:

```python
import app as _app
BACKEND_ROOT = Path(_app.__file__).resolve().parent.parent
```

## Verificar

```bash
cd apps/backend && uv run lint-imports --config importlinter.toml
cd apps/backend && uv run python -m tests.architecture.module_graph_test
```

Um hook já roda os dois a cada `.py` editado no backend, mas rode antes de abrir o PR.
