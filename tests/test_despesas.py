"""Testes do módulo Despesas. Usam SQLite temporário, nunca o banco pessoal."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

import database.db as db


class TesteModuloDespesas(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.banco_original = db.BANCO
        db.BANCO = Path(self.tempdir.name) / "teste_despesas.db"
        db.inicializar_banco()

    def tearDown(self):
        db.BANCO = self.banco_original
        self.tempdir.cleanup()

    def criar_despesa(self, **alteracoes):
        dados = {
            "descricao": "Mercado",
            "valor": 125.50,
            "categoria": "Alimentação",
            "forma_pagamento": "PIX",
            "data_despesa": "2026-11-13",
            "tem_vencimento": False,
            "vencimento": None,
            "referencia": "2026-11",
            "status": "Pago",
            "data_pagamento": "2026-11-13",
        }
        dados.update(alteracoes)
        return db.adicionar_despesa(**dados)

    def test_cadastro_pago_sem_vencimento(self):
        id_despesa = self.criar_despesa()
        despesa = db.obter_despesa(id_despesa)
        self.assertEqual(despesa[1], "Mercado")
        self.assertEqual(despesa[4], "PIX")
        self.assertEqual(despesa[5], "2026-11-13")
        self.assertEqual(despesa[6], 0)
        self.assertEqual(despesa[7], "2026-11-13")  # fallback legado
        self.assertEqual(despesa[9], "Pago")
        self.assertEqual(despesa[10], "2026-11-13")

    def test_cadastro_pendente_com_vencimento(self):
        id_despesa = self.criar_despesa(
            descricao="Conta de energia",
            valor=187.90,
            forma_pagamento="Boleto",
            data_despesa="2026-11-01",
            tem_vencimento=True,
            vencimento="2026-11-20",
            status="Pendente",
            data_pagamento=None,
        )
        despesa = db.obter_despesa(id_despesa)
        self.assertEqual(despesa[4], "Boleto")
        self.assertEqual(despesa[6], 1)
        self.assertEqual(despesa[7], "2026-11-20")
        self.assertEqual(despesa[9], "Pendente")
        self.assertIsNone(despesa[10])

    def test_filtros_por_forma_categoria_status_e_referencia(self):
        self.criar_despesa()
        self.criar_despesa(
            descricao="Ônibus", valor=12.00, categoria="Transporte",
            forma_pagamento="Dinheiro", referencia="2026-10",
        )
        self.assertEqual(len(db.listar_despesas(forma_pagamento="PIX")), 1)
        self.assertEqual(len(db.listar_despesas(categoria="Transporte")), 1)
        self.assertEqual(len(db.listar_despesas(status="Pendente")), 0)
        self.assertEqual(len(db.listar_despesas(referencia="2026-10")), 1)

    def test_edicao_preserva_status_e_data_de_pagamento(self):
        id_despesa = self.criar_despesa()
        self.assertTrue(db.editar_despesa(
            id_despesa, "Mercado revisado", 140.00, "Alimentação", "Cartão de débito",
            "2026-11-12", False, None, "2026-11",
        ))
        despesa = db.obter_despesa(id_despesa)
        self.assertEqual(despesa[1], "Mercado revisado")
        self.assertEqual(despesa[2], 140.00)
        self.assertEqual(despesa[4], "Cartão de débito")
        self.assertEqual(despesa[9], "Pago")
        self.assertEqual(despesa[10], "2026-11-13")

    def test_alterar_status_com_data_de_pagamento_manual(self):
        id_despesa = self.criar_despesa(status="Pendente", data_pagamento=None)
        self.assertTrue(db.marcar_como_paga(id_despesa, "2026-11-14"))
        self.assertEqual(db.obter_despesa(id_despesa)[10], "2026-11-14")
        self.assertTrue(db.marcar_como_pendente(id_despesa))
        self.assertEqual(db.obter_despesa(id_despesa)[9], "Pendente")
        self.assertIsNone(db.obter_despesa(id_despesa)[10])

    def test_arquivamento_e_restauracao_preservam_forma_pagamento(self):
        id_despesa = self.criar_despesa()
        self.assertTrue(db.arquivar_conta(id_despesa))
        self.assertEqual(len(db.listar_despesas()), 0)
        arquivadas = db.listar_despesas(arquivada=True)
        self.assertEqual(len(arquivadas), 1)
        self.assertEqual(arquivadas[0][4], "PIX")
        self.assertTrue(db.restaurar_conta(id_despesa))
        self.assertEqual(len(db.listar_despesas()), 1)

    def test_validacoes(self):
        with self.assertRaises(ValueError):
            self.criar_despesa(descricao="   ")
        with self.assertRaises(ValueError):
            self.criar_despesa(valor=0)
        with self.assertRaises(ValueError):
            self.criar_despesa(forma_pagamento="Cartão de crédito")
        with self.assertRaises(ValueError):
            self.criar_despesa(tem_vencimento=True, vencimento=None)

    def test_migracao_de_registro_antigo_preserva_dados(self):
        # Simula um arquivo antigo independente, sem as novas colunas.
        db.BANCO.unlink(missing_ok=True)
        conexao = sqlite3.connect(db.BANCO)
        conexao.execute("""
            CREATE TABLE contas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descricao TEXT NOT NULL,
                valor REAL NOT NULL,
                categoria TEXT NOT NULL,
                vencimento TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pendente',
                pago_em TEXT,
                criado_em TEXT,
                referencia TEXT,
                arquivada INTEGER NOT NULL DEFAULT 0
            )
        """)
        conexao.execute("""
            INSERT INTO contas
                (descricao, valor, categoria, vencimento, status, referencia)
            VALUES ('Conta antiga', 89.90, 'Moradia', '2026-11-22', 'Pendente', '2026-11')
        """)
        conexao.commit()
        conexao.close()

        db.inicializar_banco()
        db.inicializar_banco()  # migração deve ser idempotente
        antiga = db.obter_despesa(1)
        self.assertEqual(antiga[1], "Conta antiga")
        self.assertEqual(antiga[4], "Não informado")
        self.assertIsNone(antiga[5])  # data real não é inventada
        self.assertEqual(antiga[6], 1)
        self.assertEqual(antiga[7], "2026-11-22")


if __name__ == "__main__":
    unittest.main(verbosity=2)
