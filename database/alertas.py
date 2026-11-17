"""Consultas de alertas financeiros do Meu Financeiro.

Somente leitura: identifica despesas e faturas em aberto por data de
vencimento. Nenhum status é alterado automaticamente.
"""

from __future__ import annotations

from datetime import date, timedelta

from database.cartoes import listar_faturas_mensais
from database.db import conectar, obter_configuracao


DIAS_ALERTA_PADRAO = 3
DIAS_ALERTA_MINIMO = 1
DIAS_ALERTA_MAXIMO = 60


def obter_dias_alerta() -> int:
    """Lê e valida a antecedência configurada para avisos futuros."""
    try:
        dias = int(obter_configuracao("dias_alerta", str(DIAS_ALERTA_PADRAO)))
    except (TypeError, ValueError):
        dias = DIAS_ALERTA_PADRAO
    return max(DIAS_ALERTA_MINIMO, min(dias, DIAS_ALERTA_MAXIMO))


def _classificar_vencimento(vencimento: str, hoje: date, limite: date) -> str | None:
    data_vencimento = date.fromisoformat(vencimento)
    if data_vencimento < hoje:
        return "atrasadas"
    if data_vencimento == hoje:
        return "hoje"
    if data_vencimento == hoje + timedelta(days=1):
        return "amanha"
    if hoje < data_vencimento <= limite:
        return "proximas"
    return None


def obter_alertas_financeiros(hoje: date | None = None, dias_antecedencia: int | None = None) -> dict:
    """Retorna despesas e faturas agrupadas por urgência.

    Categorias:
    - atrasadas: vencimento anterior a hoje e saldo em aberto;
    - hoje: vencimento igual a hoje;
    - amanha: vencimento no dia seguinte;
    - proximas: depois de amanhã até o limite configurado.

    Faturas parcialmente pagas aparecem somente pelo saldo restante. Despesas
    arquivadas/pagas e faturas sem saldo positivo não geram alertas.
    """
    hoje = hoje or date.today()
    if dias_antecedencia is None:
        dias_antecedencia = obter_dias_alerta()
    try:
        dias_antecedencia = int(dias_antecedencia)
    except (TypeError, ValueError):
        dias_antecedencia = DIAS_ALERTA_PADRAO
    dias_antecedencia = max(DIAS_ALERTA_MINIMO, min(dias_antecedencia, DIAS_ALERTA_MAXIMO))

    limite = hoje + timedelta(days=dias_antecedencia)
    grupos: dict[str, list[dict]] = {
        "atrasadas": [],
        "hoje": [],
        "amanha": [],
        "proximas": [],
    }

    with conectar() as conexao:
        despesas = conexao.execute(
            """SELECT id, descricao, categoria, forma_pagamento, vencimento,
                      CAST(ROUND(valor * 100) AS INTEGER) AS valor_centavos
               FROM contas
               WHERE arquivada = 0
                 AND status = 'Pendente'
                 AND tem_vencimento = 1
               ORDER BY vencimento, descricao COLLATE NOCASE"""
        ).fetchall()

    for id_despesa, descricao, categoria, forma, vencimento, valor_centavos in despesas:
        grupo = _classificar_vencimento(vencimento, hoje, limite)
        if grupo is None:
            continue
        diferenca = (date.fromisoformat(vencimento) - hoje).days
        grupos[grupo].append({
            "id": id_despesa,
            "tipo": "Despesa",
            "descricao": descricao,
            "detalhe": f"{categoria} · {forma}",
            "vencimento": vencimento,
            "valor_centavos": int(valor_centavos or 0),
            "dias_para_vencer": diferenca,
        })

    # O serviço de cartões já calcula totais, créditos e pagamentos em centavos.
    # Mantemos essa regra centralizada para não duplicar cálculos financeiros.
    for fatura in listar_faturas_mensais():
        id_fatura, id_cartao, nome_cartao, ano, mes = fatura[:5]
        vencimento = fatura[6]
        total_centavos = int(fatura[7] or 0)
        pago_centavos = int(fatura[8] or 0)
        saldo_centavos = total_centavos - pago_centavos
        if saldo_centavos <= 0:
            continue

        grupo = _classificar_vencimento(vencimento, hoje, limite)
        if grupo is None:
            continue
        diferenca = (date.fromisoformat(vencimento) - hoje).days
        grupos[grupo].append({
            "id": id_fatura,
            "tipo": "Fatura",
            "descricao": f"{nome_cartao} · {int(mes):02d}/{int(ano)}",
            "detalhe": "Fatura de cartão de crédito",
            "vencimento": vencimento,
            "valor_centavos": saldo_centavos,
            "dias_para_vencer": diferenca,
        })

    for itens in grupos.values():
        itens.sort(key=lambda item: (item["vencimento"], item["tipo"], item["descricao"].casefold()))

    total = sum(len(itens) for itens in grupos.values())
    return {
        "hoje": hoje.isoformat(),
        "dias_antecedencia": dias_antecedencia,
        "limite": limite.isoformat(),
        "atrasadas": grupos["atrasadas"],
        "hoje_itens": grupos["hoje"],
        "amanha": grupos["amanha"],
        "proximas": grupos["proximas"],
        "total": total,
        "total_atrasadas": len(grupos["atrasadas"]),
        "total_hoje": len(grupos["hoje"]),
        "total_amanha": len(grupos["amanha"]),
        "total_proximas": len(grupos["proximas"]),
    }
