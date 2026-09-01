# O Diligo e a Resolução CFM nº 2.454/2026

Documento de referência: o que a norma exige, o que o Diligo faz sobre cada exigência, e o que
ele deliberadamente **não** faz.

**Fonte normativa:** `docs/normas/cfm-2454-2026.md` (verificado contra o PDF oficial) e o texto
integral em `docs/normas/cfm-2454-2026-texto-extraido.txt`. Toda citação aqui vem de lá. Nenhum
artigo, prazo ou dispositivo neste documento foi inferido.

---

## 1. A norma, em uma página

**Resolução CFM nº 2.454/2026** — governança de inteligência artificial na medicina.
Publicada no DOU em **27/02/2026**, com **retificação em 05/03/2026**.
**Vigência: 26/08/2026** (Art. 23 — 180 dias da publicação).

### A quem se dirige

Dois sujeitos, com deveres diferentes:

- **O médico** — responde pelos atos que pratica usando IA (Art. 7º). A IA não o exime do Código
  de Ética Médica.
- **A instituição médica** — pública ou privada, que **desenvolver ou utilizar** IA. É dela a
  obrigação de avaliar risco (Art. 12), estabelecer governança (Art. 14) e proteger dados
  (Art. 16, 17).

**Quem fiscaliza:** o **Conselho Regional de Medicina da jurisdição** (Art. 15). Isso importa mais
do que parece — a fiscalização é do CRM do lugar onde o estabelecimento está, não de um órgão
central. É por isso que, num grupo hospitalar, **cada unidade responde por si**.

### Não há período de adaptação

**Art. 21:** *"As disposições desta resolução aplicam-se também aos modelos, sistemas e aplicações
de IA em desenvolvimento ou em uso nas instituições médicas na data da vigência."*

O sistema que já está rodando desde antes de 26/08/2026 está sob a norma **desde o primeiro dia**.
Isso define a natureza do trabalho: a maior parte do que precisa ser inventariado e avaliado
**já está em produção e ninguém cadastrou**.

---

## 2. As cinco obrigações centrais

### 2.1 Avaliar o risco de cada sistema — Art. 12

> **Art. 12.** As instituições médicas, públicas ou privadas, que desenvolverem ou utilizarem
> modelos, sistemas e aplicações de IA deverão realizar uma **avaliação preliminar** com a
> finalidade de definir seu **grau de risco**.
>
> **Parágrafo único.** A avaliação preliminar basear-se-á na categorização e nos critérios
> previstos neste capítulo […] levando em conta **fatores como** o potencial impacto nos direitos
> fundamentais e na saúde dos pacientes, a criticidade do contexto de uso, a complexidade e grau
> de autonomia do modelo, **a finalidade pretendida e as finalidades potenciais**, **o nível de
> intervenção humana no resultado**, e a quantidade e sensibilidade dos dados utilizados.

**São seis fatores**, e o § único os nomeia:

| # | Fator |
| --- | --- |
| 1 | impacto nos direitos fundamentais e na saúde dos pacientes |
| 2 | criticidade do contexto de uso |
| 3 | complexidade e grau de autonomia do modelo |
| 4 | finalidade pretendida **e finalidades potenciais** |
| 5 | nível de intervenção humana no resultado |
| 6 | quantidade e sensibilidade dos dados utilizados |

**O que o Diligo faz:** coleta os seis como **dado estruturado**, um por um, com a análise escrita
da instituição para cada. A classificação final é da instituição — o produto **não sugere nível
automaticamente**, porque o Art. 12 atribui a avaliação a ela.

**Ponto de atenção para quem for redesenhar:** os fatores 4 e 5 são os mais negligenciados na
prática. "Finalidades potenciais" é o que pega o sistema comprado como administrativo e usado, no
dia a dia, como apoio à decisão. "Nível de intervenção humana" é o que distingue aprovação real de
aprovação por hábito.

### 2.2 Classificar em quatro níveis — Art. 13 e Anexo II

> **Art. 13.** […] serão categorizados, quanto ao risco, nos níveis **baixo, médio, alto ou
> inaceitável**, **conforme definido no anexo II**, e deverão ser informados ao usuário.

O **Anexo II** caracteriza os três primeiros (incisos I, II e III). Por exemplo, baixo risco:

> *"aplicações de IA cujo potencial de causar consequências negativas […] é mínimo ou inexistente.
> Caracterizam-se por não exercer influência decisória direta em diagnósticos ou tratamentos
> individuais […] Exemplos: agendamento de consultas, gestão logística de insumos hospitalares,
> chatbots fornecendo informações gerais de saúde (sem personalizar aconselhamento clínico)…"*

**LACUNA DA PRÓPRIA NORMA, e o produto precisa saber representá-la:** o Art. 13 prevê o nível
**"inaceitável"**, e **o Anexo II não o caracteriza**. Não há critério publicado para essa
categoria.

**O que o Diligo faz:** exibe a caracterização literal do Anexo II ao lado de cada nível, citando o
inciso. Para "inaceitável", **não inventa definição** — o nível existe na classificação da solução,
onde o Art. 13 o coloca, mas não entra na régua por fator, porque graduar um fator num nível sem
critério publicado seria registrar palpite como avaliação.

**Distinção que se erra com facilidade:** os **fatores** são do **Art. 12, § único**; os **níveis**
são do **Anexo II**. Citar um pelo outro é erro em qualquer direção.

### 2.3 Governança interna — Art. 14 e Anexo III

> **Art. 14.** A instituição médica ou o médico que desenvolver ou contratar […] deverá
> estabelecer **processos internos de governança** aptos a garantir a segurança, a qualidade e a
> ética, incluindo as medidas contidas no **Anexo III**.
>
> **Parágrafo único.** **Em instituições de saúde que adotarem sistemas próprios de IA** é
> necessária a criação de uma **Comissão de IA e Telemedicina** sob a coordenação médica e
> **subordinada à diretoria técnica**, cuja função é assegurar o cumprimento do anexo III.

**A Comissão é condicionada:** só é exigida de quem adota **sistemas próprios**. Quem apenas
contrata de terceiro responde por menos. É por isso que a pergunta *"a instituição desenvolve ou
contrata?"* tem consequência normativa, e não é burocracia.

**O Anexo III tem oito medidas.** As que mais pesam para o produto:

| Inciso | Medida |
| --- | --- |
| I | Transparência: relatórios regulares em linguagem clara com desempenho, limitações conhecidas, vieses identificados e mitigações |
| II | **Monitoramento contínuo com análise estratificada** para identificar viés (ex.: diferença de acurácia entre grupos populacionais); viés grave e insanável → **descontinuar** |
| III | **O Diretor Técnico é o responsável** pela fiscalização e pelas diretrizes de segurança, ética e transparência |
| VI | Gestão de ciclo de vida como produto, com **revisão periódica do sistema em produção** |
| VIII | **Acesso de órgãos de controle** a relatórios de auditoria, de monitoramento e a informações de configuração — Conselhos de Medicina, CONEP, Ministério Público |

**O inciso III é o eixo do produto inteiro.** Quem assina é o Diretor Técnico do estabelecimento —
e a Resolução CFM nº 997/1980, art. 11 (citada pela 2.147/2016) reforça: o DT é o **principal
responsável**, e todos os serviços técnicos lhe são **hierarquicamente subordinados**.

**O inciso VIII é a razão de o dossiê existir na forma em que existe:** a norma prevê que órgão
externo terá acesso. Um dossiê que só convence quem já confia não serve.

### 2.4 Autonomia do médico — Art. 3º, 18 e 19

> **Art. 3º, III.** É direito do médico **recusar** a utilização de sistemas de IA que não
> apresentem **validação científica adequada**, certificação regulatória pertinente, ou que
> contrariem princípios éticos, técnicos ou legais da medicina.

> **Art. 18, § 1º.** Em nenhum momento os sistemas de IA poderão **restringir ou substituir a
> autoridade final do médico**.

> **Art. 19, § 2º.** *(vedação à instituição de impor metas ou políticas que subordinem a conduta
> médica)*

**Consequência prática que o produto torna visível:** o direito do Art. 3º, III **só existe na
prática se a instituição tiver os números**. Sem acurácia, eficácia e grau de evidência
registrados, o médico não tem como exercer a recusa — o direito vira letra. É por isso que a
ausência desses dados não é lacuna administrativa: é impedimento a um direito.

### 2.5 Dados, segurança e transparência ao paciente — Art. 11, 16, 17

> **Art. 11.** Qualquer utilização de IA deverá ser **comunicada e explicada aos pacientes**,
> reforçando-se que tais sistemas servem de apoio ao médico, mas **não substituem a autoridade e a
> decisão final humana**.

> **Art. 16** *(texto vigente, após a retificação de 05/03/2026)***.** Os dados […] devem ser
> tratados observando rigorosamente a **proteção geral de dados pessoais**, bem como as normativas
> específicas de segurança da informação em saúde.

**ATENÇÃO — o que a retificação mudou:** a versão original do Art. 16 citava **nominalmente a
LGPD**. A retificação de 05/03/2026 **retirou a menção** e a substituiu por "proteção geral de
dados pessoais". **É proibido afirmar que esta Resolução exige conformidade com a LGPD.** A LGPD
continua se aplicando por força própria — mas não é esta norma que a invoca, e citar a versão
anterior é citar texto revogado.

---

## 3. O que o Diligo é

**Um SaaS de conformidade contínua com a Resolução CFM nº 2.454/2026.** Ele não é um sistema de
IA, não avalia sistemas de IA por conta própria, e não emite certificado.

O que ele faz, em uma frase: **transforma o cumprimento da norma numa evidência que se sustenta
diante de quem fiscaliza.**

### 3.1 A invariante que define o produto

> **Zero dado de paciente no sistema.**

Um guardrail determinístico bloqueia CPF, CNS, RG e data de nascimento em **qualquer texto livre,
antes de persistir**. Não é filtro de exibição: o dado não entra. A barreira é estrutural — um
único módulo pode gravar documento, e um teste que varre o código-fonte falha se qualquer outro
caminho tentar.

**Por que isso é central e não um detalhe de privacidade:** uma ferramenta de conformidade que
acumulasse dado assistencial criaria o risco que existe para reduzir.

### 3.2 A cadeia probatória

O Diligo não guarda "o estado atual da conformidade". Ele guarda **o que foi afirmado, por quem,
quando, e prova que não mudou depois**.

```
documento assinado          markdown + frontmatter, com quem verificou e quando
   ↓
trilha append-only          cada evento encadeado por hash ao anterior
   ↓
âncora diária write-once    o hash de cabeça do dia, gravado uma vez e imutável
   ↓
carimbo de tempo RFC 3161   autoridade externa atesta a data
   ↓
dossiê em PDF               a peça que vai ao conselho
```

**Quatro regras que o produto trata como invioláveis:**

1. **Documento assinado nunca é editado.** Revisão cria versão nova; a anterior é depreciada, não
   apagada.
2. **Rascunho não é evidência.** Nada entra na trilha antes da assinatura — e a tela mostra, antes
   do ato, exatamente quais eventos a assinatura vai gerar.
3. **Só o Diretor Técnico assina, e o TOTP é exigido no ato.** Não é configuração; é o Anexo III,
   III e a 997/1980.
4. **A fonte de verdade é o arquivo, não o banco.** O banco é projeção reconstruível. Uma peça
   probatória precisa ser arquivo com cadeia de hash — se fosse linha de tabela, "documento
   assinado nunca é editado" seria promessa de disciplina em vez de propriedade do sistema.

### 3.3 A ideia mais forte do produto: a lacuna declarada

**Campo sem dado não trava o preenchimento.** Ele vira pendência declarada, com o dispositivo que
exige aquele dado, o motivo escrito pela instituição, e o destino da pendência. E **entra na
evidência assinada**.

A tela de assinatura diz, literalmente: *"você está assinando com N lacuna(s) declarada(s)"*.

**Por quê:** um produto de conformidade que só aceita o completo ensina a instituição a mentir. O
campo preenchido com palpite é pior que o campo declarado ausente — porque o palpite parece
resposta. A alternativa a declarar a lacuna é um dossiê que **parece** completo.

### 3.4 O que o produto se recusa a fazer

Isto é tão parte do desenho quanto o resto, e vale para qualquer redesenho:

- **Não diz "certificado" nem "homologado pelo CFM".** Não existe homologação. O produto organiza
  evidência; quem julga é o conselho.
- **Não promete resultado legal.**
- **Não sugere classificação de risco automaticamente.** O Art. 12 atribui a avaliação à
  instituição.
- **Não inventa número.** Se o dado não existe, o painel mostra menos indicadores — nunca uma
  estimativa que pareça medição.
- **Não esconde pendência.** Nenhum filtro, seletor de status ou painel personalizado pode fazer
  uma pendência desaparecer da vista de quem responde por ela.
- **Não afirma dever que a norma não impõe.** Onde a Resolução é silenciosa — prazo de retenção,
  cadência em dias, número de membros de comissão —, o produto declara que a escolha é da
  instituição, em vez de apresentá-la como exigência.

---

## 4. O modelo: instituição e grupo hospitalar

### 4.1 A unidade é o sujeito

O Art. 15 dá a fiscalização ao CRM **da jurisdição de cada estabelecimento**. Logo:

- **Cada unidade tem CNPJ, Diretor Técnico inscrito num conselho, trilha, âncora e dossiê próprios.**
- **A rede não é sujeito de conformidade.** Não tem dossiê e não assina. Um "dossiê da rede"
  criaria um sujeito que a norma não reconhece, e a pergunta seguinte — quem o assina — não teria
  resposta.

### 4.2 Mas o contrato é corporativo

O mesmo sistema tem risco diferente em unidades diferentes: muda a criticidade do contexto, muda o
grau de autonomia, muda o nível de intervenção humana. Um sistema de leitura de imagem num hospital
terciário com radiologista 24h não é o mesmo risco que numa unidade sem plantão presencial das 22h
às 6h.

Por isso o modelo tem **duas camadas**:

| Camada | O que é | Quem assina |
| --- | --- | --- |
| **Rede** | Catálogo corporativo, avaliação de **referência**, política e regimento | Comissão corporativa — assina **documento corporativo** |
| **Unidade** | Implantação, avaliação **local**, ato de adesão | **Diretoria Técnica da unidade** |

**A regra no topo do modelo:** *a avaliação de referência da rede **não supre** a assinatura local.*
Uma implantação com referência publicada e sem avaliação local assinada continua sendo pendência
bloqueante da unidade.

### 4.3 Desvio nunca é ocultável

Quando a leitura local do risco difere da corporativa, a unidade declara **desvio**, com
justificativa **obrigatória** — e o dossiê mostra **os dois lados**, critério a critério.

Exemplo real do produto: um sistema de pré-leitura de imagem, classificado pela rede como
autonomia **média** porque "o laudo final é sempre do radiologista de plantão", recebe da unidade
autonomia **alta** — *"entre 22h e 6h esta unidade não tem radiologista presencial: a pré-leitura
orienta a conduta do plantonista generalista antes de qualquer laudo."*

Mesma classe final, outro caminho. **A matriz da rede não fica verde por omissão.**

### 4.4 O rollup é pelo pior elo

Num grupo, a cobertura de uma marca **nunca é média** das unidades: vale o pior elo. Porque é o
pior elo que recebe a fiscalização.

---

## 5. Os papéis

| Papel | Escopo | O que faz |
| --- | --- | --- |
| **Diretoria Técnica** | unidade | **Assina.** É quem responde perante o conselho |
| **Qualidade** | unidade | Preenche, levanta lacuna, prepara evidência |
| **TI** | unidade | Responde por fornecedor, integração, dado e segurança |
| **Leitura** | unidade | Audita e acompanha |
| **Comissão corporativa** | rede | Homologa no catálogo, publica avaliação de referência e documento corporativo |
| **Administração de rede** | rede | Estrutura: marca, filiação de unidade |

**A separação entre os dois papéis de rede não é organizacional, é normativa:** um é **julgamento
clínico**, o outro é **estrutura**. Quem administra a árvore não pode publicar avaliação de risco —
pela mesma razão que um comitê de tecnologia nunca pode aparecer como signatário de evidência
clínica.

**E nenhum papel de rede assina evidência de unidade.** Isso não depende de disciplina: a política
de acesso do banco torna a escrita sempre de uma unidade só.

---

## 6. Três divergências verificadas e uma incógnita

Registradas porque quem for redesenhar precisa saber o que é decisão nossa e o que é a norma.

1. **O Anexo II não caracteriza "inaceitável".** O Art. 13 prevê o nível; o anexo define três. O
   produto representa isso declarando a ressalva, não preenchendo o vazio.
2. **O Anexo III, II remete a um "art. 10, § 2º" que não existe** no texto publicado. O produto
   cita o inciso pelo que ele determina e não repete a remissão quebrada.
3. **A Comissão do Art. 14 é condicionada a quem adota sistemas próprios**, mas o produto ainda a
   recomenda para qualquer instituição com governança fraca — inclusive a que só contrata.
   Divergência conhecida, ainda não resolvida.
4. **A retificação de 05/03/2026 só está apurada num ponto** (o Art. 16 / LGPD). O restante do que
   ela mudou não foi levantado.

---

## 7. Vocabulário — para o redesenho usar as palavras certas

| Termo | Significa |
| --- | --- |
| **Dossiê** | O PDF que reúne a evidência de **um estabelecimento** e vai ao conselho |
| **Bundle** | O conjunto de arquivos que é a fonte de verdade daquela unidade |
| **Trilha** | O registro append-only encadeado por hash de tudo que aconteceu |
| **Âncora** | O hash de cabeça do dia, gravado uma vez, imutável |
| **Achado** | Uma pendência de conformidade que o motor detecta (pode bloquear o dossiê) |
| **Lacuna declarada** | Um campo que a instituição declarou não ter, com motivo e dispositivo |
| **Implantação** | O uso local de um sistema do catálogo corporativo |
| **Avaliação de referência** | A leitura de risco da **rede**; não substitui a local |
| **Postura** | O que a unidade declara diante da referência: `confirma` ou `desvio` |
| **Guardrail** | A barreira que impede dado de paciente de entrar |

**Uma palavra a evitar:** "compliance score". O produto não pontua conformidade — ele mostra o que
está provado, o que está pendente e o que falta, e deixa o julgamento com quem julga.
