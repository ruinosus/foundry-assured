// Envolve o trecho citado em <mark> DEPOIS da renderização, andando pelos nós de texto.
//
// Marcar o markdown ANTES de renderizar quebraria bloco de código, tabela e link — e é em
// documento técnico que o trecho cai nesses lugares. Aqui não há sintaxe para quebrar.
//
// A comparação é feita em texto NORMALIZADO (espaço colapsado) porque o trecho vem do ÍNDICE
// e o documento vem do BLOB: eles divergem em quebra de linha e indentação. O mapa `posicoes`
// é o que traduz um índice do texto normalizado de volta para (nó, deslocamento) reais.
//
// Extraído de SourceViewer.tsx (era função interna do componente) para poder ser testado sem
// montar React/CopilotKit — só DOM puro, exercitável direto com jsdom.

// Fronteira de elemento de BLOCO conta como espaço em branco, mesmo sem nó de texto entre eles.
// Sem isto, "</p><p>" (dois parágrafos), "</li><li>" (lista) e "</td><td>" (tabela) colam a
// última palavra de um bloco com a primeira do próximo — e um chunk do índice quase sempre
// atravessa pelo menos um parágrafo, então esse era o caso COMUM, não a exceção.
const ELEMENTOS_BLOCO = new Set([
  "P", "DIV", "LI", "TD", "TH", "TR", "TABLE", "THEAD", "TBODY", "TFOOT",
  "UL", "OL", "PRE", "BLOCKQUOTE", "H1", "H2", "H3", "H4", "H5", "H6",
  "SECTION", "ARTICLE", "DL", "DT", "DD", "FIGURE", "FIGCAPTION", "HR",
]);

function blocoAncestral(no: Text): Element | null {
  let el: Element | null = no.parentElement;
  while (el && !ELEMENTOS_BLOCO.has(el.tagName)) el = el.parentElement;
  return el;
}

export function realcar(raiz: HTMLElement, trecho: string): boolean {
  const alvo = trecho.replace(/\s+/g, " ").trim();
  if (alvo.length < 24) return false;

  const nos: Text[] = [];
  // `<br>` NÃO é elemento de bloco (não entra em ELEMENTOS_BLOCO — ele não CONTÉM nada, é uma
  // quebra solta dentro do MESMO bloco), mas produz quebra visual, e o trecho vindo do índice a
  // vê como espaço. Sem tratá-lo, "linha1<br>linha2" dentro do MESMO `<p>` colaria as duas
  // palavras de fronteira sem espaço nenhum entre elas — truncando o realce no meio, do mesmo
  // jeito que a fronteira de bloco truncava antes deste arquivo existir. Hoje isto não é
  // alcançável (nenhum documento do corpus usa `<br>`, e o Streamdown não liga `remark-breaks`),
  // mas silenciosamente voltaria a truncar no dia em que alguém escrever um hard break.
  const brAntes = new Set<Text>();
  const caminhador = document.createTreeWalker(raiz, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {
    acceptNode(no: Node) {
      if (no.nodeType === Node.TEXT_NODE) return NodeFilter.FILTER_ACCEPT;
      if ((no as Element).tagName === "BR") return NodeFilter.FILTER_ACCEPT;
      // Qualquer outro elemento (<strong>, <span>...) não é aceito ELE MESMO, mas o walker
      // continua descendo pelos filhos — é assim que o texto dentro de `<strong>` ainda aparece.
      return NodeFilter.FILTER_SKIP;
    },
  });
  let brPendente = false;
  for (let n = caminhador.nextNode(); n; n = caminhador.nextNode()) {
    if (n.nodeType === Node.ELEMENT_NODE) {
      brPendente = true;
      continue;
    }
    const texto = n as Text;
    nos.push(texto);
    if (brPendente) brAntes.add(texto);
    brPendente = false;
  }

  // Texto normalizado + posição de cada caractere no nó de origem.
  let plano = "";
  const posicoes: Array<{ no: Text; off: number }> = [];
  let espacoPendente = false;
  let blocoAnterior: Element | null = null;
  let primeiro = true;
  for (const no of nos) {
    const bloco = blocoAncestral(no);
    // Trocou de bloco (parágrafo, item de lista, célula) em relação ao nó anterior: trata como
    // se houvesse um espaço entre eles, mesmo sem caractere nenhum aí no DOM.
    if (!primeiro && bloco !== blocoAnterior) espacoPendente = plano.length > 0;
    // `<br>` logo antes deste nó: mesma lógica, mas DENTRO do mesmo bloco.
    if (brAntes.has(no)) espacoPendente = plano.length > 0;
    blocoAnterior = bloco;
    primeiro = false;

    const bruto = no.data;
    for (let i = 0; i < bruto.length; i++) {
      if (/\s/.test(bruto[i])) {
        espacoPendente = plano.length > 0;
        continue;
      }
      if (espacoPendente) {
        plano += " ";
        posicoes.push({ no, off: i });
        espacoPendente = false;
      }
      plano += bruto[i];
      posicoes.push({ no, off: i });
    }
  }

  // O maior prefixo do trecho que exista no documento — divergências de normalização entre
  // índice e blob costumam ficar no FIM do trecho, então encurtar pelo fim é o que resolve.
  let inicio = -1;
  let usados = 0;
  for (let corte = alvo.length; corte >= 24; corte -= Math.max(8, Math.floor(corte / 8))) {
    inicio = plano.indexOf(alvo.slice(0, corte));
    if (inicio >= 0) {
      usados = corte;
      break;
    }
  }
  if (inicio < 0) return false;

  // Se o corte parou bem em cima de um espaço, esse espaço mapeia para o deslocamento do
  // caractere REAL seguinte (é assim que a normalização acima registra espaço sintético — não
  // há posição própria para ele). Incluir esse espaço faria `setEnd(ate+1)` avançar um
  // caractere real a mais do outro lado da fronteira. Descartar o(s) espaço(s) do fim do corte
  // evita o off-by-one.
  while (usados > 0 && alvo[usados - 1] === " ") usados--;
  if (usados < 24) return false;

  // Marca por NÓ: um Range que cruza fronteira de elemento não aceita surroundContents.
  const fim = inicio + usados - 1;
  const porNo = new Map<Text, { de: number; ate: number }>();
  for (let i = inicio; i <= fim && i < posicoes.length; i++) {
    const { no, off } = posicoes[i];
    const faixa = porNo.get(no);
    if (!faixa) porNo.set(no, { de: off, ate: off });
    else faixa.ate = off;
  }

  let primeira: HTMLElement | null = null;
  for (const [no, faixa] of porNo) {
    const range = document.createRange();
    range.setStart(no, faixa.de);
    range.setEnd(no, Math.min(faixa.ate + 1, no.data.length));
    const marca = document.createElement("mark");
    marca.className = "source-hit";
    // `porNo` garante no máximo UMA faixa por nó de texto, e os dois limites do range sempre
    // apontam para o MESMO nó — não existe caso, hoje, em que este range cruze um nó já
    // alterado por uma marca anterior (a causa clássica de InvalidStateError aqui). O catch
    // fica como cinto de segurança para não derrubar a visualização inteira se essa garantia
    // mudar no futuro; se isto disparar de verdade, é sinal de que o agrupamento por nó quebrou.
    try {
      range.surroundContents(marca);
    } catch {
      continue;
    }
    if (!primeira) primeira = marca;
  }

  const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  primeira?.scrollIntoView({ block: "center", behavior: reduzMovimento ? "auto" : "smooth" });
  return primeira !== null;
}
