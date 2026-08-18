"""O saneamento que roda ANTES de gravar — barreira estrutural, não faxina.

POR QUE ANTES E NÃO DEPOIS. Uma passada de limpeza sobre o que já foi gravado significa que o
valor cru existiu em algo durável — e num container WORM ele existiria para sempre. A redação
acontece no caminho de escrita ou não acontece.

O QUE ELE É, dito sem eufemismo: um bloqueio DETERMINÍSTICO de padrões estruturais. Ele reconhece
a FORMA de um documento (CPF com dígito verificador, cartão por Luhn, e-mail, telefone, data de
nascimento), não o significado de um texto. Isso o torna incompleto por construção: um prontuário
escrito em prosa passa inteiro. É barreira, não garantia — e o produto continua não podendo ser
apontado para dado de paciente.

Dizer isso aqui é parte do controle. Um redator apresentado como "proteção de PII" faz alguém
concluir que pode mandar qualquer coisa; apresentado como o que é, ele protege do acidente sem
autorizar o hábito.

O CPF É VALIDADO, não só reconhecido pela forma: `000.000.000-00` tem forma de CPF e não é um.
Mascarar toda sequência de 11 dígitos apagaria número de protocolo, id de pedido e telefone com
DDD — e um redator que estraga dado legítimo é desligado na primeira semana.
"""

from __future__ import annotations

import re

MASCARA = "«redigido:{tipo}»"

_CPF = re.compile(r"\b(\d{3})\.?(\d{3})\.?(\d{3})-?(\d{2})\b")
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
#: Telefone brasileiro com DDD, com ou sem o 9. Exige o parêntese OU o hífen para não engolir
#: qualquer número de 10-11 dígitos — id de pedido tem essa cara.
_FONE = re.compile(r"\b(?:\(\d{2}\)\s?|\d{2}\s)?9?\d{4}-\d{4}\b")
_NASC = re.compile(r"\b(0?[1-9]|[12]\d|3[01])/(0?[1-9]|1[0-2])/(19|20)\d{2}\b")
#: Cartão: 13–19 dígitos, com separadores opcionais. Confirmado por Luhn antes de mascarar.
_CARTAO = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _cpf_valido(digitos: str) -> bool:
    """Dígitos verificadores do CPF (mod 11). Rejeita os repetidos, que passam na conta."""
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        dv = (soma * 10) % 11 % 10
        if dv != int(digitos[tamanho]):
            return False
    return True


def _luhn(digitos: str) -> bool:
    if not 13 <= len(digitos) <= 19:
        return False
    total, alt = 0, False
    for ch in reversed(digitos):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def redact(texto: str) -> tuple[str, list[str]]:
    """`(texto saneado, tipos encontrados)`.

    Os TIPOS sobem, o conteúdo não. É o que permite registrar "havia um CPF aqui" na trilha sem
    pôr o CPF na trilha — que seria trocar um vazamento por um vazamento imutável.
    """
    achados: list[str] = []
    if not texto:
        return texto, achados

    def marca(tipo: str) -> str:
        if tipo not in achados:
            achados.append(tipo)
        return MASCARA.format(tipo=tipo)

    def sub_cpf(m: re.Match) -> str:
        digitos = "".join(m.groups())
        return marca("cpf") if _cpf_valido(digitos) else m.group(0)

    def sub_cartao(m: re.Match) -> str:
        digitos = re.sub(r"\D", "", m.group(0))
        # Um CPF válido também passa por aqui: já foi mascarado antes, então o que chega é outra
        # coisa. Luhn evita mascarar sequência longa que não é cartão.
        return marca("cartao") if _luhn(digitos) else m.group(0)

    saida = _CPF.sub(sub_cpf, texto)
    saida = _CNPJ.sub(lambda m: marca("cnpj"), saida)
    saida = _EMAIL.sub(lambda m: marca("email"), saida)
    saida = _NASC.sub(lambda m: marca("nascimento"), saida)
    saida = _FONE.sub(lambda m: marca("telefone"), saida)
    saida = _CARTAO.sub(sub_cartao, saida)
    return saida, achados
