import streamlit as st


def mostrar_menu(paginas):
    """Exibe o menu lateral e retorna a página selecionada.

    Migra a seleção antiga "Contas" para o novo nome "Despesas" sem
    interromper a sessão de quem atualiza a aplicação.
    """
    if st.session_state.get("pagina_atual") == "Contas" and "Despesas" in paginas:
        st.session_state["pagina_atual"] = "Despesas"

    st.sidebar.title("💳 Meu Financeiro")
    st.sidebar.caption("Controle financeiro pessoal")

    return st.sidebar.radio(
        "NAVEGAÇÃO",
        list(paginas),
        key="pagina_atual",
    )
