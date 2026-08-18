// Flat config (ESLint 9). Next 16 removed the `next lint` subcommand — the lint
// script now calls the ESLint CLI directly, so this file IS the configuration
// (there was none before: `next lint` used to set one up interactively, which in
// CI just failed silently behind continue-on-error).
//
// ESLint fica em 9 DE PROPÓSITO, e o `^10` que estava no package.json era deriva.
// O `eslint-config-next` declara peer `eslint: >=9.0.0`, mas a dependência dele
// `eslint-plugin-react@^7.37.0` tem peer `... || ^9.7` — nenhuma versão publicada
// do plugin suporta ESLint 10. O peer aberto mentia; o limite real mora um nível
// abaixo. Com ESLint 10 instalado o lint não achava erro nenhum: ele MORRIA ao
// carregar a regra `react/display-name` (`contextOrFilename.getFilename is not a
// function`), e o `continue-on-error` do CI engolia o crash. Um gate que quebra e
// um gate que passa ficavam com a mesma aparência — pela SEGUNDA vez neste mesmo
// arquivo. Voltar para 10 exige o plugin publicar suporte, não mexer aqui.
import next from "eslint-config-next";

const config = [
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
  ...next,
  {
    rules: {
      // UMA regra baixada, nomeada e medida — não as três da era do React Compiler em bloco.
      // Elas chegaram caladas num MINOR do `eslint-plugin-react-hooks` (^7.0.0, dentro do
      // eslint-config-next) no mesmo período em que este gate parou de rodar, então nunca foram
      // aplicadas a este código. Das três, duas foram CONSERTADAS em vez de desligadas:
      //
      //   purity      — as duas de verdade eram chave de <tr> sorteada a cada render, que
      //                 remontava a linha inteira (AgentDetail); a terceira era um fallback de
      //                 `Math.random()` para navegador que não existe (SuggestedPrompts).
      //   immutability — a única ocorrência ganhou disable LOCAL com motivo, no LanguageToggle:
      //                 escrever no cookie é o efeito do handler, não um descuido.
      //
      // Sobra `set-state-in-effect`, e ela fica em `warn` com o número na frente: 18 sítios, em
      // 3 formatos diferentes, em quase toda tela de listagem. É o `useEffect(() => { void
      // load(); }, [load])` cujo `load` começa com `setLoading(true)` — redundante na montagem,
      // porque o estado inicial já é esse. O conserto é real (mover o prelúdio para quem
      // recarrega), não é mecânico, e refazer 18 telas é decisão de quem paga a refatoração —
      // não efeito colateral de um bump de dependência. Promover a `error` quando cair a zero.
      "react-hooks/set-state-in-effect": "warn",
    },
  },
];

export default config;
