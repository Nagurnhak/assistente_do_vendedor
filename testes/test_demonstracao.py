"""Fluxo completo de compra no modo demonstração, com a rede BLOQUEADA durante o teste
(prova de que a demonstração não acessa Bling, Trello nem Tray).

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _sem_rede(*_, **__):
    raise AssertionError("o modo demonstração tentou acessar a rede!")


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

    def tearDown(self):
        socket.socket.connect, socket.create_connection = self._conectar, self._criar

    def rodar(self, *respostas):
        it = iter(respostas)
        builtins.input = lambda *_: next(it)
        with contextlib.redirect_stdout(io.StringIO()):
            self.fi.processar_pedido()

    def test_compra_com_produto_estruturado_e_personalizacao(self):
        self.rodar(
            "1002", "2",                          # pedido 1002, precisa comprar
            "n", "s", "pintura preta", "50", "n",  # personalização só na base
            "", "", "25/10/2026", "", "s",        # OC Metalúrgica
            "", "", "27/10/2026", "", "s",        # OC Estofados
            "", "", "", "30/10/2026", "", "s",    # OC Fábrica (tampo + personalização da base)
            "s",                                  # e-mails enviados
            "", "20",                             # transportadora do pedido, prazo 20 dias úteis
            "n", "1", "s",                        # card da fábrica: não urgente, aba 1, confirma
            "", "",                               # prints simulados
            "n",                                  # sem HTML
        )
        demo = self.demo
        obs = {demo.FORNECEDORES[o["fornecedor"]["id"]]: o["observacoes"] for o in demo.OCS.values()}
        self.assertEqual(obs["Metalúrgica Aurora"], "Pedido Tray: 1002 | 1x Base Aurora Aço Preto")
        self.assertEqual(obs["Estofados Horizonte"], "Pedido Tray: 1002 | 4x Cadeira Lina Cor:Grafite")
        self.assertEqual(obs[demo.FABRICA], "Pedido Tray: 1002 | 1x Tampo Aurora 1,60m | "
                                            "PERSONALIZAÇÃO: 1x Base Aurora Aço Preto: pintura preta")
        self.assertEqual([c["lista"] for c in demo.CARDS], ["Logística", "Marcenaria: Corte"])
        self.assertEqual(demo.PEDIDOS[10002]["situacao"]["id"], 102)  # OC enviada
        self.assertEqual(demo.STATUS_TRAY["1002"], "Mercadoria Solicitada ao depósito central")

    def test_tudo_em_estoque_vai_para_separacao(self):
        self.rodar("1001", "1", "n", "", "", "s", "", "n")  # estoque, sem personalização, Trello, print, sem HTML
        self.assertEqual(self.demo.OCS, {})
        self.assertEqual(self.demo.PEDIDOS[10001]["situacao"]["id"], 101)  # Em separação
        self.assertEqual(self.demo.STATUS_TRAY["1001"], "Pedido em separação")
        self.assertIn("Transportadora Rápida Ltda", self.demo.CARDS[0]["nome"])

    def test_pedido_inexistente_nao_cria_nada(self):
        self.rodar("999")
        self.assertEqual((self.demo.OCS, self.demo.CARDS), ({}, []))


if __name__ == "__main__":
    unittest.main()
