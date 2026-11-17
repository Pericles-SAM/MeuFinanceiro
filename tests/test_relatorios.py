"""Testes do módulo de relatórios. Utiliza banco SQLite temporário."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import db
from database.cartoes import (
    adicionar_ajuste_fatura,
    adicionar_cartao_credito,
    inicializar_estrutura_cartoes,
    listar_faturas_mensais,
    registrar_compra,
    registrar_pagamento_fatura,
)
from database.relatorios import (
    listar_lancamentos_relatorio,
    listar_meses_disponiveis,
    obter_dados_relatorio,
    rotulo_mes,
    validar_mes,
)


class TestRelatorios(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.banco_original = db.BANCO
        db.BANCO = Path(self.temp.name) / "relatorios_teste.db"
        db.inicializar_banco()
        inicializar_estrutura_cartoes()

    def tearDown(self):
        db.BANCO = self.banco_original
        self.temp.cleanup()

    def criar_dados(self):
        id_pago = db.adicionar_despesa(
            "Mercado", 120, "Alimentação", "PIX", "2026-11-03",
            tem_vencimento=False, referencia="2026-11", status="Pago",
            data_pagamento="2026-11-04",
        )
        id_pendente = db.adicionar_despesa(
            "Energia", 200, "Moradia", "Boleto", "2026-11-05",
            tem_vencimento=True, vencimento="2026-12-10",
            referencia="2026-11", status="Pendente",
        )
        cartao = adicionar_cartao_credito("Cartão Azul", 10, 17, "proxima")
        compra = registrar_compra(
            cartao, "SSD", "2026-11-08", "778.00", 15,
            categoria="Tecnologia",
        )
        faturas = listar_faturas_mensais(cartao_id=cartao)
        fatura_nov = next(f for f in faturas if (f[3], f[4]) == (2026, 11))
        fatura_dez = next(f for f in faturas if (f[3], f[4]) == (2026, 12))
        adicionar_ajuste_fatura(fatura_dez[0], "Encargo", "Anuidade proporcional", 5.00)
        registrar_pagamento_fatura(fatura_nov[0], 51.87, "2026-11-20", "Pagamento da fatura")
        return id_pago, id_pendente, cartao, compra, fatura_nov, fatura_dez

    def test_competencia_considera_referencia_das_despesas_e_valor_total_da_compra(self):
        self.criar_dados()
        dados = obter_dados_relatorio("competencia", ["2026-11"])
        self.assertEqual(dados["total_centavos"], 12000 + 20000 + 77800 + 500)
        itens_compra = [i for i in dados["lancamentos"] if i["descricao"] == "SSD"]
        self.assertEqual(len(itens_compra), 1)
        self.assertEqual(itens_compra[0]["valor_centavos"], 77800)
        self.assertIn("15x", itens_compra[0]["detalhe"])

    def test_vencimento_distribui_parcelas_e_ajustes_pelo_vencimento_real(self):
        self.criar_dados()
        dados = obter_dados_relatorio("vencimento", ["2026-12"])
        cartao = [i for i in dados["lancamentos"] if i["origem"] == "Cartão"]
        self.assertEqual(sum(i["valor_centavos"] for i in cartao), 5187 + 500)
        self.assertTrue(any("Parcela 2/15" in i["detalhe"] for i in cartao))
        self.assertTrue(any(i["descricao"] == "Anuidade proporcional" for i in cartao))

    def test_pagamento_mostra_saida_real_sem_recontar_compras(self):
        self.criar_dados()
        dados = obter_dados_relatorio("pagamento", ["2026-11"])
        self.assertEqual(dados["total_centavos"], 12000 + 5187)
        self.assertTrue(any(i["categoria"] == "Pagamento de cartão" for i in dados["lancamentos"]))
        self.assertFalse(any(i["descricao"] == "SSD" for i in dados["lancamentos"]))

    def test_meses_nao_consecutivos_sao_comparados_incluindo_mes_zerado(self):
        self.criar_dados()
        dados = obter_dados_relatorio("competencia", ["2026-11", "2027-01", "2027-03"])
        totais = {i["mes"]: i["total_centavos"] for i in dados["por_mes"]}
        self.assertEqual(list(totais), ["2026-11", "2027-01", "2027-03"])
        self.assertEqual(totais["2027-01"], 0)
        self.assertEqual(totais["2027-03"], 0)
        self.assertEqual(dados["quantidade_meses"], 3)
        self.assertEqual(dados["media_mensal_centavos"], round((12000 + 20000 + 77800 + 500) / 3))

    def test_despesas_arquivadas_sao_incluidas_por_padrao_e_podem_ser_excluidas(self):
        id_pago, *_ = self.criar_dados()
        db.arquivar_conta(id_pago)
        com_arquivadas = obter_dados_relatorio("competencia", ["2026-11"], True)
        sem_arquivadas = obter_dados_relatorio("competencia", ["2026-11"], False)
        self.assertEqual(com_arquivadas["total_centavos"] - sem_arquivadas["total_centavos"], 12000)

    def test_lista_meses_disponiveis_depende_do_criterio(self):
        self.criar_dados()
        meses_competencia = listar_meses_disponiveis("competencia")
        meses_vencimento = listar_meses_disponiveis("vencimento")
        meses_pagamento = listar_meses_disponiveis("pagamento")
        self.assertIn("2026-11", meses_competencia)
        self.assertIn("2026-12", meses_vencimento)
        self.assertIn("2026-11", meses_pagamento)

    def test_validacao_de_mes_e_criterio(self):
        self.assertEqual(validar_mes("2026-03"), "2026-03")
        self.assertEqual(rotulo_mes("2026-03"), "Março/2026")
        with self.assertRaises(ValueError):
            validar_mes("2026-13")
        with self.assertRaises(ValueError):
            listar_lancamentos_relatorio("errado", ["2026-11"])

    def test_referencia_vazia_na_despesa_antiga_usa_data_despesa_como_recurso(self):
        with db.conectar() as conexao:
            conexao.execute("""INSERT INTO contas
                (descricao, valor, categoria, vencimento, status, referencia,
                 arquivada, forma_pagamento, data_despesa, tem_vencimento)
                VALUES ('Antiga', 10, 'Outros', '2026-07-20', 'Pago', NULL,
                        0, 'Não informado', '2026-07-02', 1)""")
        dados = obter_dados_relatorio("competencia", ["2026-07"])
        self.assertEqual(dados["total_centavos"], 1000)


if __name__ == "__main__":
    unittest.main()
