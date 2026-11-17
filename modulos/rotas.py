from modulos.ajustes import mostrar_ajustes
from modulos.cartoes import mostrar_cartoes
from modulos.despesas import mostrar_despesas
from modulos.inicio import mostrar_inicio
from modulos.relatorios import mostrar_relatorios


# O nome exibido no menu é a chave; o valor é a função da respectiva tela.
PAGINAS = {
    "Início": mostrar_inicio,
    "Despesas": mostrar_despesas,
    "Cartões": mostrar_cartoes,
    "Relatórios": mostrar_relatorios,
    "Ajustes": mostrar_ajustes,
}
