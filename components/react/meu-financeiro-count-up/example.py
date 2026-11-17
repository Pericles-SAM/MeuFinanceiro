import streamlit as st

from meu_financeiro_count_up import meu_financeiro_count_up


st.set_page_config(
    page_title="Demonstração Count Up",
    page_icon="💳",
    layout="wide",
)

st.title("Meu Financeiro — Count Up")
st.caption("Demonstração do componente React integrado ao Streamlit.")

valor_despesas = st.number_input(
    "Altere o valor para testar a animação",
    min_value=0.0,
    value=2450.0,
    step=50.0,
    format="%.2f",
)

valor_pago = valor_despesas * 0.72
valor_pendente = valor_despesas - valor_pago

col1, col2, col3 = st.columns(3)

with col1:
    meu_financeiro_count_up(
        valor_despesas,
        "Total de despesas",
        prefixo="R$",
        duracao=1.4,
        casas_decimais=2,
        key="demo_total_despesas",
    )

with col2:
    meu_financeiro_count_up(
        valor_pago,
        "Total pago",
        prefixo="R$",
        duracao=1.4,
        casas_decimais=2,
        key="demo_total_pago",
    )

with col3:
    meu_financeiro_count_up(
        valor_pendente,
        "Total pendente",
        prefixo="R$",
        duracao=1.4,
        casas_decimais=2,
        key="demo_total_pendente",
    )

st.divider()
st.info(
    "Experimente alterar o valor acima. Os três indicadores receberão os "
    "novos valores do Python e animarão a transição no React."
)
