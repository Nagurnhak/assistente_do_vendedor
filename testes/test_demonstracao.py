"""Fluxo completo de compra no modo demonstração, com a rede BLOQUEADA durante o teste
(prova de que a demonstração não acessa Bling, Trello, Tray nem WhatsApp).

Rode na pasta do projeto:  py -m unittest discover testes
"""
import builtins
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


def _proximo_dia_util(dia):
    while dia.weekday() >= 5:
        dia += timedelta(days=1)
    return dia


class TestDemonstracao(unittest.TestCase):
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

    def rodar(self, *respostas):
        it = iter(respostas)
        builtins.input = lambda *_: next(it)
        with contextlib.redirect_stdout(io.StringIO()):
            self.fi.processar_pedido()

    def novos_cards(self):
        return self.demo.CARDS[self.demo._INICIAIS:]

    def test_compra_com_produto_estruturado_personalizacao_e_frete_pela_tabela(self):
        self.rodar(
            "1002", "2",                        # pedido 1002, precisa comprar
            "", "",                             # transportadora do Bling; prazo = data da Tray
            "s", "s",                           # os dois itens precisam ser comprados
            "n", "s", "pintura preta", "50", "n",  # personalização só no tampo (da fábrica)
            "", "", "", "", "s",                # OC Metalúrgica (base)
            "", "", "", "", "s",                # OC Estofados (cadeiras)
            "", "", "", "", "", "s",            # OC Fábrica (tampo + personalização)
            "s", "s",                           # OCs enviadas pelo Bling (a da fábrica vai pelo Trello)
            "s", "F", "", "",                   # HTML: pessoa física, itens e personalização sugeridos
            "n", "1", "s",                      # card da fábrica: não urgente, aba 1, confirma
        )
        demo, fi = self.demo, self.fi
        obs = {demo.FORNECEDORES[o["fornecedor"]["id"]]: o["observacoes"] for o in demo.OCS.values()}
        self.assertEqual(len(obs), 3)
        self.assertIn("Base Aurora Aço Preto", obs["Metalúrgica Aurora"])
        self.assertIn("4x Cadeira Lina", obs["Estofados Horizonte"])
        self.assertIn("PERSONALIZAÇÃO", obs[demo.FABRICA])
        self.assertIn("pintura preta", obs[demo.FABRICA])

        # prazos pela tabela (Campinas/SP, pessoa física: 4 dias úteis de frete):
        # card da Logística = embarque máximo; OCs = embarque - 3 dias úteis de logística
        logistica, fabrica = self.novos_cards()
        self.assertEqual((logistica["lista"], fabrica["lista"]), ("Logística", "Marcenaria: Corte"))
        prevista = date.fromisoformat({o["dataPrevista"] for o in demo.OCS.values()}.pop())
        self.assertEqual(fi.somar_dias_uteis(prevista, fi.LOGISTICA_DIAS_UTEIS).isoformat(), logistica["prazo"])
        self.assertEqual(fabrica["prazo"], prevista.isoformat())

        # fichas no lugar dos prints, checklist de separação, observação e status
        self.assertEqual(logistica["anexos"], ["ficha_pedido_1002.png"])
        self.assertTrue(fabrica["anexos"][0].startswith("ficha_OC_"))
        self.assertEqual(len(logistica["checklists"][0]["checkItems"]), 4)  # base, tampo, personalização e cadeiras
        self.assertIn("OC 5001", demo.PEDIDOS_TRAY["1002"]["store_note"])
        self.assertEqual(demo.PEDIDOS[10002]["situacao"]["id"], 102)  # OC enviada
        self.assertEqual(demo.STATUS_TRAY["1002"], "Aguardando fornecedor")

    def test_tudo_em_estoque_vai_para_separacao(self):
        self.rodar("1001", "1", "", "", "n", "n", "s")  # estoque, sem personalização, sem HTML, confirma
        demo = self.demo
        self.assertEqual(demo.OCS, {})
        self.assertEqual(demo.PEDIDOS[10001]["situacao"]["id"], 101)  # Em separação
        self.assertEqual(demo.STATUS_TRAY["1001"], "Pedido em separação")
        card = self.novos_cards()[0]
        self.assertIn("Transportadora Rápida Ltda", card["nome"])
        self.assertEqual(card["anexos"], ["ficha_pedido_1001.png"])

    def test_pedido_inexistente_nao_cria_nada(self):
        self.rodar("999")
        self.assertEqual((self.demo.OCS, self.novos_cards()), ({}, []))

    def test_pedidos_para_comprar_vem_da_tray(self):
        pedidos = self.fi.pedidos_para_comprar()
        self.assertEqual([p["numero"] for p in pedidos], ["1001", "1002", "1003"])
        self.assertIn("4x Cadeira Lina - Cor: Grafite", pedidos[1]["itens"])

    def test_lista_a_separar_e_lembretes_da_logistica(self):
        fi = self.fi
        with contextlib.redirect_stdout(io.StringIO()):
            resumo = fi.organizar_a_separar(aplicar=True)
        self.assertEqual(resumo["total"], 2)
        self.assertEqual(len(resumo["parados"]), 1)  # o card que entrou na lista há 8 dias
        hoje = _proximo_dia_util(date.today())
        etapas = {m["pedido"]: m["etapa"] for m in fi.mensagens_logistica(hoje=hoje)}
        self.assertEqual(etapas, {"0998": "2", "0995": "atraso"})


class TestPrazosFrete(unittest.TestCase):
    def setUp(self):
        import ferramentas_internas as fi
        import prazos_frete
        fi.MODO_DEMO = True
        self.pf = prazos_frete

    def test_tabela_por_cidade_pf_e_pj(self):
        self.assertEqual(self.pf.prazo("Rápida Standard", "13000000", "Campinas", "SP")["dias"], 4)
        self.assertEqual(self.pf.prazo("TRANSPORTADORA RÁPIDA LTDA", "13000000", "Campinas", "SP", True)["dias"], 3)

    def test_regiao_local_vale_para_qualquer_transportadora(self):
        self.assertEqual(self.pf.prazo("Qualquer Uma", "01001000", "São Paulo", "SP")["dias"], 1)

    def test_sem_tabela_usa_a_regra_anterior(self):
        self.assertIsNone(self.pf.prazo("Retirada na loja", "50000000", "Recife", "PE")["dias"])
        self.assertIsNone(self.pf.prazo("Rápida", "50000000", "Recife", "PE")["dias"])


class TestFichas(unittest.TestCase):
    def test_ficha_do_pedido_e_da_oc_saem_em_png(self):
        try:
            import fichas
        except ImportError:
            self.skipTest("Pillow não instalado")
        pedido = {"numero": "1002", "data": "01/10/2026", "status": "A Enviar", "entrega": "23/10/2026",
                  "prazos": {"embarque": "22/10/2026", "atrasado": True, "compra": "01/10/2026", "entrega": "23/10/2026",
                             "fornecedores": "17/10/2026", "combinados": 15, "frete": "Rápida: 4 dias úteis",
                             "logistica": 3},
                  "cliente": "Cliente Exemplo", "endereco": ["Rua Exemplo, 1"],
                  "itens": [{"qtd": "1", "titulo": "Mesa Aurora", "ocs": "OC 5001"}], "html": [],
                  "frete": "Rápida", "transportadora": "Rápida", "pagamento": "Pix"}
        oc = {"numero": 5003, "fornecedor": "Fábrica", "pedido": "1002", "urgente": True, "atrasado": True,
              "data_prevista": "17/10/2026", "embarque": "22/10/2026", "entrega_cliente": "23/10/2026",
              "itens": [{"qtd": "1", "titulo": "Tampo Aurora 1,60m"}], "personalizacao": [("1x Tampo", "pintura preta")]}
        for png in (fichas.ficha_pedido(pedido), fichas.ficha_oc(oc)):
            self.assertTrue(png.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
