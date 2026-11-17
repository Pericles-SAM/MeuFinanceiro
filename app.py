import streamlit as st

from components.estilos import carregar_css
from components.navegacao import mostrar_menu
from database.db import inicializar_banco
from database.cartoes import inicializar_estrutura_cartoes
from modulos.rotas import PAGINAS


# A configuração da página deve ser a primeira chamada do Streamlit.
st.set_page_config(
    page_title="Meu Financeiro",
    page_icon="💳",
    layout="wide",
)

# Prepara o banco e os elementos compartilhados da interface.
inicializar_banco()
inicializar_estrutura_cartoes()
carregar_css()

# Menu e roteamento centralizados: as telas ficam em arquivos independentes.
pagina = mostrar_menu(PAGINAS)
PAGINAS[pagina]()
