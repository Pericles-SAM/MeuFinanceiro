import tempfile
import unittest
from datetime import date
from pathlib import Path

from database import db
from database.cartoes import (
    adicionar_cartao_credito,
    inicializar_estrutura_cartoes,
    registrar_compra,
    registrar_pagamento_fatura,
)
from database.dashboard import obter_dados_dashboard, obter_referencias_disponiveis


class TestDashboard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.banco_original = db.BANCO
        db.BANCO = Path(self.temp.name) / "dashboard_teste.db"
        db.inicializar_banco()
        inicializar_estrutura_cartoes()

    def tearDown(self):
        db.BANCO = self.banco_original
        self.temp.cleanup()

    def _dados_base(self):
        db.adicionar_despesa(
            "Energia", 150, "Moradia", "PIX", "2026-11-05",
            tem_vencimento=True, vencimento="2026-11-19",
            referencia="2026-11", status="Pendente",
        )
        db.adicionar_despesa(
            "Mercado", 80, "Alimentação", "Cartão de débito", "2026-11-02",
            tem_vencimento=False, referencia="2026-11", status="Pago",
            data_pagamento="2026-11-03",
        )
        cartao = adicionar_cartao_credito("Cartão teste", 10, 17, "proxima")
        registrar_compra(
            cartao, "Compra parcelada", "2026-11-08", 300, 3,
            categoria="Moradia",
        )
        return cartao

    def test_soma_despesas_e_parcelas_sem_somar_pagamento_fatura_como_gasto(self):
        cartao = self._dados_base()
        from database.cartoes import listar_faturas_mensais
        fatura = next(f for f in listar_faturas_mensais(ano=2026, mes=11) if f[1] == cartao)
        registrar_pagamento_fatura(fatura[0], 50, "2026-11-12", "Pagamento parcial")

        dados = obter_dados_dashboard("2026-11", hoje=date(2026, 11, 13), dias_alerta=5)

        self.assertEqual(dados["despesas_sem_credito_centavos"], 23000)
        self.assertEqual(dados["parcelas_cartao_centavos"], 10000)
        self.assertEqual(dados["total_gastos_centavos"], 33000)
        self.assertEqual(dados["despesas_pendentes_centavos"], 15000)
        self.assertEqual(dados["saldo_faturas_abertas_centavos"], 5000)
        self.assertEqual(dados["saidas_pagas_centavos"], 13000)
        self.assertEqual(dados["obrigacoes_atrasadas"], 0)
        self.assertEqual(len(dados["proximos_vencimentos"]), 1)

    def test_categoria_agrega_despesa_e_parcela(self):
        self._dados_base()
        dados = obter_dados_dashboard("2026-11", hoje=date(2026, 11, 13), dias_alerta=7)
        por_categoria = {item["categoria"]: item["total_centavos"] for item in dados["categorias"]}
        self.assertEqual(por_categoria["Moradia"], 25000)
        self.assertEqual(por_categoria["Alimentação"], 8000)

    def test_fatura_atrasada_entra_no_total_de_obrigacoes_atrasadas(self):
        cartao = self._dados_base()
        from database.cartoes import listar_faturas_mensais
        fatura = next(f for f in listar_faturas_mensais(ano=2026, mes=11) if f[1] == cartao)
        registrar_pagamento_fatura(fatura[0], 20, "2026-11-12")
        dados = obter_dados_dashboard("2026-11", hoje=date(2026, 11, 20), dias_alerta=3)
        self.assertEqual(dados["faturas_atrasadas"], 1)
        self.assertEqual(dados["obrigacoes_atrasadas"], 2)  # energia + fatura

    def test_referencias_incluem_mes_atual_e_registros_existentes(self):
        self._dados_base()
        refs = obter_referencias_disponiveis(date(2026, 11, 13))
        self.assertIn("2026-11", refs)
        self.assertEqual(refs[0], "2027-11")

    def test_referencia_invalida_rejeitada(self):
        with self.assertRaises(ValueError):
            obter_dados_dashboard("2026-13", hoje=date(2026, 11, 13))


if __name__ == "__main__":
    unittest.main()
