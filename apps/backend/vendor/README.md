# vendor/

Código de terceiro **copiado**, não instalado.

## `okf_validate.py`

Verificador determinístico de conformidade do **Open Knowledge Format v0.2** (§11).

- **Origem:** [`scaccogatto/okf-skills`](https://github.com/scaccogatto/okf-skills),
  `skills/validate/scripts/okf_validate.py`
- **Licença:** MIT © Marco Boffo. A especificação OKF é do Google Cloud, Apache-2.0.
- **Copiado em:** 2026-08-30

### Por que COPIADO e não instalado

O script é autocontido — 565 linhas, e as únicas coisas que ele alcança são `argparse`, `json`,
`re`, `sys`, `dataclasses`, `pathlib` e `yaml`. Sem `subprocess`, sem `urllib`, sem `eval`.
Verificado antes de rodá-lo pela primeira vez.

Com esse perfil, copiar é estritamente melhor que depender: o código fica **revisável no
repositório**, entra na mesma revisão de PR que o resto, e o gate não passa a ter uma superfície
de supply chain que se atualiza sozinha. O projeto tem 55 estrelas e um mantenedor — a régua do
NORDOR-122 sobre reputação e manutenção pesa contra depender, e não contra usar.

### Por que usar, em vez de escrever o nosso

A MÁXIMA MAIOR vale para formato também: a conformidade §11 é **da spec**, não nossa. O Google
publicou o formato e não publicou validador; este implementa as regras verbatim, incluindo a que
mais se erra — *cross-link quebrado NÃO é erro*, porque o §6.1 obriga o consumidor a tolerá-lo.
Um validador nosso teria essa regra errada no primeiro dia.

A fronteira é clara, e ela importa:

| | quem valida | o que |
|---|---|---|
| **conformidade OKF** | este script | `type` presente, frontmatter parseável, arquivos reservados |
| **política do produto** | `eval/` e `tests/` | piso de citação, ACL por fonte, o `spec` do formflow |

Chamar o segundo de "validação OKF" seria dizer que seguimos o padrão enquanto recusamos bundles
que o padrão manda aceitar.

### Atualizar

Baixar o arquivo de novo, ler o diff, e rodar `tests.knowledge.okf_conformance_test`. Não há
automação para isso de propósito: é código de terceiro entrando no repositório, e deve passar por
uma pessoa.
