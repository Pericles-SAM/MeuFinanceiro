"""Dashboard principal do Meu Financeiro."""

from datetime import date

import pandas as pd
import streamlit as st

from components.formatacao import formatar_moeda
from database.alertas import obter_alertas_financeiros
from database.cartoes import calcular_situacao_fatura, listar_faturas_mensais
from database.dashboard import (
    obter_dados_dashboard,
    obter_referencias_disponiveis,
    rotulo_referencia,
)

try:
    from meu_financeiro_count_up import meu_financeiro_count_up
except ImportError:  # Mantém o dashboard funcional se o componente React não estiver instalado.
    meu_financeiro_count_up = None


def _indicador(container, rotulo, valor_centavos, chave):
    valor = int(valor_centavos) / 100
    if meu_financeiro_count_up is not None:
        with container:
            meu_financeiro_count_up(
                valor,
                rotulo,
                prefixo="R$",
                duracao=1.25,
                casas_decimais=2,
                key=chave,
            )
    else:
        container.metric(rotulo, formatar_moeda(valor))


def _formatar_data(data_iso):
    return date.fromisoformat(data_iso).strftime("%d/%m/%Y")


def _rotulo_prazo(dias):
    if dias < 0:
        quantidade = abs(dias)
        return f"Atrasada há {quantidade} dia(s)"
    if dias == 0:
        return "Vence hoje"
    if dias == 1:
        return "Vence amanhã"
    return f"Vence em {dias} dias"


def _mostrar_resumo_alertas(alertas):
    st.subheader("🔔 Situação dos vencimentos")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Atrasadas", alertas["total_atrasadas"])
    col2.metric("Vencem hoje", alertas["total_hoje"])
    col3.metric("Vencem amanhã", alertas["total_amanha"])
    col4.metric(f"Próximas ({alertas['dias_antecedencia']} dias)", alertas["total_proximas"])

    if alertas["total_atrasadas"]:
        st.error(
            f"Existem {alertas['total_atrasadas']} obrigação(ões) vencida(s) "
            "com saldo pendente. Confira os detalhes abaixo."
        )
    elif alertas["total"] == 0:
        st.success("Nenhuma obrigação financeira exige atenção neste momento.")
    elif alertas["total_hoje"]:
        st.warning("Você tem obrigações com vencimento hoje.")


def _mostrar_grupo_alertas(titulo, itens, estado="collapsed"):
    if not itens:
        return

    with st.expander(f"{titulo} · {len(itens)}", expanded=(estado == "expanded")):
        for item in itens:
            with st.container(border=True):
                col_data, col_info, col_valor = st.columns(
                    [1.25, 3, 1.4], vertical_alignment="center"
                )
                with col_data:
                    st.caption(_rotulo_prazo(item["dias_para_vencer"]))
                    st.write(f"**{_formatar_data(item['vencimento'])}**")
                with col_info:
                    st.write(f"**{item['descricao']}**")
                    st.caption(f"{item['tipo']} · {item['detalhe']}")
                with col_valor:
                    st.caption("Saldo a pagar")
                    st.write(f"**{formatar_moeda(item['valor_centavos'] / 100)}**")


def _mostrar_alertas_detalhados(alertas):
    st.subheader("📅 Alertas e próximos vencimentos")
    st.caption(
        "Os avisos incluem despesas e faturas de cartão. Faturas parcialmente "
        "pagas exibem somente o saldo restante."
    )

    if alertas["total"] == 0:
        st.info("Não há vencimentos pendentes dentro das faixas de alerta.")
        return

    _mostrar_grupo_alertas("🔴 Obrigações atrasadas", alertas["atrasadas"], "expanded")
    _mostrar_grupo_alertas("🟠 Vencem hoje", alertas["hoje_itens"], "expanded")
    _mostrar_grupo_alertas("🔵 Vencem amanhã", alertas["amanha"])
    _mostrar_grupo_alertas(
        f"Próximos {alertas['dias_antecedencia']} dias", alertas["proximas"]
    )


def _abrir_fatura_no_cartoes(id_fatura, id_cartao, ano, mes):
    """Navega do Dashboard diretamente para a fatura e seus itens."""
    st.session_state["pagina_atual"] = "Cartões"
    st.session_state["secao_cartoes"] = "Faturas"
    st.session_state["fatura_dashboard_selecionada"] = int(id_fatura)
    st.session_state["filtro_faturas_cartao"] = int(id_cartao)
    st.session_state["filtro_faturas_ano"] = int(ano)
    st.session_state["filtro_faturas_mes"] = int(mes)


def _mostrar_cartoes(dados, referencia):
    st.subheader("Resumo dos cartões")
    col1, col2, col3 = st.columns(3)
    col1.metric("Cartões ativos", dados["cartoes_ativos"])
    col2.metric(
        "Faturas em aberto no período",
        formatar_moeda(dados["saldo_faturas_abertas_centavos"] / 100),
    )
    col3.metric(
        "Comprometimento futuro",
        formatar_moeda(dados["saldo_futuro_centavos"] / 100),
    )
    if dados["creditos_disponiveis_centavos"] > 0:
        st.caption(
            "Créditos disponíveis nas faturas do período: "
            + formatar_moeda(dados["creditos_disponiveis_centavos"] / 100)
        )

    ano, mes = map(int, referencia.split("-"))
    faturas_periodo = listar_faturas_mensais(ano=ano, mes=mes)
    st.markdown(f"**Faturas de {rotulo_referencia(referencia)}**")
    st.caption(
        "Abra uma fatura para conferir compras, parcelas, encargos, créditos e pagamentos "
        "que compõem o valor apresentado."
    )

    if not faturas_periodo:
        st.info("Nenhuma fatura de cartão foi gerada para este período.")
        return

    for fatura in faturas_periodo:
        (id_fatura, id_cartao, nome, ano_fatura, mes_fatura,
         fechamento, vencimento, total, pago) = fatura
        situacao, saldo = calcular_situacao_fatura(total, pago, vencimento)
        with st.container(border=True):
            col_nome, col_total, col_saldo, col_acao = st.columns(
                [2.5, 1.25, 1.35, 1.7], vertical_alignment="center"
            )
            with col_nome:
                st.write(f"**{nome} · {rotulo_referencia(f'{ano_fatura:04d}-{mes_fatura:02d}')}**")
                st.caption(f"Fecha {_formatar_data(fechamento)} · Vence {_formatar_data(vencimento)}")
            with col_total:
                st.caption("Total da fatura")
                st.write(f"**{formatar_moeda(total / 100)}**")
            with col_saldo:
                rotulo_saldo = "Crédito disponível" if situacao == "Crédito disponível" else "Saldo restante"
                st.caption(rotulo_saldo)
                st.write(f"**{formatar_moeda(saldo / 100)}**")
                st.caption(situacao)
            with col_acao:
                st.button(
                    "Ver compras e itens",
                    key=f"dashboard_ver_fatura_{id_fatura}",
                    use_container_width=True,
                    on_click=_abrir_fatura_no_cartoes,
                    args=(id_fatura, id_cartao, ano_fatura, mes_fatura),
                )


def mostrar_inicio():
    hoje = date.today()
    st.title("Olá! Seja bem-vindo 👋")
    st.caption("Uma visão consolidada das suas finanças.")

    referencias = obter_referencias_disponiveis(hoje)
    referencia_atual = hoje.strftime("%Y-%m")
    indice_atual = referencias.index(referencia_atual)
    referencia = st.selectbox(
        "Período de análise",
        options=referencias,
        index=indice_atual,
        format_func=rotulo_referencia,
        key="dashboard_referencia",
    )

    dados = obter_dados_dashboard(referencia, hoje=hoje)
    alertas = obter_alertas_financeiros(hoje=hoje)

    col1, col2, col3, col4 = st.columns(4)
    _indicador(col1, "Gastos no período", dados["total_gastos_centavos"], f"dash_gastos_{referencia}")
    _indicador(col2, "Despesas pendentes", dados["despesas_pendentes_centavos"], f"dash_pendentes_{referencia}")
    _indicador(col3, "Saldo das faturas", dados["saldo_faturas_abertas_centavos"], f"dash_faturas_{referencia}")
    _indicador(col4, "Saídas pagas no período", dados["saidas_pagas_centavos"], f"dash_saidas_{referencia}")

    st.caption(
        "Gastos no período considera o mês de referência das Despesas e o mês "
        "do ciclo das faturas de Cartões. O pagamento da fatura não é somado "
        "novamente como gasto. Já 'Saídas pagas' considera o dinheiro efetivamente "
        "pago em despesas e faturas neste mês."
    )

    with st.expander("Como o total de gastos foi calculado?"):
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("**Despesas fora do crédito**")
            st.write(formatar_moeda(dados["despesas_sem_credito_centavos"] / 100))
            st.write("**Parcelas dos cartões no ciclo**")
            st.write(formatar_moeda(dados["parcelas_cartao_centavos"] / 100))
        with col_b:
            st.write("**Encargos e faturas antigas**")
            st.write(formatar_moeda(dados["encargos_cartao_centavos"] / 100))
            st.write("**Créditos e estornos descontados**")
            st.write(formatar_moeda(dados["creditos_cartao_centavos"] / 100))

    _mostrar_resumo_alertas(alertas)

    st.divider()
    col_grafico, col_tendencia = st.columns([1, 1.25], gap="large")

    with col_grafico:
        st.subheader("Despesas por categoria")
        categorias = dados["categorias"]
        if categorias:
            tabela = pd.DataFrame({
                "Categoria": [item["categoria"] for item in categorias],
                "Total": [item["total_centavos"] / 100 for item in categorias],
            }).set_index("Categoria")
            st.bar_chart(tabela, y="Total", use_container_width=True)
            st.caption(
                "Inclui despesas, parcelas e encargos. Créditos e estornos são "
                "descontados do total geral, mas não aparecem como categoria de gasto."
            )
        else:
            st.info("Ainda não há despesas ou parcelas categorizadas neste período.")

    with col_tendencia:
        st.subheader("Evolução dos gastos")
        tendencia = dados["tendencia"]
        tabela_tendencia = pd.DataFrame({
            "Mês": [item["rotulo"] for item in tendencia],
            "Gastos": [item["total_centavos"] / 100 for item in tendencia],
        }).set_index("Mês")
        st.line_chart(tabela_tendencia, y="Gastos", use_container_width=True)
        st.caption("Últimos seis meses até o período selecionado, incluindo parcelas por ciclo de fatura.")

    st.divider()
    col_vencimentos, col_cartoes = st.columns([1.2, 1], gap="large")
    with col_vencimentos:
        _mostrar_alertas_detalhados(alertas)
    with col_cartoes:
        _mostrar_cartoes(dados, referencia)
