"""Regras de negócio (não acessam nada fora do computador).

Rode na pasta do projeto:  py -m unittest discover testes
"""
import builtins
import contextlib
import io
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import ferramentas_internas as fi  # noqa: E402

fi.MODO_DEMO = True  # config fictícia: nenhum config.json é lido


def responder(*respostas):
    it = iter(respostas)
    builtins.input = lambda *_: next(it)


class TestNumeros(unittest.TestCase):
    def test_formato_brasileiro(self):
        casos = {"150,50": 150.5, "1.500,50": 1500.5, "1.500": 1500.0, "R$ 1.234,56": 1234.56,
                 "150.50": 150.5, "0,5": 0.5}
        for texto, esperado in casos.items():
            self.assertEqual(fi.converter_numero(texto), esperado, texto)

    def test_texto_invalido(self):
        for texto in ("abc", "", "1,2,3"):
            with self.assertRaises(ValueError):
                fi.converter_numero(texto)

    def test_reais(self):
        self.assertEqual(fi.formatar_reais(1425.48), "R$ 1.425,48")
        self.assertEqual(fi.formatar_reais(1500000), "R$ 1.500.000,00")


class TestCalculadora(unittest.TestCase):
    def test_descontos(self):
        valores = fi.valores_desconto(1500.50, 30.00)
        self.assertEqual(valores, {"12x": 1455.47, "3x": 1384.2, "pix": 1312.93})


class TestPrazoTrello(unittest.TestCase):
    def test_folga_de_10_dias_uteis(self):
        for combinados, no_trello in [(20, 10), (25, 15), (11, 1), (10, 10), (8, 8), (0, 0)]:
            self.assertEqual(fi.dias_uteis_trello(combinados), no_trello)

    def test_data_do_card(self):
        responder("20")
        with contextlib.redirect_stdout(io.StringIO()):
            iso = fi.pedir_data_limite()
        self.assertEqual(iso[:10], fi.somar_dias_uteis(date.today(), 10).isoformat())

    def test_dias_uteis_pulam_fim_de_semana(self):
        sexta = date(2026, 10, 16)
        self.assertEqual(fi.somar_dias_uteis(sexta, 1), date(2026, 10, 19))  # segunda


class TestTextos(unittest.TestCase):
    def test_nome_sem_sufixo_da_loja(self):
        self.assertEqual(fi.nome_curto("Cadeira Lina - Loja Exemplo Cor:Grafite"), "Cadeira Lina Cor:Grafite")

    def test_lista_nao_quebra_numero_com_virgula(self):
        self.assertEqual(fi.separar_lista("2,5x Tecido, 1x Mesa 1,20m"), ["2,5x Tecido", "1x Mesa 1,20m"])
        self.assertEqual(fi.separar_lista("1x Mesa, Branca", digitado=False), ["1x Mesa, Branca"])

    def test_html_escapa_e_calcula_datas(self):
        html, embarque, entrega = fi.montar_descricao_html("F", 10, ["2x Cadeira <Lina>"], [],
                                                           hoje=date(2026, 10, 15))
        self.assertIn("2x Cadeira &lt;Lina&gt;", html)
        self.assertEqual(entrega, date(2026, 10, 29))
        self.assertEqual(embarque, date(2026, 10, 22))

    def test_fabrica_reconhecida_pelo_identificador(self):
        self.assertTrue(fi.e_fabrica("FABRICA PROPRIA EXEMPLO LTDA"))
        self.assertFalse(fi.e_fabrica("Metalúrgica Aurora"))


class TestEscolherNoTerminal(unittest.TestCase):
    def test_aceita_chave_rotulo_ou_palavra(self):
        tipo = [("F", "Pessoa física"), ("J", "Pessoa jurídica")]
        with contextlib.redirect_stdout(io.StringIO()):
            for digitado, esperado in [("f", "F"), ("fisica", "F"), ("Pessoa Jurídica", "J"), ("x", None)]:
                if esperado is None:
                    responder(digitado, "j")
                    esperado = "J"
                else:
                    responder(digitado)
                self.assertEqual(fi.escolher("?", tipo), esperado)


if __name__ == "__main__":
    unittest.main()
