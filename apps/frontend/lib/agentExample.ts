// Exemplo de definição de agente para os campos de texto.
/** O exemplo do campo: JSON montado aqui, com a frase vinda do dicionário.
 *
 * O JSON não pode morar no dicionário — `{` e `}` são a sintaxe de placeholder do ICU, e
 * next-intl recusa a mensagem com MALFORMED_ARGUMENT. Além disso, estrutura não é texto: ela é
 * a mesma em qualquer idioma. Só a frase de dentro é que muda.
 */
export function exampleDefinition(instructions: string): string {
  return JSON.stringify(
    { kind: "prompt", model: "gpt-5-mini", instructions },
    null,
    2,
  );
}
