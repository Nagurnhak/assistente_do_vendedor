"""Módulos Vendas (Lançar pedido e Conferência) e Cadastro no modo demonstração, com a rede BLOQUEADA.

Rode na pasta do projeto:  py -m unittest discover testes
"""
import contextlib
import importlib
import io
import os
import socket
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _sem_rede(*_, **__):
    raise AssertionError("o modo demonstração tentou acessar a rede!")


class Base(unittest.TestCase):
    def setUp(self):
        self._conectar, self._criar = socket.socket.connect, socket.create_connection
        socket.socket.connect = _sem_rede
        socket.create_connection = _sem_rede
        import ferramentas_internas as fi
        import demo
        self.fi = fi
        self.demo = importlib.reload(demo)  # dados limpos a cada teste
        self.demo.ATRASO = 0
        fi.MODO_DEMO = True
        fi._escolha_externa = None

    def tearDown(self):
        socket.socket.connect, socket.create_connection = self._conectar, self._criar


class TestCadastro(Base):
    def setUp(self):
        super().setUp()
        import cadastro
        self.cadastro = importlib.reload(cadastro)

    def varrer(self, fornecedor="Fornecedor A"):
        return self.cadastro.varredura(self.demo.tabela_exemplo(fornecedor), fornecedor, avisar=lambda _: None)

    def status(self, resultado):
        return {i["codigo_bling"]: i["status"] for i in resultado["itens"]}

    def test_calculo_compra_custo_e_venda(self):
        perfil = {"desconto": 0.10, "ipi": 0.05, "frete": 0.05, "margem": 2.0}
        self.assertEqual(self.cadastro.calcular(1000, perfil), (900.0, 992.25, 1984.5))

    def test_preco_em_vermelho_usa_desconto_promocional(self):
        perfil = {"desconto": 0.20, "desconto_promocional": 0.05, "margem": 1.0}
        self.assertEqual(self.cadastro.calcular(100, perfil, promocional=True)[0], 95.0)

    def test_varredura_classifica_cada_situacao(self):
        r = self.varrer()
        self.assertEqual(self.status(r), {"100001": "em_dia", "100002": "desatualizado", "100003": "desatualizado",
                                          "100004": "sob_consulta", "100005": "sem_tray", "100008": "kit"})
        self.assertEqual(sorted(n["codigo"] for n in r["novos"]), ["100006", "100007"])  # sem cadastro no sistema
        self.assertEqual([f["codigo"] for f in r["fora"]], ["100009"])                    # saiu da tabela
        self.assertEqual([i["codigo_bling"] for i in r["invalidos"]], ["160"])            # código que não é da tabela

    def test_aplicar_corrige_bling_e_tray_e_a_nova_varredura_fica_em_dia(self):
        r = self.varrer()
        marcados = [i for i in r["itens"] if i["status"] in ("desatualizado", "sob_consulta")]
        ok, falhas = self.cadastro.aplicar(marcados, avisar=lambda _: None)
        self.assertEqual((ok, falhas), (3, []))
        depois = self.status(self.varrer())
        self.assertEqual({depois[c] for c in ("100002", "100003", "100004")}, {"em_dia"})
        self.assertEqual(depois["100008"], "kit")  # kit nunca é aplicado sozinho

    def test_sob_consulta_so_muda_o_custo(self):
        item = next(i for i in self.varrer()["itens"] if i["status"] == "sob_consulta")
        self.cadastro.aplicar([item], avisar=lambda _: None)
        tray = self.demo.TRAY_PROD[item["tray_id"]]
        self.assertEqual(float(tray["cost_price"]), item["custo_novo"])
        self.assertEqual(float(tray["price"]), 0)  # o preço de venda não aparece no site

    def test_inativar_nao_apaga_nada(self):
        item = self.varrer()["fora"][0]
        ok, falhas = self.cadastro.inativar([item], avisar=lambda _: None)
        self.assertEqual((ok, falhas), (1, []))
        self.assertEqual(self.demo.PROD_CAD[item["bling_produto_id"]]["situacao"], "I")
        self.assertEqual(self.demo.TRAY_PROD[item["tray_id"]]["available"], 0)

    def test_tabela_semanal_variacoes_e_preco_promocional(self):
        r = self.varrer("Fornecedor B")
        status = self.status(r)
        self.assertEqual(status["FB-1100CINZA"], "desatualizado")
        self.assertEqual(status["FB-1100PRETA"], "em_dia")
        ara = next(i for i in r["itens"] if i["codigo"] == "FB-1200")
        self.assertTrue(ara["promocional"])

    def test_cor_nao_e_confundida_com_letra_do_modelo(self):
        tabela = {"FB-1102B": {"linhas": [{"cor": "Preta", "preco": 10.0, "promocional": False}]},
                  "FB-1102": {"linhas": [{"cor": "Branca", "preco": 20.0, "promocional": False}]}}
        perfil = {"casar": "prefixo", "padrao_base": r"FB-\d+"}
        situacao, codigo, _ = self.cadastro.casar_codigo("FB-1102BRANCA", tabela, perfil)
        self.assertEqual((situacao, codigo), ("ok", "FB-1102"))


class TestConferencia(Base):
    def setUp(self):
        super().setUp()
        import conferencia
        self.conferencia = importlib.reload(conferencia)

    def conferir(self, vendedor=1):
        with contextlib.redirect_stdout(io.StringIO()):
            return self.conferencia.conferir(vendedor, forcar=True)

    def test_so_pedidos_do_vendedor_com_o_mais_urgente_primeiro(self):
        self.assertEqual([p["numero"] for p in self.conferir(1)], ["1004", "1005"])
        self.assertEqual([p["numero"] for p in self.conferir(2)], ["1006"])

    def test_situacao_de_cada_oc_e_previsao_vencida(self):
        pedido = self.conferir(1)[0]
        self.assertTrue(pedido["atrasado"])
        self.assertEqual(pedido["fonte"], "Observações")
        estados = {o["numero"]: o["estado"] for o in pedido["ocs"]}
        self.assertEqual(estados, {"4991": "atrasada", "4992": "chegou", "4993": "aberta"})
        etapa = next(o["etapa"] for o in pedido["ocs"] if o["numero"] == "4993")
        self.assertEqual(etapa, "Marcenaria: Corte")  # a lista do Trello em que o card da fábrica está

    def test_oc_atrasada_conta_mesmo_com_a_previsao_do_pedido_em_dia(self):
        pedido = self.conferir(2)[0]
        self.assertFalse(pedido["atrasado"])
        self.assertIn("atrasada", [o["estado"] for o in pedido["ocs"]])

    def test_nova_previsao_vira_a_data_principal(self):
        pedido = self.conferir(1)[0]
        nova = date.today() + timedelta(days=40)
        self.conferencia.registrar_nova_previsao(pedido["numero"], nova, "Ana")
        with contextlib.redirect_stdout(io.StringIO()):
            atualizado = self.conferencia.conferir(1)  # usa o cache: a tela não relê a Tray
        pedido = next(p for p in atualizado if p["numero"] == "1004")
        self.assertEqual(pedido["previsao"], nova)
        self.assertFalse(pedido["atrasado"])

    def test_ultima_nova_previsao_manda_nas_observacoes(self):
        texto = "Data prevista para entrega: 30/11/2026<br>Nova previsão (vendedor, 29/10): 15/12/26"
        self.assertEqual(self.conferencia.data_das_observacoes(texto)[0], date(2026, 12, 15))

    def test_mensagem_de_cobranca_traz_oc_atraso_e_referencia(self):
        pedido = self.conferir(1)[0]
        oc = next(o for o in pedido["ocs"] if o["estado"] == "atrasada")
        mensagem = self.conferencia.mensagem_cobranca(pedido, oc)
        self.assertIn("OC 4991", mensagem["texto"])
        self.assertIn("de atraso", mensagem["texto"])
        self.assertIn("#OC4991", mensagem["texto"])


class TestLancarPedido(Base):
    ENDERECO = {"address": "Rua Nova", "number": "7", "complement": "", "neighborhood": "Centro", "city": "Recife",
                "state": "PE", "zip_code": "50000-000"}

    def setUp(self):
        super().setUp()
        import lancar_pedido
        self.lp = importlib.reload(lancar_pedido)

    def test_busca_cliente_por_nome_e_por_documento(self):
        self.assertEqual(self.lp.buscar_clientes("Exemplo Um")[0]["id"], 1)
        self.assertEqual(self.lp.buscar_clientes("00000000000100")[0]["id"], 2)

    def test_le_os_dados_do_cliente_colados_do_whatsapp(self):
        dados = self.lp.interpretar_dados_cliente(
            "[14:05, 28/10/2026] Fulano: Nome: Maria Exemplo\nCPF 123.456.789-09\ncliente@exemplo.com\n"
            "(11) 91234-5678\nCEP: 01001-000\nRua das Flores, nº 100\nCentro\nSão Paulo/SP")
        self.assertEqual((dados["nome"], dados["documento"], dados["email"]),
                         ("Maria Exemplo", "123.456.789-09", "cliente@exemplo.com"))
        self.assertEqual((dados["rua"], dados["numero"], dados["cidade"], dados["uf"]),
                         ("Rua das Flores", "100", "São Paulo", "SP"))

    def test_nao_cadastra_cliente_duplicado(self):
        with self.assertRaisesRegex(ValueError, "Já existe cliente"):
            self.lp.cadastrar_cliente({"nome": "Outro", "documento": "000.000.000-00", "email": "x@exemplo.com",
                                       "cep": "01001-000", "rua": "Rua", "numero": "1", "bairro": "B", "cidade": "C",
                                       "uf": "SP"})

    def test_enderecos_de_cobranca_e_entrega_vao_em_lista_com_o_tipo(self):
        corpo = self.lp.montar_corpo(self.demo.CLIENTES[1], self.ENDERECO, self.ENDERECO,
                                     [{"product_id": 501, "variant_id": 0, "preco": 640, "quantidade": 2}],
                                     1, "Rápida", 100, "Pix", "PENDENTE")
        tipos = [e["type"] for e in corpo["Order"]["Customer"]["CustomerAddress"]]
        self.assertEqual(tipos, ["0", "1"])
        self.assertEqual(corpo["Order"]["ProductsSold"][0]["price"], "640.00")

    def test_lanca_e_confere_o_pedido(self):
        principal = self.demo.CLIENTES[1]["address"]
        with contextlib.redirect_stdout(io.StringIO()):
            r = self.lp.lancar(1, self.lp.endereco_principal(self.demo.CLIENTES[1]), self.ENDERECO,
                               [{"product_id": 501, "variant_id": 0, "preco": 640, "quantidade": 2}],
                               1, "Rápida", 100, "Pix", "PENDENTE")
        self.assertEqual(r["numero"], "2001")
        self.assertEqual(r["total"], 1380.0)
        self.assertTrue(r["entrega_ok"])
        self.assertEqual(self.demo.CLIENTES[1]["address"], principal)  # o cadastro não muda

    def test_nao_lanca_sem_produto(self):
        with self.assertRaises(ValueError):
            self.lp.lancar(1, {}, {}, [], 1, "Rápida", 0, "Pix", "PENDENTE")


class TestRegrasDoPedido(Base):
    def test_venda_do_bling_so_vale_com_o_numero_da_tray(self):
        conferir = self.fi.conferir_vinculo_tray
        self.assertEqual(conferir({"numeroLoja": "1002"}, "1002"), "numero_da_loja")
        self.assertIsNone(conferir({"numeroLoja": "1003"}, "1002"))
        self.assertEqual(conferir({"observacoes": "Pedido Tray 1002, pago no Pix"}, "1002"), "observacoes")
        self.assertIsNone(conferir({"observacoes": "Tray 10020"}, "1002"))  # número parecido não serve
        self.assertIsNone(conferir({"observacoes": "Cliente Exemplo Dois"}, "1002"))  # nunca pelo nome

    def test_retirada_no_deposito_nao_tem_frete(self):
        self.assertTrue(self.fi.eh_retirada("Retirada na Loja"))
        self.assertTrue(self.fi.eh_retirada("Retirar no depósito"))
        self.assertFalse(self.fi.eh_retirada("Transportadora Rápida"))


class TestKits(unittest.TestCase):
    def setUp(self):
        import sincronizar_kits
        self.sk = importlib.reload(sincronizar_kits)

    def test_preco_no_kit_com_quantidade_e_desconto(self):
        self.assertEqual(self.sk.preco_no_kit(100, {"quantity": "4", "price_rule": "1"}), 400.0)
        item = {"id": 1, "quantity": "2", "price_rule": "2", "discount_type": "%", "discount_value": "10"}
        self.assertEqual(self.sk.preco_no_kit(100, item), 180.0)

    def test_desconto_em_reais_nao_e_mexido(self):
        item = {"id": 1, "quantity": "1", "price_rule": "2", "discount_type": "$", "discount_value": "10"}
        with self.assertRaises(ValueError):
            self.sk.preco_no_kit(100, item)

    def test_preco_promocional_so_vale_dentro_do_periodo(self):
        hoje = date.today()
        variacao = {"price": "200", "promotional_price": "150", "start_promotion": (hoje - timedelta(days=1)).isoformat(),
                    "end_promotion": (hoje + timedelta(days=1)).isoformat()}
        self.assertEqual(self.sk.preco_vigente(variacao), 150.0)
        variacao["end_promotion"] = (hoje - timedelta(days=1)).isoformat()
        self.assertEqual(self.sk.preco_vigente(variacao), 200.0)

    def test_planejar_corrige_so_o_preco_errado(self):
        self.sk._cache_variacoes[501] = {11: 100.0, 12: 120.0}
        itens = [{"product_parent_id": 900, "product_id": 501, "quantity": "2", "price_rule": "1",
                  "discount_type": "%", "discount_value": "0",
                  "ProductVariantKit": [{"variant_id": 11, "product_kit_id": 1, "price": "200.00"},
                                        {"variant_id": 12, "product_kit_id": 1, "price": "180.00"}]}]
        payload, mudancas, faltantes = self.sk.planejar(itens)
        self.assertEqual(mudancas, [(501, 12, 180.0, 240.0)])
        self.assertEqual([v["price"] for v in payload[0]["ProductVariantKit"]], ["200.00", "240.00"])
        self.assertEqual(faltantes, [])


if __name__ == "__main__":
    unittest.main()
