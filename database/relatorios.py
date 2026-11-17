"""Consultas de relatórios e análises do Meu Financeiro.

Os valores são devolvidos em centavos (inteiros). Cada critério representa
uma perspectiva diferente e explícita:
- competência: despesa pela referência; compra no crédito pelo valor total
  no mês da compra;
- vencimento: despesa pelo vencimento; compras no crédito por parcela na
  data de vencimento da fatura;
- pagamento: despesas pela data em que foram pagas e pagamentos de faturas
  pela data do pagamento (fluxo de caixa, não novo gasto).

Este módulo é somente de leitura.
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from database.db import conectar

CRITERIOS = {"competencia", "vencimento", "pagamento"}
MESES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)


def validar_criterio(criterio: str) -> str:
    criterio = (criterio or "").strip().lower()
    if criterio not in CRITERIOS:
        raise ValueError("Critério inválido. Use competência, vencimento ou pagamento.")
    return criterio


def validar_mes(mes: str) -> str:
    try:
        ano_txt, mes_txt = str(mes).split("-", 1)
        ano, numero_mes = int(ano_txt), int(mes_txt)
        if ano < 1900 or not 1 <= numero_mes <= 12 or len(ano_txt) != 4:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError("O mês deve estar no formato AAAA-MM.")
    return f"{ano:04d}-{numero_mes:02d}"


def rotulo_mes(mes: str) -> str:
    mes = validar_mes(mes)
    ano, numero_mes = map(int, mes.split("-"))
    return f"{MESES[numero_mes - 1]}/{ano}"


def _meses_validos(meses: Iterable[str]) -> list[str]:
    if isinstance(meses, str):
        meses = [meses]
    return sorted({validar_mes(mes) for mes in (meses or [])})


def listar_meses_disponiveis(
    criterio: str,
    incluir_arquivadas: bool = True,
    hoje: date | None = None,
) -> list[str]:
    """Lista os meses que possuem registros para o critério selecionado."""
    criterio = validar_criterio(criterio)
    hoje = hoje or date.today()
    meses: set[str] = set()
    filtro_arquivo = "" if incluir_arquivadas else " AND arquivada = 0"

    with conectar() as conexao:
        if criterio == "competencia":
            sql = f"""SELECT DISTINCT COALESCE(
                NULLIF(referencia, ''), substr(COALESCE(data_despesa, vencimento), 1, 7)
            ) FROM contas WHERE 1=1 {filtro_arquivo}"""
            meses.update(row[0] for row in conexao.execute(sql).fetchall() if row[0])
            meses.update(row[0] for row in conexao.execute(
                "SELECT DISTINCT substr(data_compra, 1, 7) FROM compras_cartao WHERE ativa = 1"
            ).fetchall() if row[0])
            meses.update(row[0] for row in conexao.execute("""SELECT DISTINCT
                CASE WHEN a.tipo = 'Legado' THEN printf('%04d-%02d', f.ano, f.mes)
                     ELSE substr(a.criado_em, 1, 7) END
                FROM ajustes_fatura a JOIN faturas_cartao f ON f.id = a.fatura_id
                WHERE a.cancelado = 0""").fetchall() if row[0])

        elif criterio == "vencimento":
            sql = f"""SELECT DISTINCT substr(vencimento, 1, 7)
                FROM contas WHERE tem_vencimento = 1 {filtro_arquivo}"""
            meses.update(row[0] for row in conexao.execute(sql).fetchall() if row[0])
            meses.update(row[0] for row in conexao.execute("""SELECT DISTINCT
                substr(f.data_vencimento, 1, 7)
                FROM parcelas_cartao p
                JOIN compras_cartao cp ON cp.id = p.compra_id
                JOIN faturas_cartao f ON f.id = p.fatura_id
                WHERE p.ativa = 1 AND cp.ativa = 1""").fetchall() if row[0])
            meses.update(row[0] for row in conexao.execute("""SELECT DISTINCT
                substr(f.data_vencimento, 1, 7)
                FROM ajustes_fatura a JOIN faturas_cartao f ON f.id = a.fatura_id
                WHERE a.cancelado = 0""").fetchall() if row[0])

        else:  # pagamento
            sql = f"""SELECT DISTINCT substr(pago_em, 1, 7)
                FROM contas WHERE status = 'Pago' AND pago_em IS NOT NULL {filtro_arquivo}"""
            meses.update(row[0] for row in conexao.execute(sql).fetchall() if row[0])
            meses.update(row[0] for row in conexao.execute("""SELECT DISTINCT
                substr(data_pagamento, 1, 7) FROM pagamentos_fatura
                WHERE estornado = 0 AND data_pagamento IS NOT NULL""").fetchall() if row[0])

    # Mantém uma janela útil quando ainda não há histórico para o critério.
    if not meses:
        indice = hoje.year * 12 + hoje.month - 1
        for deslocamento in range(11, -1, -1):
            ano, mes_zero = divmod(indice - deslocamento, 12)
            meses.add(f"{ano:04d}-{mes_zero + 1:02d}")
    return sorted((validar_mes(m) for m in meses), reverse=True)


def listar_lancamentos_relatorio(
    criterio: str,
    meses: Iterable[str],
    incluir_arquivadas: bool = True,
) -> list[dict]:
    """Retorna lançamentos normalizados para um ou vários meses selecionados."""
    criterio = validar_criterio(criterio)
    meses_selecionados = _meses_validos(meses)
    if not meses_selecionados:
        return []

    placeholders = ",".join("?" for _ in meses_selecionados)
    linhas: list[dict] = []
    filtro_arquivo = "" if incluir_arquivadas else " AND arquivada = 0"

    def adicionar(mes, origem, descricao, categoria, data, valor, forma, detalhe):
        if mes in meses_selecionados:
            linhas.append({
                "mes": mes,
                "origem": origem,
                "descricao": descricao or "Sem descrição",
                "categoria": categoria or "Sem categoria",
                "data": (str(data)[:10] if data else ""),
                "valor_centavos": int(valor or 0),
                "forma_pagamento": forma or "Não informado",
                "detalhe": detalhe or "",
            })

    with conectar() as conexao:
        # Despesas: competência, vencimento ou data efetiva do pagamento.
        if criterio == "competencia":
            mes_expr = "COALESCE(NULLIF(referencia, ''), substr(COALESCE(data_despesa, vencimento), 1, 7))"
            data_expr = "COALESCE(data_despesa, vencimento)"
            where_extra = ""
        elif criterio == "vencimento":
            mes_expr = "substr(vencimento, 1, 7)"
            data_expr = "vencimento"
            where_extra = " AND tem_vencimento = 1"
        else:
            mes_expr = "substr(pago_em, 1, 7)"
            data_expr = "substr(pago_em, 1, 10)"
            where_extra = " AND status = 'Pago' AND pago_em IS NOT NULL"

        despesas = conexao.execute(f"""SELECT
                {mes_expr} AS mes,
                descricao, categoria, {data_expr} AS data,
                CAST(ROUND(valor * 100) AS INTEGER) AS valor_centavos,
                forma_pagamento, status, tem_vencimento, arquivada
            FROM contas
            WHERE {mes_expr} IN ({placeholders}) {filtro_arquivo} {where_extra}
            ORDER BY mes, data, descricao COLLATE NOCASE""",
            meses_selecionados,
        ).fetchall()
        for mes, descricao, categoria, data, valor, forma, status, tem_venc, arquivada in despesas:
            detalhe = f"{status} · {'Arquivada' if arquivada else 'Ativa'}"
            if criterio == "vencimento" and not tem_venc:
                continue
            adicionar(mes, "Despesa", descricao, categoria, data, valor, forma, detalhe)

        if criterio == "competencia":
            # Para competência, compra no crédito é reconhecida pelo valor total
            # no mês em que ocorreu, independentemente do número de parcelas.
            compras = conexao.execute(f"""SELECT
                    substr(cp.data_compra, 1, 7), cp.descricao,
                    COALESCE(NULLIF(TRIM(cp.categoria), ''), 'Sem categoria'),
                    cp.data_compra, cp.valor_total_centavos, cp.numero_parcelas,
                    c.nome
                FROM compras_cartao cp JOIN cartoes c ON c.id = cp.cartao_id
                WHERE cp.ativa = 1 AND substr(cp.data_compra, 1, 7) IN ({placeholders})
                ORDER BY cp.data_compra, cp.id""", meses_selecionados).fetchall()
            for mes, descricao, categoria, data, valor, parcelas, cartao in compras:
                detalhe = f"Compra no crédito · {int(parcelas)}x · {cartao}"
                adicionar(mes, "Cartão", descricao, categoria, data, valor,
                          "Cartão de crédito", detalhe)

            ajustes = conexao.execute(f"""SELECT
                    CASE WHEN a.tipo = 'Legado' THEN printf('%04d-%02d', f.ano, f.mes)
                         ELSE substr(a.criado_em, 1, 7) END AS mes,
                    a.tipo, a.descricao, a.valor_centavos, a.criado_em,
                    c.nome, f.ano, f.mes
                FROM ajustes_fatura a
                JOIN faturas_cartao f ON f.id = a.fatura_id
                JOIN cartoes c ON c.id = f.cartao_id
                WHERE a.cancelado = 0 AND (
                    (a.tipo = 'Legado' AND printf('%04d-%02d', f.ano, f.mes) IN ({placeholders}))
                    OR (a.tipo <> 'Legado' AND substr(a.criado_em, 1, 7) IN ({placeholders}))
                ) ORDER BY mes, a.id""",
                (*meses_selecionados, *meses_selecionados),
            ).fetchall()
            for mes, tipo, descricao, valor, criado, cartao, ano, numero_mes in ajustes:
                valor_ajuste = -int(valor) if tipo == "Crédito" else int(valor)
                if tipo == "Legado":
                    detalhe = f"Registro antigo importado · ciclo {int(numero_mes):02d}/{ano} · {cartao}"
                    data = f"{int(ano):04d}-{int(numero_mes):02d}-01"
                    categoria = "Fatura antiga importada"
                else:
                    detalhe = f"{tipo} lançado no cartão {cartao}"
                    data = criado
                    categoria = "Encargos e ajustes"
                adicionar(mes, "Cartão", descricao, categoria, data, valor_ajuste,
                          "Cartão de crédito", detalhe)

        elif criterio == "vencimento":
            parcelas = conexao.execute(f"""SELECT
                    substr(f.data_vencimento, 1, 7), cp.descricao,
                    COALESCE(NULLIF(TRIM(cp.categoria), ''), 'Sem categoria'),
                    f.data_vencimento, p.valor_centavos, p.numero_parcela,
                    p.total_parcelas, c.nome
                FROM parcelas_cartao p
                JOIN compras_cartao cp ON cp.id = p.compra_id
                JOIN faturas_cartao f ON f.id = p.fatura_id
                JOIN cartoes c ON c.id = cp.cartao_id
                WHERE p.ativa = 1 AND cp.ativa = 1
                  AND substr(f.data_vencimento, 1, 7) IN ({placeholders})
                ORDER BY f.data_vencimento, cp.descricao COLLATE NOCASE""",
                meses_selecionados,
            ).fetchall()
            for mes, descricao, categoria, data, valor, numero, total, cartao in parcelas:
                adicionar(mes, "Cartão", descricao, categoria, data, valor,
                          "Cartão de crédito", f"Parcela {numero}/{total} · {cartao}")

            ajustes = conexao.execute(f"""SELECT
                    substr(f.data_vencimento, 1, 7), a.tipo, a.descricao,
                    a.valor_centavos, f.data_vencimento, c.nome
                FROM ajustes_fatura a
                JOIN faturas_cartao f ON f.id = a.fatura_id
                JOIN cartoes c ON c.id = f.cartao_id
                WHERE a.cancelado = 0 AND substr(f.data_vencimento, 1, 7) IN ({placeholders})
                ORDER BY f.data_vencimento, a.id""", meses_selecionados).fetchall()
            for mes, tipo, descricao, valor, data, cartao in ajustes:
                valor_ajuste = -int(valor) if tipo == "Crédito" else int(valor)
                categoria = "Créditos e estornos" if tipo == "Crédito" else "Encargos e ajustes"
                adicionar(mes, "Cartão", descricao, categoria, data, valor_ajuste,
                          "Cartão de crédito", f"{tipo} na fatura · {cartao}")

        else:  # Pagamento: perspectiva de fluxo de caixa.
            pagamentos = conexao.execute(f"""SELECT
                    substr(pg.data_pagamento, 1, 7), pg.data_pagamento,
                    pg.valor_centavos, c.nome, f.ano, f.mes, pg.observacao
                FROM pagamentos_fatura pg
                JOIN faturas_cartao f ON f.id = pg.fatura_id
                JOIN cartoes c ON c.id = f.cartao_id
                WHERE pg.estornado = 0 AND pg.data_pagamento IS NOT NULL
                  AND substr(pg.data_pagamento, 1, 7) IN ({placeholders})
                ORDER BY pg.data_pagamento, pg.id""", meses_selecionados).fetchall()
            for mes, data, valor, cartao, ano, numero_mes, observacao in pagamentos:
                descricao = f"Pagamento da fatura {int(numero_mes):02d}/{ano} · {cartao}"
                adicionar(mes, "Cartão", descricao, "Pagamento de cartão", data,
                          valor, "Pagamento de fatura", observacao or "Saída efetiva")

    linhas.sort(key=lambda item: (item["mes"], item["data"], item["origem"], item["descricao"].casefold()))
    return linhas


def obter_dados_relatorio(
    criterio: str,
    meses: Iterable[str],
    incluir_arquivadas: bool = True,
) -> dict:
    """Consolida totais por mês/categoria, incluindo meses sem movimento."""
    meses_selecionados = _meses_validos(meses)
    lancamentos = listar_lancamentos_relatorio(
        criterio, meses_selecionados, incluir_arquivadas
    ) if meses_selecionados else []

    por_mes = {mes: 0 for mes in meses_selecionados}
    por_categoria: dict[str, int] = {}
    por_categoria_mes: dict[tuple[str, str], int] = {}
    for item in lancamentos:
        mes = item["mes"]
        categoria = item["categoria"]
        valor = int(item["valor_centavos"])
        por_mes[mes] = por_mes.get(mes, 0) + valor
        por_categoria[categoria] = por_categoria.get(categoria, 0) + valor
        chave = (categoria, mes)
        por_categoria_mes[chave] = por_categoria_mes.get(chave, 0) + valor

    total = sum(por_mes.values())
    quantidade_meses = len(meses_selecionados)
    media = round(total / quantidade_meses) if quantidade_meses else 0

    return {
        "criterio": validar_criterio(criterio),
        "meses": meses_selecionados,
        "lancamentos": lancamentos,
        "total_centavos": total,
        "media_mensal_centavos": media,
        "quantidade_meses": quantidade_meses,
        "quantidade_lancamentos": len(lancamentos),
        "por_mes": [
            {"mes": mes, "total_centavos": valor}
            for mes, valor in sorted(por_mes.items())
        ],
        "por_categoria": [
            {"categoria": categoria, "total_centavos": valor}
            for categoria, valor in sorted(
                por_categoria.items(), key=lambda par: par[1], reverse=True
            )
        ],
        "por_categoria_mes": [
            {"categoria": categoria, "mes": mes, "total_centavos": valor}
            for (categoria, mes), valor in sorted(por_categoria_mes.items())
        ],
    }
