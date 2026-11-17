"""Contador financeiro animado para o Meu Financeiro (Streamlit Components V2)."""

from __future__ import annotations

import math
from typing import Any

import streamlit as st


out = st.components.v2.component(
    "meu-financeiro-count-up.meu_financeiro_count_up",
    js="index-*.js",
    html='<div class="react-root"></div>',
)


def meu_financeiro_count_up(
    valor: float,
    rotulo: str,
    *,
    prefixo: str = "R$",
    sufixo: str = "",
    duracao: float = 1.2,
    casas_decimais: int = 2,
    key: str | int | None = None,
) -> Any:
    """Renderiza um número animado no formato brasileiro.

    Parameters
    ----------
    valor:
        Valor numérico que será exibido.
    rotulo:
        Texto descritivo apresentado acima do valor.
    prefixo:
        Texto antes do número. Use "R$" para valores monetários ou "".
    sufixo:
        Texto depois do número, por exemplo "%".
    duracao:
        Duração da animação em segundos. Aceita valores entre 0 e 10.
    casas_decimais:
        Quantidade de casas decimais, de 0 a 4.
    key:
        Chave opcional e estável para identificar a instância do componente.

    Returns
    -------
    ComponentResult
        Resultado retornado pelo componente Streamlit V2.
    """
    if isinstance(valor, bool):
        raise TypeError("O valor precisa ser numérico, não booleano.")

    try:
        valor_numerico = float(valor)
    except (TypeError, ValueError) as erro:
        raise TypeError("O valor precisa ser um número válido.") from erro

    if not math.isfinite(valor_numerico):
        raise ValueError("O valor precisa ser finito.")

    rotulo = str(rotulo).strip()
    if not rotulo:
        raise ValueError("Informe um rótulo para o indicador.")

    try:
        duracao_numerica = float(duracao)
    except (TypeError, ValueError) as erro:
        raise TypeError("A duração precisa ser numérica.") from erro

    if not math.isfinite(duracao_numerica) or not 0 <= duracao_numerica <= 10:
        raise ValueError("A duração deve estar entre 0 e 10 segundos.")

    if isinstance(casas_decimais, bool) or not isinstance(casas_decimais, int):
        raise TypeError("casas_decimais precisa ser um número inteiro.")

    if not 0 <= casas_decimais <= 4:
        raise ValueError("casas_decimais deve estar entre 0 e 4.")

    dados = {
        "valor": valor_numerico,
        "rotulo": rotulo,
        "prefixo": str(prefixo),
        "sufixo": str(sufixo),
        "duracao": duracao_numerica,
        "casas_decimais": casas_decimais,
    }

    return out(key=key, data=dados)


__all__ = ["meu_financeiro_count_up"]
