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

Confira a cobertura em vez de confiar — o script abaixo compara `app/modules/` com o que os
contratos declaram:

```bash
cd apps/backend && python3 - <<'PY'
import pathlib, tomllib
cfg = tomllib.loads(pathlib.Path("importlinter.toml").read_text())
mods = sorted(p.name for p in pathlib.Path("app/modules").iterdir()
              if p.is_dir() and not p.name.startswith(("_", ".")))
priv = [c for c in cfg["tool"]["importlinter"]["contracts"]
        if c["name"].endswith("internals are private")]
print("sem contrato:", [m for m in mods if not any(c["name"].startswith(m + " ") for c in priv)])
for c in priv:
    alvo = c["name"].split(" internals")[0]
    falta = {f"app.modules.{m}" for m in mods} - {f"app.modules.{alvo}"} - set(c["source_modules"])
    if falta:
        print(f"{c['name']}: nao vigia {sorted(x.split('.')[-1] for x in falta)}")
PY
```

**Em 2026-08-20 esse script acusava buracos em todos os 18 contratos**, e `builder`/`pricing`
sem contrato nenhum — `Contracts: 22 kept, 0 broken` no verde. Se ainda acusar, o gate está
verde sem estar protegendo; diga isso em vez de assumir que passou.

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
