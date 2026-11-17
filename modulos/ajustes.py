"""Preferências e configurações do Meu Financeiro."""

import streamlit as st

from database.alertas import (
    DIAS_ALERTA_MAXIMO,
    DIAS_ALERTA_MINIMO,
    obter_dias_alerta,
)
from database.db import salvar_configuracao


def mostrar_ajustes():
    st.title("⚙️ Ajustes")
    st.caption("Personalize o comportamento do Meu Financeiro.")

    st.subheader("🔔 Alertas de vencimento")
    st.write(
        "Defina com quantos dias de antecedência o sistema deve destacar "
        "despesas e faturas que estão chegando ao vencimento."
    )

    dias_atual = obter_dias_alerta()
    with st.form("form_config_alertas"):
        dias_novos = st.slider(
            "Antecedência dos avisos",
            min_value=DIAS_ALERTA_MINIMO,
            max_value=DIAS_ALERTA_MAXIMO,
            value=dias_atual,
            step=1,
            help="Os avisos de vencimento hoje, amanhã e os atrasados sempre aparecem. "
                 "Este número controla os avisos adicionais para os dias seguintes.",
        )
        if dias_novos == 1:
            st.caption(
                "O aviso antecipado ficará limitado aos vencimentos de amanhã. "
                "Os vencimentos de hoje e as obrigações atrasadas também serão exibidos."
            )
        else:
            st.caption(
                f"Além dos avisos de hoje e amanhã, serão exibidas obrigações com "
                f"vencimento até {dias_novos} dias a partir de hoje."
            )
        salvar = st.form_submit_button("Salvar preferências", use_container_width=True)

    if salvar:
        salvar_configuracao("dias_alerta", dias_novos)
        st.session_state["mensagem_ajustes"] = "Preferência de alertas salva com sucesso!"
        st.rerun()

    mensagem = st.session_state.pop("mensagem_ajustes", None)
    if mensagem:
        st.success(mensagem)

    st.divider()
    st.subheader("Como os alertas funcionam")
    st.markdown(
        "- **Atrasadas:** obrigações pendentes cujo vencimento já passou.\n"
        "- **Vencem hoje:** despesas e faturas com vencimento na data atual.\n"
        "- **Vencem amanhã:** obrigações com vencimento no dia seguinte.\n"
        "- **Próximas:** obrigações dentro da antecedência configurada.\n\n"
        "Os alertas são calculados quando você abre ou atualiza o aplicativo. "
        "Nesta versão, não são enviadas notificações quando o aplicativo está fechado."
    )
