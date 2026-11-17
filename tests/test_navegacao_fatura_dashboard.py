"""Testes do acesso direto à fatura a partir do Dashboard.

Execute com:
    python -m unittest discover -s tests -v

Os testes usam um banco temporário e não alteram o banco financeiro real.
"""

import ast
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import database.db as db
import database.cartoes as cartoes


RAIZ_PROJETO = Path(__file__).resolve().parents[1]
ARQUIVO_INICIO = RAIZ_PROJETO / "modulos" / "inicio.py"


class TesteAcessoDiretoAFatura(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.banco_original = db.BANCO
        db.BANCO = Path(self.tempdir.name) / "teste_drilldown.db"
        db.inicializar_banco()
        cartoes.inicializar_estrutura_cartoes()

    def tearDown(self):
        db.BANCO = self.banco_original
        self.tempdir.cleanup()

    def test_fatura_de_dezembro_2027_exibe_parcela_15_de_15_do_ssd(self):
        id_cartao = cartoes.adicionar_cartao_credito("Cartão principal", 10, 17)
        id_compra = cartoes.registrar_compra(
            id_cartao,
            "SSD",
            "2026-10-08",
            778.00,
            15,
            categoria="Tecnologia",
        )

        faturas = cartoes.listar_faturas_mensais(
            cartao_id=id_cartao, ano=2027, mes=12
        )
        self.assertEqual(len(faturas), 1)
        fatura = faturas[0]

        itens = cartoes.listar_itens_fatura(fatura[0])
        parcela_ssd = next(item for item in itens if item[1] == "SSD")

        self.assertEqual(parcela_ssd[0], "Parcela")
        self.assertEqual(parcela_ssd[4], 15)
        self.assertEqual(parcela_ssd[5], 15)
        self.assertEqual(parcela_ssd[3], 5186)  # R$ 51,86 na última parcela.
        self.assertEqual(parcela_ssd[6], id_compra)
        self.assertEqual(fatura[7], 5186)

    def test_callback_define_pagina_aba_e_filtros_da_fatura(self):
        arvore = ast.parse(ARQUIVO_INICIO.read_text(encoding="utf-8"))
        funcao = next(
            no for no in arvore.body
            if isinstance(no, ast.FunctionDef)
            and no.name == "_abrir_fatura_no_cartoes"
        )
        modulo = ast.Module(body=[funcao], type_ignores=[])
        estado = {}
        ambiente = {"st": SimpleNamespace(session_state=estado)}
        exec(compile(modulo, str(ARQUIVO_INICIO), "exec"), ambiente)

        ambiente["_abrir_fatura_no_cartoes"](91, 7, 2027, 12)

        self.assertEqual(estado["pagina_atual"], "Cartões")
        self.assertEqual(estado["secao_cartoes"], "Faturas")
        self.assertEqual(estado["fatura_dashboard_selecionada"], 91)
        self.assertEqual(estado["filtro_faturas_cartao"], 7)
        self.assertEqual(estado["filtro_faturas_ano"], 2027)
        self.assertEqual(estado["filtro_faturas_mes"], 12)


if __name__ == "__main__":
    unittest.main()
