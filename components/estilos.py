from pathlib import Path

import streamlit as st


def carregar_css():
    """Carrega o CSS da pasta styles na raiz do projeto, se existir."""
    raiz_projeto = Path(__file__).resolve().parents[1]
    caminho_css = raiz_projeto / "styles" / "main.css"

    if not caminho_css.exists():
        st.warning("O arquivo styles/main.css não foi encontrado.")
        return

    css = caminho_css.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
