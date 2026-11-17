"""Compatibilidade com versões anteriores: a área Contas agora se chama Despesas."""

from modulos.despesas import mostrar_despesas


def mostrar_contas():
    mostrar_despesas()
