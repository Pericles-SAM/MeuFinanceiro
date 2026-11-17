"""Consultas consolidadas para o dashboard do Meu Financeiro.

Este módulo é somente de leitura: não altera despesas, compras, parcelas ou
pagamentos. Valores monetários são devolvidos em centavos (inteiros).
"""

from __future__ import annotations

from datetime import date

from database.db import conectar, obter_configuracao

MESES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)


def _validar_referencia(referencia: str) -> tuple[int, int]:
    try:
        ano_texto, mes_texto = str(referencia).split("-", maxsplit=1)
        ano, mes = int(ano_texto), int(mes_texto)
        if ano < 1900 or not 1 <= mes <= 12:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise ValueError("A referência deve estar no formato AAAA-MM.")
    return ano, mes


def rotulo_referencia(referencia: str) -> str:
    ano, mes = _validar_referencia(referencia)
    return f"{MESES[mes - 1]}/{ano}"


def _somar_despesas(conexao, referencia: str, status: str | None = None) -> int:
    sql = """SELECT COALESCE(SUM(CAST(ROUND(valor * 100) AS INTEGER)), 0)
             FROM contas WHERE arquivada = 0 AND referencia = ?"""
    parametros: list[object] = [referencia]
    if status:
        sql += " AND status = ?"
        parametros.append(status)
    return int(conexao.execute(sql, parametros).fetchone()[0] or 0)


def _somar_parcelas_cartao(conexao, ano: int, mes: int) -> int:
    return int(conexao.execute("""SELECT COALESCE(SUM(p.valor_centavos), 0)
        FROM parcelas_cartao p
        JOIN compras_cartao cp ON cp.id = p.compra_id
        JOIN faturas_cartao f ON f.id = p.fatura_id
        WHERE p.ativa = 1 AND cp.ativa = 1 AND f.ano = ? AND f.mes = ?""",
        (ano, mes),
    ).fetchone()[0] or 0)


def _somar_ajustes_cartao(conexao, ano: int, mes: int) -> tuple[int, int]:
    """Retorna (encargos+legado, créditos), ambos em centavos positivos."""
    linha = conexao.execute("""SELECT
        COALESCE(SUM(CASE WHEN a.tipo IN ('Encargo', 'Legado') THEN a.valor_centavos ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN a.tipo = 'Crédito' THEN a.valor_centavos ELSE 0 END), 0)
        FROM ajustes_fatura a
        JOIN faturas_cartao f ON f.id = a.fatura_id
        WHERE a.cancelado = 0 AND f.ano = ? AND f.mes = ?""", (ano, mes)).fetchone()
    return int(linha[0] or 0), int(linha[1] or 0)


def _faturas(conexao) -> list[tuple]:
    return conexao.execute("""SELECT
        f.id, f.cartao_id, c.nome, f.ano, f.mes,
        f.data_fechamento, f.data_vencimento,
        COALESCE((SELECT SUM(p.valor_centavos)
                  FROM parcelas_cartao p
                  JOIN compras_cartao cp ON cp.id = p.compra_id
                  WHERE p.fatura_id = f.id AND p.ativa = 1 AND cp.ativa = 1), 0)
        + COALESCE((SELECT SUM(CASE WHEN a.tipo = 'Crédito' THEN -a.valor_centavos
                                    ELSE a.valor_centavos END)
                    FROM ajustes_fatura a
                    WHERE a.fatura_id = f.id AND a.cancelado = 0), 0) AS total_centavos,
        COALESCE((SELECT SUM(pg.valor_centavos)
                  FROM pagamentos_fatura pg
                  WHERE pg.fatura_id = f.id AND pg.estornado = 0), 0) AS pago_centavos
        FROM faturas_cartao f
        JOIN cartoes c ON c.id = f.cartao_id
        ORDER BY f.data_vencimento, c.nome COLLATE NOCASE""").fetchall()


def obter_referencias_disponiveis(hoje: date | None = None) -> list[str]:
    """Lista meses usados nos dados e uma janela ao redor do mês atual."""
    hoje = hoje or date.today()
    referencias: set[str] = set()
    with conectar() as conexao:
        for (ref,) in conexao.execute(
            "SELECT DISTINCT referencia FROM contas WHERE referencia IS NOT NULL AND referencia <> ''"
        ).fetchall():
            try:
                _validar_referencia(ref)
                referencias.add(ref)
            except ValueError:
                continue
        for ano, mes in conexao.execute(
            "SELECT DISTINCT ano, mes FROM faturas_cartao"
        ).fetchall():
            referencias.add(f"{int(ano):04d}-{int(mes):02d}")

    indice_atual = hoje.year * 12 + hoje.month - 1
    for deslocamento in range(-12, 13):
        indice = indice_atual + deslocamento
        ano, mes_zero = divmod(indice, 12)
        referencias.add(f"{ano:04d}-{mes_zero + 1:02d}")
    return sorted(referencias, reverse=True)


def obter_dados_dashboard(
    referencia: str,
    hoje: date | None = None,
    dias_alerta: int | None = None,
) -> dict:
    """Consolida indicadores, categorias, tendência e vencimentos do período.

    Definições para evitar dupla contagem:
    - gastos do período = despesas pela referência + parcelas alocadas ao ciclo
      mensal do cartão + encargos/legados - créditos;
    - pagamentos de fatura aparecem apenas no fluxo de saídas pagas, nunca são
      somados novamente aos gastos;
    - despesas arquivadas e compras/parcelas canceladas ficam fora dos totais.
    """
    ano, mes = _validar_referencia(referencia)
    hoje = hoje or date.today()
    if dias_alerta is None:
        try:
            dias_alerta = int(obter_configuracao("dias_alerta", "3"))
        except (TypeError, ValueError):
            dias_alerta = 3
    dias_alerta = max(0, min(int(dias_alerta), 60))
    limite_alerta = date.fromordinal(hoje.toordinal() + dias_alerta).isoformat()
    hoje_iso = hoje.isoformat()

    with conectar() as conexao:
        despesas_total = _somar_despesas(conexao, referencia)
        despesas_pendentes = _somar_despesas(conexao, referencia, "Pendente")
        despesas_pagas_por_pagamento = int(conexao.execute("""SELECT
            COALESCE(SUM(CAST(ROUND(valor * 100) AS INTEGER)), 0)
            FROM contas WHERE arquivada = 0 AND status = 'Pago'
              AND substr(COALESCE(pago_em, ''), 1, 7) = ?""", (referencia,)).fetchone()[0] or 0)

        parcelas_cartao = _somar_parcelas_cartao(conexao, ano, mes)
        encargos_cartao, creditos_cartao = _somar_ajustes_cartao(conexao, ano, mes)
        total_gastos = despesas_total + parcelas_cartao + encargos_cartao - creditos_cartao

        categorias: dict[str, int] = {}
        for categoria, total in conexao.execute("""SELECT
                COALESCE(NULLIF(TRIM(categoria), ''), 'Sem categoria'),
                COALESCE(SUM(CAST(ROUND(valor * 100) AS INTEGER)), 0)
            FROM contas WHERE arquivada = 0 AND referencia = ?
            GROUP BY COALESCE(NULLIF(TRIM(categoria), ''), 'Sem categoria')""", (referencia,)).fetchall():
            categorias[categoria] = categorias.get(categoria, 0) + int(total or 0)

        for categoria, total in conexao.execute("""SELECT
                COALESCE(NULLIF(TRIM(cp.categoria), ''), 'Sem categoria'),
                COALESCE(SUM(p.valor_centavos), 0)
            FROM parcelas_cartao p
            JOIN compras_cartao cp ON cp.id = p.compra_id
            JOIN faturas_cartao f ON f.id = p.fatura_id
            WHERE p.ativa = 1 AND cp.ativa = 1 AND f.ano = ? AND f.mes = ?
            GROUP BY COALESCE(NULLIF(TRIM(cp.categoria), ''), 'Sem categoria')""", (ano, mes)).fetchall():
            categorias[categoria] = categorias.get(categoria, 0) + int(total or 0)

        if encargos_cartao:
            categorias["Encargos e faturas antigas"] = categorias.get("Encargos e faturas antigas", 0) + encargos_cartao

        faturas = _faturas(conexao)
        faturas_periodo = [f for f in faturas if int(f[3]) == ano and int(f[4]) == mes]
        saldo_faturas_abertas = sum(max(int(f[7]) - int(f[8]), 0) for f in faturas_periodo)
        creditos_disponiveis = sum(max(int(f[8]) - int(f[7]), 0) for f in faturas_periodo)

        pagamentos_cartao = int(conexao.execute("""SELECT COALESCE(SUM(valor_centavos), 0)
            FROM pagamentos_fatura
            WHERE estornado = 0 AND substr(COALESCE(data_pagamento, ''), 1, 7) = ?""",
            (referencia,),
        ).fetchone()[0] or 0)
        saidas_pagas = despesas_pagas_por_pagamento + pagamentos_cartao

        despesas_atrasadas = conexao.execute("""SELECT id, descricao, vencimento,
                CAST(ROUND(valor * 100) AS INTEGER), categoria, forma_pagamento
            FROM contas
            WHERE arquivada = 0 AND status = 'Pendente' AND tem_vencimento = 1
              AND vencimento < ?
            ORDER BY vencimento, id""", (hoje_iso,)).fetchall()
        despesas_proximas = conexao.execute("""SELECT id, descricao, vencimento,
                CAST(ROUND(valor * 100) AS INTEGER), categoria, forma_pagamento
            FROM contas
            WHERE arquivada = 0 AND status = 'Pendente' AND tem_vencimento = 1
              AND vencimento BETWEEN ? AND ?
            ORDER BY vencimento, id LIMIT 30""", (hoje_iso, limite_alerta)).fetchall()

        tendencia = []
        indice_base = ano * 12 + mes - 1
        for deslocamento in range(5, -1, -1):
            indice = indice_base - deslocamento
            ano_item, mes_zero = divmod(indice, 12)
            mes_item = mes_zero + 1
            ref_item = f"{ano_item:04d}-{mes_item:02d}"
            despesas_item = _somar_despesas(conexao, ref_item)
            parcelas_item = _somar_parcelas_cartao(conexao, ano_item, mes_item)
            encargos_item, creditos_item = _somar_ajustes_cartao(conexao, ano_item, mes_item)
            tendencia.append({
                "referencia": ref_item,
                "rotulo": f"{MESES[mes_item - 1][:3]}/{str(ano_item)[-2:]}",
                "total_centavos": despesas_item + parcelas_item + encargos_item - creditos_item,
            })

        cartoes_ativos = int(conexao.execute(
            "SELECT COUNT(*) FROM cartoes WHERE ativo = 1"
        ).fetchone()[0])
        saldo_futuro = sum(
            max(int(f[7]) - int(f[8]), 0)
            for f in faturas
            if f[6] >= hoje_iso
        )

    proximos = []
    for item in despesas_proximas:
        id_item, descricao, vencimento, valor, categoria, forma = item
        proximos.append({
            "tipo": "Despesa",
            "descricao": descricao,
            "vencimento": vencimento,
            "valor_centavos": int(valor),
            "detalhe": f"{categoria} · {forma}",
        })

    faturas_atrasadas = []
    faturas_proximas = []
    for f in faturas:
        saldo = int(f[7]) - int(f[8])
        if saldo <= 0:
            continue
        item = {
            "tipo": "Fatura",
            "descricao": f"{f[2]} · {MESES[int(f[4]) - 1]}/{f[3]}",
            "vencimento": f[6],
            "valor_centavos": saldo,
            "detalhe": "Fatura de cartão de crédito",
        }
        if f[6] < hoje_iso:
            faturas_atrasadas.append(item)
        elif f[6] <= limite_alerta:
            faturas_proximas.append(item)

    proximos.extend(faturas_proximas)
    proximos.sort(key=lambda item: (item["vencimento"], item["tipo"], item["descricao"]))
    proximos = proximos[:10]

    categorias_ordenadas = [
        {"categoria": nome, "total_centavos": total}
        for nome, total in sorted(categorias.items(), key=lambda par: par[1], reverse=True)
        if total > 0
    ]

    return {
        "referencia": referencia,
        "dias_alerta": dias_alerta,
        "total_gastos_centavos": total_gastos,
        "despesas_sem_credito_centavos": despesas_total,
        "parcelas_cartao_centavos": parcelas_cartao,
        "encargos_cartao_centavos": encargos_cartao,
        "creditos_cartao_centavos": creditos_cartao,
        "despesas_pendentes_centavos": despesas_pendentes,
        "saldo_faturas_abertas_centavos": saldo_faturas_abertas,
        "creditos_disponiveis_centavos": creditos_disponiveis,
        "saidas_pagas_centavos": saidas_pagas,
        "despesas_pagas_centavos": despesas_pagas_por_pagamento,
        "pagamentos_cartao_centavos": pagamentos_cartao,
        "obrigacoes_atrasadas": len(despesas_atrasadas) + len(faturas_atrasadas),
        "despesas_atrasadas": len(despesas_atrasadas),
        "faturas_atrasadas": len(faturas_atrasadas),
        "cartoes_ativos": cartoes_ativos,
        "saldo_futuro_centavos": saldo_futuro,
        "proximos_vencimentos": proximos,
        "categorias": categorias_ordenadas,
        "tendencia": tendencia,
    }
