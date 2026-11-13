"""Abre a demonstração de verdade, percorre os módulos e gera os prints e o GIF do README em docs/exemplos/.

Serve também de teste de fumaça da janela: qualquer erro de tela ou do fluxo faz o script terminar com falha.
Precisa de um monitor (não fecha nem minimize a janela enquanto roda). Tudo é fictício: nada sai do computador.

Rode na pasta do projeto:  py docs/gerar_prints.py
"""
import os
import sys
import tkinter
import traceback
from tkinter import messagebox

from PIL import Image, ImageGrab

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
SAIDA = os.path.join(RAIZ, "docs", "exemplos")
LARGURA_GIF = 900
SEGUNDOS_POR_QUADRO = 2.2

import ferramentas_internas as fi  # noqa: E402

fi.MODO_DEMO = True
import demo  # noqa: E402

demo.ATRASO = 0.02
import app as modulo_app  # noqa: E402
import customtkinter as ctk  # noqa: E402

RESPOSTAS_1002 = [
    "2", "", "s", "s", "pintura preta", "1", "1", "50",
    "", "", "", "", "s", "", "", "", "", "s", "", "", "", "", "", "s",
    "s", "s", "n", "1", "s",
]
erros, quadros = [], []
terminal = sys.__stdout__
messagebox.askyesno = lambda *a, **k: True  # as confirmações da janela respondem "sim"
messagebox.showinfo = lambda *a, **k: "ok"
janela = modulo_app.App()
ctk.set_appearance_mode("light")
janela.report_callback_exception = lambda *e: erros.append("".join(traceback.format_exception(*e)))
janela.geometry("1280x820+10+10")
janela.attributes("-topmost", True)


def foto(nome=None, quadro=True):
    janela.update()
    x, y, w, h = janela.winfo_rootx(), janela.winfo_rooty(), janela.winfo_width(), janela.winfo_height()
    imagem = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).convert("RGB")
    if nome:
        imagem.save(os.path.join(SAIDA, nome), optimize=True)
        print("print:", nome, imagem.size, file=terminal)
    if quadro:
        quadros.append(imagem.resize((LARGURA_GIF, round(imagem.height * LARGURA_GIF / imagem.width)), Image.LANCZOS))


def esperar(condicao, depois, limite=60):
    """Chama depois() quando a condição for verdadeira (ou registra erro ao estourar o limite em segundos)."""
    def checar(restante):
        if condicao():
            janela.after(400, depois)
        elif restante <= 0:
            erros.append(f"esperei demais por: {depois.__name__}")
            passo_fim()
        else:
            janela.after(200, lambda: checar(restante - 0.2))
    checar(limite)


def passo_inicio():
    foto("tela_inicio.png")
    janela.mostrar("lancar")
    t = janela.telas["lancar"]
    t.busca_cliente.insert(0, "Exemplo Um")
    t.buscar_cliente()
    esperar(lambda: t.cliente and t.enderecos, passo_produto)


def passo_produto():
    t = janela.telas["lancar"]
    t.busca_produto.insert(0, "Cadeira Lina")
    t.buscar_produto()
    esperar(lambda: "Preço da Tray" in t.status_produto.cget("text"), passo_item)


def passo_item():
    t = janela.telas["lancar"]
    t.quantidade.delete(0, "end")
    t.quantidade.insert(0, "4")
    t.adicionar_item()
    t.parceiro_fixo.set("Ana Exemplo")
    t.alternar_parceiro()
    t.frete_nome.insert(0, "Transportadora Rápida")
    t.frete_valor.insert(0, "180,00")
    t.pagamento.insert(0, "Pix")
    t.atualizar_resumo()
    janela.after(300, passo_lancar)


def passo_lancar():
    foto("tela_lancar_pedido.png")
    t = janela.telas["lancar"]
    t.confirmar()
    esperar(lambda: "2001" in t.resultado.cget("text") or "2001" in str(demo.PEDIDOS_TRAY.keys()), passo_lancado)


def passo_lancado():
    t = janela.telas["lancar"]
    if not t.resultado.cget("text"):
        erros.append("Lançar pedido: a tela não mostrou o resultado")
    foto()
    janela.mostrar("conferencia")
    t = janela.telas["conferencia"]
    t.vendedor.set("Ana")
    t.carregar()
    esperar(lambda: t.pedidos, passo_atrasados)


def passo_atrasados():
    t = janela.telas["conferencia"]
    t.so_atrasados.select()
    t.desenhar()
    if [p["numero"] for p in t.pedidos if t._tem_atraso(p)] != ["1004"]:
        erros.append("Conferência: o filtro de atraso deveria trazer só o pedido 1004")
    janela.after(500, passo_cobrar)


def passo_cobrar():
    foto("tela_conferencia.png")
    t = janela.telas["conferencia"]
    pedido = t.pedidos[0]
    oc = next(o for o in pedido["ocs"] if o["estado"] == "atrasada")
    t.cobrar(pedido, oc)
    janela.after(500, passo_cadastro)


def fechar_dialogos(widget):
    for filho in widget.winfo_children():
        if isinstance(filho, tkinter.Toplevel):
            filho.destroy()
        else:
            fechar_dialogos(filho)


def passo_cadastro():
    fechar_dialogos(janela)
    janela.mostrar("cadastro")
    t = janela.telas["cadastro"]
    t.varrer()
    esperar(lambda: t.resultado, passo_cadastro_resultado)


def passo_cadastro_resultado():
    t = janela.telas["cadastro"]
    r = t.resultado["resumo"]
    if (r["desatualizado"], r["novos"], r["fora"]) != (2, 2, 1):
        erros.append(f"Cadastro: resumo inesperado {r}")
    t.marcar_todos(True)
    foto("tela_cadastro.png")
    t.aplicar()
    esperar(lambda: "itens atualizados" in t.status.cget("text"), passo_cadastro_aplicado)


def passo_cadastro_aplicado():
    t = janela.telas["cadastro"]
    if "problema" in t.status.cget("text"):
        erros.append("Cadastro: " + t.status.cget("text"))
    t.visao.set("Novos na tabela")
    t.trocar_visao()
    janela.after(400, passo_novos)


def passo_novos():
    foto("tela_cadastro_novos.png")
    janela.mostrar("compras")
    t = janela.telas["compras"]
    respostas = iter(RESPOSTAS_1002)
    t.iniciar("1002")
    tirou = [False]

    def responder():
        if not t.rodando:
            janela.after(800, passo_fim)
            return
        if t.aguardando:
            if not tirou[0] and "precisa comprar" in t.pergunta.cget("text"):
                tirou[0] = True
                foto("tela_compras.png")
            resposta = next(respostas, None)
            if resposta is None:
                erros.append(f"Compras: pergunta sem resposta: {t.pergunta.cget('text')}")
                return passo_fim()
            if t.aguardando == "opcoes":
                t.escolher(resposta, resposta)
            else:
                t.responder(resposta)
        janela.after(60, responder)
    janela.after(300, responder)


def passo_fim():
    if janela.telas["compras"].console.get("1.0", "end").count("=== ERRO ==="):
        erros.append(janela.telas["compras"].console.get("1.0", "end")[-1500:])
    if len(demo.CARDS) <= demo._INICIAIS:
        erros.append("Compras: nenhum card criado")
    if quadros:
        quadros[0].save(os.path.join(SAIDA, "demo_modulos.gif"), save_all=True, append_images=quadros[1:],
                        duration=int(SEGUNDOS_POR_QUADRO * 1000), loop=0, optimize=True)
    print("ERROS:" if erros else "SEM ERROS", *erros, sep="\n", file=terminal)
    terminal.flush()
    os._exit(1 if erros else 0)


janela.after(7000, passo_inicio)  # dá tempo da conferência automática das checklists
janela.mainloop()
