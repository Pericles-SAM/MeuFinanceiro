"""Interface de relatórios e análises financeiras."""

from datetime import date

import pandas as pd
import streamlit as st

from components.formatacao import formatar_moeda
from database.relatorios import (
    listar_meses_disponiveis,
    obter_dados_relatorio,
    rotulo_mes,
)

CRITERIOS_TEXTO = {
    "Competência": "competencia",
    "Vencimento": "vencimento",
    "Pagamento": "pagamento",
}


def _valor_reais(centavos: int) -> float:
    return int(centavos) / 100


def _rotulo_criterio(criterio: str) -> tuple[str, str]:
    if criterio == "competencia":
        return "Total por competência", (
            "Despesas são agrupadas pelo mês de referência. Compras no crédito entram "
            "pelo valor total no mês em que foram realizadas, uma única vez."
        )
    if criterio == "vencimento":
        return "Total por vencimento", (
            "Despesas usam a data de vencimento; cartões usam cada parcela na data de "
            "vencimento da respectiva fatura."
        )
    return "Total pago no período", (
        "Mostra saídas efetivas: despesas pela data de pagamento e pagamentos de faturas "
        "pela data em que foram realizados. Pagamento de fatura é fluxo de caixa, não um novo gasto."
    )


def _preparar_dados(dados: dict, categoria_selecionada: str) -> list[dict]:
    lancamentos = dados["lancamentos"]
    if categoria_selecionada != "Todas":
        lancamentos = [
            item for item in lancamentos
            if item["categoria"] == categoria_selecionada
        ]
    return lancamentos


def mostrar_relatorios():
    st.title("📊 Relatórios e análises")
    st.caption("Explore seus gastos, compare períodos e entenda como seu dinheiro está sendo utilizado.")

    col_criterio, col_arquivadas = st.columns([1.4, 1])
    with col_criterio:
        criterio_label = st.segmented_control(
            "Analisar por",
            options=list(CRITERIOS_TEXTO),
            default="Competência",
            key="relatorios_criterio",
            selection_mode="single",
            width="stretch",
        )
        criterio = CRITERIOS_TEXTO[criterio_label or "Competência"]
    with col_arquivadas:
        incluir_arquivadas = st.checkbox(
            "Incluir despesas arquivadas",
            value=True,
            key="relatorios_incluir_arquivadas",
            help="Inclui despesas arquivadas na análise histórica. Compras de cartão canceladas continuam fora dos totais.",
        )

    meses_disponiveis = listar_meses_disponiveis(criterio, incluir_arquivadas)
    referencia_atual = date.today().strftime("%Y-%m")
    padrao = [mes for mes in meses_disponiveis if mes <= referencia_atual][:3]
    if not padrao:
        padrao = meses_disponiveis[:3]

    meses_selecionados = st.multiselect(
        "Selecione os meses para analisar (pode escolher meses não consecutivos)",
        options=meses_disponiveis,
        default=padrao,
        format_func=rotulo_mes,
        key=f"relatorios_meses_{criterio}_{int(incluir_arquivadas)}",
        placeholder="Escolha um ou mais meses",
    )

    if not meses_selecionados:
        st.info("Selecione pelo menos um mês para gerar a análise.")
        return

    dados = obter_dados_relatorio(criterio, meses_selecionados, incluir_arquivadas)
    categorias = sorted({item["categoria"] for item in dados["lancamentos"]}, key=str.casefold)
    categoria_selecionada = st.selectbox(
        "Categoria",
        options=["Todas", *categorias],
        key=f"relatorios_categoria_{criterio}",
    )
    lancamentos = _preparar_dados(dados, categoria_selecionada)

    por_mes = {mes: 0 for mes in dados["meses"]}
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

    total_centavos = sum(por_mes.values())
    media_centavos = round(total_centavos / len(por_mes)) if por_mes else 0
    titulo_total, explicacao = _rotulo_criterio(criterio)

    st.divider()
    st.caption(explicacao)
    col_total, col_media, col_meses, col_lancamentos = st.columns(4)
    col_total.metric(titulo_total, formatar_moeda(_valor_reais(total_centavos)))
    col_media.metric("Média por mês selecionado", formatar_moeda(_valor_reais(media_centavos)))
    col_meses.metric("Meses comparados", len(por_mes))
    col_lancamentos.metric("Lançamentos", len(lancamentos))

    if not lancamentos:
        st.info("Não existem lançamentos para os filtros selecionados. Os meses sem movimento permanecem na comparação com valor zero.")
        st.subheader("Comparação mensal")
        tabela_vazia = pd.DataFrame({
            "Mês": [rotulo_mes(mes) for mes in por_mes],
            "Total (R$)": [0.0 for _ in por_mes],
        }).set_index("Mês")
        st.bar_chart(tabela_vazia)
        return

    st.divider()
    col_mensal, col_categoria = st.columns(2, gap="large")

    with col_mensal:
        st.subheader("Comparação entre meses")
        tabela_mensal = pd.DataFrame({
            "Mês": [rotulo_mes(mes) for mes in sorted(por_mes)],
            "Total (R$)": [_valor_reais(por_mes[mes]) for mes in sorted(por_mes)],
        }).set_index("Mês")
        st.bar_chart(tabela_mensal, y="Total (R$)", use_container_width=True)
        st.caption("Os meses são comparados individualmente, mesmo quando não são consecutivos.")

    with col_categoria:
        st.subheader("Distribuição por categoria")
        categorias_ordenadas = sorted(por_categoria.items(), key=lambda par: par[1], reverse=True)
        tabela_categoria = pd.DataFrame({
            "Categoria": [item[0] for item in categorias_ordenadas],
            "Total (R$)": [_valor_reais(item[1]) for item in categorias_ordenadas],
        }).set_index("Categoria")
        st.bar_chart(tabela_categoria, y="Total (R$)", use_container_width=True)
        st.caption("Créditos e estornos aparecem como valores negativos nas categorias correspondentes.")

    st.divider()
    st.subheader("Comparação por categoria e mês")
    matriz = pd.DataFrame(
        0.0,
        index=sorted(por_categoria, key=str.casefold),
        columns=[rotulo_mes(mes) for mes in sorted(por_mes)],
    )
    for (categoria, mes), valor in por_categoria_mes.items():
        matriz.loc[categoria, rotulo_mes(mes)] = _valor_reais(valor)
    matriz.index.name = "Categoria"
    st.dataframe(
        matriz,
        use_container_width=True,
        column_config={
            coluna: st.column_config.NumberColumn(coluna, format="R$ %.2f")
            for coluna in matriz.columns
        },
    )

    st.divider()
    st.subheader("Detalhamento dos lançamentos")
    st.caption("Consulte a origem, categoria, data e descrição de cada valor incluído na análise.")
    linhas_tabela = []
    for item in sorted(lancamentos, key=lambda x: (x["mes"], x["data"], x["descricao"].casefold()), reverse=True):
        linhas_tabela.append({
            "Mês": rotulo_mes(item["mes"]),
            "Origem": item["origem"],
            "Descrição": item["descricao"],
            "Categoria": item["categoria"],
            "Data": item["data"],
            "Forma": item["forma_pagamento"],
            "Valor": formatar_moeda(_valor_reais(item["valor_centavos"])),
            "Detalhe": item["detalhe"],
        })
    tabela_detalhes = pd.DataFrame(linhas_tabela)
    st.dataframe(tabela_detalhes, use_container_width=True, hide_index=True)

    csv = tabela_detalhes.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "⬇️ Exportar lançamentos (CSV)",
        data=csv,
        file_name=f"meu_financeiro_relatorio_{criterio}.csv",
        mime="text/csv",
        use_container_width=False,
    )
