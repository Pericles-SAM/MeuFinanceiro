"""Testes dos alertas financeiros com SQLite temporário."""

from datetime import date
from pathlib import Path
import tempfile
import unittest

import database.db as db
import database.cartoes as cartoes
from database.alertas import obter_alertas_financeiros, obter_dias_alerta


class TesteAlertasFinanceiros(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.banco_original = db.BANCO
        db.BANCO = Path(self.tempdir.name) / "alertas.db"
        db.inicializar_banco()
        cartoes.inicializar_estrutura_cartoes()

    def tearDown(self):
        db.BANCO = self.banco_original
        self.tempdir.cleanup()

    def criar_despesa(self, descricao, vencimento, valor=100, status="Pendente", forma="Boleto"):
        return db.adicionar_despesa(
            descricao=descricao,
            valor=valor,
            categoria="Moradia",
            forma_pagamento=forma,
            data_despesa="2026-11-01",
            tem_vencimento=True,
            vencimento=vencimento,
            referencia="2026-11",
            status=status,
            data_pagamento=None if status == "Pendente" else "2026-11-01",
        )

    def test_classifica_despesas_em_atraso_hoje_amanha_e_proximas(self):
        self.criar_despesa("Atrasada", "2026-11-12")
        self.criar_despesa("Hoje", "2026-11-13")
        self.criar_despesa("Amanhã", "2026-11-14")
        self.criar_despesa("Depois", "2026-11-16")
        self.criar_despesa("Fora da faixa", "2026-11-20")
        alertas = obter_alertas_financeiros(date(2026, 11, 13), 3)
        self.assertEqual([x["descricao"] for x in alertas["atrasadas"]], ["Atrasada"])
        self.assertEqual([x["descricao"] for x in alertas["hoje_itens"]], ["Hoje"])
        self.assertEqual([x["descricao"] for x in alertas["amanha"]], ["Amanhã"])
        self.assertEqual([x["descricao"] for x in alertas["proximas"]], ["Depois"])
        self.assertEqual(alertas["total"], 4)

    def test_ignora_pagas_sem_vencimento_e_arquivadas(self):
        self.criar_despesa("Paga", "2026-11-12", status="Pago")
        id_sem_vencimento = db.adicionar_despesa(
            "Compra à vista", 50, "Alimentação", "PIX", "2026-11-12",
            tem_vencimento=False, referencia="2026-11", status="Pendente"
        )
        id_arquivada = self.criar_despesa("Arquivada", "2026-11-12")
        db.arquivar_conta(id_arquivada)
        alertas = obter_alertas_financeiros(date(2026, 11, 13), 3)
        descricoes = [item["descricao"] for grupo in ("atrasadas", "hoje_itens", "amanha", "proximas") for item in alertas[grupo]]
        self.assertEqual(descricoes, [])

    def test_antecedencia_configuravel_e_validada(self):
        self.criar_despesa("Em cinco dias", "2026-11-18")
        db.salvar_configuracao("dias_alerta", 5)
        alertas = obter_alertas_financeiros(date(2026, 11, 13))
        self.assertEqual(obter_dias_alerta(), 5)
        self.assertEqual(len(alertas["proximas"]), 1)
        db.salvar_configuracao("dias_alerta", "valor inválido")
        self.assertEqual(obter_dias_alerta(), 3)

    def test_fatura_de_cartao_aparece_pelo_saldo_restante(self):
        id_cartao = cartoes.adicionar_cartao_credito("Cartão teste", 5, 13, "proxima")
        cartoes.registrar_compra(id_cartao, "Compra de teste", "2026-10-20", 300, 1)
        fatura = cartoes.listar_faturas_mensais(cartao_id=id_cartao)[0]
        self.assertEqual(fatura[6], "2026-11-13")
        cartoes.registrar_pagamento_fatura(fatura[0], 100, "2026-11-10")

        alertas = obter_alertas_financeiros(date(2026, 11, 13), 3)
        faturas_hoje = [x for x in alertas["hoje_itens"] if x["tipo"] == "Fatura"]
        self.assertEqual(len(faturas_hoje), 1)
        self.assertEqual(faturas_hoje[0]["valor_centavos"], 20000)

    def test_fatura_quitada_nao_gera_alerta(self):
        id_cartao = cartoes.adicionar_cartao_credito("Cartão quitado", 5, 13, "proxima")
        cartoes.registrar_compra(id_cartao, "Compra", "2026-10-20", 100, 1)
        fatura = cartoes.listar_faturas_mensais(cartao_id=id_cartao)[0]
        cartoes.registrar_pagamento_fatura(fatura[0], 100, "2026-11-10")
        alertas = obter_alertas_financeiros(date(2026, 11, 13), 3)
        self.assertEqual(alertas["total"], 0)

    def test_limite_inclui_o_ultimo_dia_configurado(self):
        self.criar_despesa("Limite", "2026-11-16")
        alertas = obter_alertas_financeiros(date(2026, 11, 13), 3)
        self.assertEqual(len(alertas["proximas"]), 1)

    def test_fatura_atrasada_aparece_com_saldo_restante(self):
        id_cartao = cartoes.adicionar_cartao_credito("Cartão atrasado", 5, 12, "proxima")
        cartoes.registrar_compra(id_cartao, "Compra antiga", "2026-10-06", 250, 1)
        fatura = cartoes.listar_faturas_mensais(cartao_id=id_cartao)[0]
        self.assertEqual(fatura[6], "2026-11-12")
        cartoes.registrar_pagamento_fatura(fatura[0], 50, "2026-11-10")

        alertas = obter_alertas_financeiros(date(2026, 11, 13), 3)
        faturas_atrasadas = [x for x in alertas["atrasadas"] if x["tipo"] == "Fatura"]
        self.assertEqual(len(faturas_atrasadas), 1)
        self.assertEqual(faturas_atrasadas[0]["valor_centavos"], 20000)

    def test_fatura_de_cartao_inativo_continua_gerando_alerta(self):
        id_cartao = cartoes.adicionar_cartao_credito("Cartão inativo", 5, 14, "proxima")
        cartoes.registrar_compra(id_cartao, "Compra", "2026-10-20", 80, 1)
        fatura = cartoes.listar_faturas_mensais(cartao_id=id_cartao)[0]
        cartoes.alterar_status_cartao(id_cartao, False)

        alertas = obter_alertas_financeiros(date(2026, 11, 13), 3)
        faturas_amanha = [x for x in alertas["amanha"] if x["tipo"] == "Fatura"]
        self.assertEqual(len(faturas_amanha), 1)
        self.assertEqual(faturas_amanha[0]["descricao"], "Cartão inativo · 11/2026")


if __name__ == "__main__":
    unittest.main(verbosity=2)
