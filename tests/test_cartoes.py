"""Testes automatizados do modelo de cartões, compras, parcelas e faturas.

Execute na raiz do projeto com:
    python -m unittest discover -s tests -v

Os testes usam um banco temporário e nunca alteram database/financeiro.db.
"""

from pathlib import Path
import tempfile
import unittest

import database.db as db
import database.cartoes as cartoes


class TesteModuloCartoes(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.banco_original = db.BANCO
        db.BANCO = Path(self.tempdir.name) / "teste_financeiro.db"
        db.inicializar_banco()
        cartoes.inicializar_estrutura_cartoes()

    def tearDown(self):
        db.BANCO = self.banco_original
        self.tempdir.cleanup()

    def criar_cartao(self, nome="Cartão de teste", fechamento=10, vencimento=17, regra="proxima"):
        return cartoes.adicionar_cartao_credito(nome, fechamento, vencimento, regra)

    def test_divisao_em_centavos(self):
        parcelas = cartoes.dividir_em_parcelas("100,00".replace(",", "."), 3)
        self.assertEqual(parcelas, [3334, 3333, 3333])
        self.assertEqual(sum(parcelas), 10000)

    def test_limites_de_parcelamento(self):
        with self.assertRaises(ValueError):
            cartoes.dividir_em_parcelas("0.02", 3)
        with self.assertRaises(ValueError):
            cartoes.dividir_em_parcelas("100.00", 49)

    def test_regras_de_fechamento(self):
        self.assertEqual(cartoes.calcular_ciclo_compra("2026-11-08", 10), (2026, 11))
        self.assertEqual(cartoes.calcular_ciclo_compra("2026-11-11", 10), (2026, 12))
        self.assertEqual(cartoes.calcular_ciclo_compra("2026-11-10", 10, "proxima"), (2026, 12))
        self.assertEqual(cartoes.calcular_ciclo_compra("2026-11-10", 10, "atual"), (2026, 11))

    def test_dias_invalidos_sao_ajustados_no_fim_do_mes(self):
        self.assertEqual(
            cartoes.calcular_datas_fatura(2027, 2, 31, 31),
            ("2027-02-28", "2027-03-31"),
        )
        self.assertEqual(
            cartoes.calcular_datas_fatura(2028, 2, 31, 31),
            ("2028-02-29", "2028-03-31"),
        )

    def test_compra_gera_parcelas_em_ciclos_futuros(self):
        id_cartao = self.criar_cartao()
        id_compra = cartoes.registrar_compra(
            id_cartao, "Televisão", "2026-11-08", "900.00", 3,
            "Eletrônicos", "Compra de teste",
        )
        parcelas = cartoes.listar_parcelas_compra(id_compra)
        self.assertEqual(len(parcelas), 3)
        self.assertEqual([p[3] for p in parcelas], [30000, 30000, 30000])
        self.assertEqual([(p[4], p[5]) for p in parcelas], [(2026, 11), (2026, 12), (2027, 1)])

    def test_fatura_agrega_parcelas_e_permite_pagamento_parcial(self):
        id_cartao = self.criar_cartao()
        cartoes.registrar_compra(id_cartao, "Compra A", "2026-11-08", "300.00", 3)
        fatura = next(
            f for f in cartoes.listar_faturas_mensais(id_cartao)
            if (f[3], f[4]) == (2026, 11)
        )
        self.assertEqual(fatura[7], 10000)
        cartoes.registrar_pagamento_fatura(fatura[0], 25.00, "2026-11-17", "Parcial")
        atualizada = cartoes.obter_fatura_mensal(fatura[0])
        self.assertEqual(atualizada[8], 2500)
        situacao, saldo = cartoes.calcular_situacao_fatura(
            atualizada[7], atualizada[8], atualizada[6]
        )
        self.assertEqual(saldo, 7500)
        self.assertIn(situacao, {"Parcial", "Parcial atrasada"})

    def test_nao_permite_pagamento_acima_do_saldo(self):
        id_cartao = self.criar_cartao()
        cartoes.registrar_compra(id_cartao, "Compra", "2026-11-08", "10.00", 1)
        fatura = cartoes.listar_faturas_mensais(id_cartao)[0]
        with self.assertRaises(ValueError):
            cartoes.registrar_pagamento_fatura(fatura[0], 10.01)

    def test_pagamento_estornado_fica_no_historico(self):
        id_cartao = self.criar_cartao()
        cartoes.registrar_compra(id_cartao, "Compra", "2026-11-08", "10.00", 1)
        fatura = cartoes.listar_faturas_mensais(id_cartao)[0]
        id_pagamento = cartoes.registrar_pagamento_fatura(fatura[0], 5.00)
        self.assertTrue(cartoes.estornar_pagamento_fatura(id_pagamento, "Valor incorreto"))
        pagamento = cartoes.listar_pagamentos_fatura(fatura[0])[0]
        self.assertEqual(pagamento[4], 1)
        self.assertEqual(pagamento[5], "Valor incorreto")
        self.assertEqual(cartoes.obter_fatura_mensal(fatura[0])[8], 0)

    def test_credito_e_encargo_alteram_fatura_e_podem_ser_estornados(self):
        id_cartao = self.criar_cartao()
        id_fatura, _ = cartoes.registrar_ajuste_no_ciclo(
            id_cartao, 2027, 5, "Encargo", "Anuidade", 20.00
        )
        id_credito = cartoes.adicionar_ajuste_fatura(id_fatura, "Crédito", "Cashback", 5.00)
        self.assertEqual(cartoes.obter_fatura_mensal(id_fatura)[7], 1500)
        cartoes.estornar_ajuste_fatura(id_credito, "Lançamento incorreto")
        self.assertEqual(cartoes.obter_fatura_mensal(id_fatura)[7], 2000)

    def test_edicao_preserva_versoes_anteriores(self):
        id_cartao = self.criar_cartao()
        id_compra = cartoes.registrar_compra(id_cartao, "Compra original", "2026-11-08", 90.00, 3)
        cartoes.editar_compra(id_compra, id_cartao, "Compra revisada", "2026-11-09", 100.00, 4)
        parcelas = cartoes.listar_parcelas_compra(id_compra)
        self.assertEqual(len(parcelas), 7)
        self.assertEqual(sum(p[3] for p in parcelas if p[11] == 2), 10000)
        self.assertEqual(len(cartoes.listar_historico_compra(id_compra)), 1)

    def test_cancelamento_e_restauracao_logicos(self):
        id_cartao = self.criar_cartao()
        id_compra = cartoes.registrar_compra(id_cartao, "Compra", "2026-11-08", 120.00, 2)
        self.assertTrue(cartoes.cancelar_compra(id_compra))
        self.assertEqual(cartoes.obter_compra(id_compra)[8], 0)
        self.assertTrue(cartoes.restaurar_compra(id_compra))
        self.assertEqual(cartoes.obter_compra(id_compra)[8], 1)

    def test_pagamento_ativo_protege_compra_de_edicao_e_cancelamento(self):
        id_cartao = self.criar_cartao()
        id_compra = cartoes.registrar_compra(id_cartao, "Compra", "2026-11-08", 120.00, 2)
        fatura = next(f for f in cartoes.listar_faturas_mensais(id_cartao) if f[3:5] == (2026, 11))
        cartoes.registrar_pagamento_fatura(fatura[0], 10.00)
        with self.assertRaises(ValueError):
            cartoes.editar_compra(id_compra, id_cartao, "Outra", "2026-11-08", 80.00, 1)
        with self.assertRaises(ValueError):
            cartoes.cancelar_compra(id_compra)

    def test_cartao_arquivado_nao_recebe_novas_compras(self):
        id_cartao = self.criar_cartao()
        cartoes.alterar_status_cartao(id_cartao, False)
        with self.assertRaises(ValueError):
            cartoes.registrar_compra(id_cartao, "Compra", "2026-11-08", 10.00, 1)
        cartoes.alterar_status_cartao(id_cartao, True)
        self.assertEqual(cartoes.listar_cartoes_credito(ativos=True)[0][0], id_cartao)


    def test_nao_permite_cartoes_com_nomes_duplicados(self):
        id_cartao = self.criar_cartao("Meu cartão")
        self.criar_cartao("Outro cartão")
        with self.assertRaises(ValueError):
            self.criar_cartao("MEU CARTÃO")
        with self.assertRaises(ValueError):
            cartoes.editar_cartao_credito(id_cartao, "OUTRO CARTÃO", 10, 17, "proxima")
        nomes = {c[1] for c in cartoes.listar_cartoes_credito()}
        self.assertEqual(nomes, {"Meu cartão", "Outro cartão"})

    def test_migracao_de_fatura_antiga_e_idempotente(self):
        with db.conectar() as conexao:
            id_cartao = conexao.execute(
                "INSERT INTO cartoes (nome, dia_fechamento, dia_vencimento) VALUES (?, ?, ?)",
                ("Cartão antigo", 10, 17),
            ).lastrowid
            conexao.execute(
                "INSERT INTO faturas (cartao_id, valor, vencimento, status, pago_em) VALUES (?, ?, ?, ?, ?)",
                (id_cartao, 123.45, "2026-10-17", "Pago", "2026-10-10 10:00:00"),
            )
        cartoes.inicializar_estrutura_cartoes()
        cartoes.inicializar_estrutura_cartoes()
        fatura = cartoes.listar_faturas_mensais(id_cartao)[0]
        self.assertEqual((fatura[7], fatura[8]), (12345, 12345))
        with db.conectar() as conexao:
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM faturas").fetchone()[0], 1)
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM faturas_antigas_importadas").fetchone()[0], 1)

    def test_editar_conta_preserva_atualizacao(self):
        id_conta = db.adicionar_conta("Internet", 100.0, "Moradia", "2026-11-15", "2026-11")
        self.assertTrue(db.editar_conta(id_conta, "Internet fibra", 120.0, "Moradia", "2026-11-16", "2026-11"))
        self.assertEqual(db.obter_conta(id_conta)[1], "Internet fibra")
        self.assertEqual(db.obter_conta(id_conta)[2], 120.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
