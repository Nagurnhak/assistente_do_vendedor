"""
Assistente do Vendedor - janela do aplicativo.

Telas:
    Início       cartões clicáveis para cada ferramenta + situação das integrações
    Calculadora  valores em 12x, 3x e à vista no Pix
    Compras      o fluxo de compras (Tray -> Bling -> Trello) guiado dentro da janela
    HTML         descrição padrão Tray, com os itens puxados do Bling

A lógica continua no ferramentas_internas.py; este arquivo só cuida da janela.
O fluxo de compras usa print()/input(): aqui eles são ligados ao painel da tela
de Compras (o fluxo roda numa thread separada para a janela não travar).

Rode:  py app.py
"""

import builtins
import os
import queue
import re
import sys
import threading
import time
import webbrowser
from datetime import date, datetime

import customtkinter as ctk

import ferramentas_internas as fi

TITULO = "Assistente do Vendedor"

# Cores (claro, escuro) - identidade laranja
CARTAO = ("#FFFFFF", "#2A2622")
CARTAO_HOVER = ("#FFF1E6", "#3A2F27")
BORDA = ("#EADFD6", "#3D3530")
LATERAL = ("#FBF4EE", "#1F1B18")
SUAVE = ("#6B625B", "#A89F98")
DESTAQUE = ("#D9631E", "#F28C38")
DESTAQUE_HOVER = ("#B8501A", "#D9762B")
VERDE = ("#1E7B4F", "#4CC38A")
AMBAR = ("#9A6200", "#E8AE4A")
PRAZO =("#B42318", "#F28B82")
VERMELHO = ("#B42318", "#F28B82")
MATIZ_LARANJA = 0.065  # ~23° no círculo de cores


def aplicar_tema_laranja():
    """Troca os azuis do tema padrão do customtkinter por laranjas de mesma luminosidade
    (botões, seleções, barras, caixas de marcar...)."""
    import colorsys

    def trocar(cor):
        if not (isinstance(cor, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", cor)):
            return cor
        r, g, b = (int(cor[i:i + 2], 16) / 255 for i in (1, 3, 5))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        if 0.5 <= h <= 0.72 and s >= 0.3:  # é um azul
            r, g, b = colorsys.hls_to_rgb(MATIZ_LARANJA, l, min(1.0, s * 1.15))
            return "#%02X%02X%02X" % tuple(round(x * 255) for x in (r, g, b))
        return cor

    def percorrer(valor):
        if isinstance(valor, dict):
            return {k: percorrer(v) for k, v in valor.items()}
        if isinstance(valor, list):
            return [percorrer(v) for v in valor]
        return trocar(valor)

    tema = ctk.ThemeManager.theme
    for chave in list(tema):
        tema[chave] = percorrer(tema[chave])
    tema["CTkButton"]["fg_color"] = list(DESTAQUE)
    tema["CTkButton"]["hover_color"] = list(DESTAQUE_HOVER)
    tema["CTkButton"]["text_color"] = ["#FFFFFF", "#FFFFFF"]
    tema["CTkSegmentedButton"]["selected_color"] = list(DESTAQUE)
    tema["CTkSegmentedButton"]["selected_hover_color"] = list(DESTAQUE_HOVER)

DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


def recurso(nome):
    """Arquivo que vai dentro do .exe (ex.: o ícone)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nome)


def fonte(tamanho=14, negrito=False, familia="Segoe UI"):
    return ctk.CTkFont(family=familia, size=tamanho, weight="bold" if negrito else "normal")


def data_por_extenso(d):
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"


def estado_integracoes():
    """Só confere o config.json (não acessa a internet). Na demonstração: tudo simulado."""
    if fi.MODO_DEMO:
        return {"Bling": "simulado", "Trello": "simulado", "Tray": "simulado"}
    estado = {"Bling": False, "Trello": False, "Tray": False}
    try:
        cfg = fi.config()
    except Exception:
        return estado
    preenchido = lambda v: bool(v) and not str(v).upper().startswith(("SEU_", "SUA_"))
    estado["Bling"] = preenchido((cfg.get("bling") or {}).get("client_id"))
    estado["Trello"] = preenchido((cfg.get("trello") or {}).get("key"))
    try:
        import TRAY
        estado["Tray"] = TRAY.tray_configurada()
    except Exception:
        pass
    return estado


# ---------------------------------------------------------------------------
# PONTE print()/input() <-> janela
# ---------------------------------------------------------------------------

class Ponte:
    """Recebe o que o fluxo imprime e entrega as respostas digitadas na janela."""

    def __init__(self):
        self.saida = queue.Queue()
        self.perguntas = queue.Queue()
        self.respostas = queue.Queue()

    def write(self, texto):
        if texto:
            self.saida.put(texto)
        return len(texto or "")

    def flush(self):
        pass

    def input(self, pergunta=""):
        pergunta = str(pergunta)
        if threading.current_thread() is threading.main_thread():  # não deveria acontecer
            return ctk.CTkInputDialog(title=TITULO, text=pergunta).get_input() or ""
        self.write(pergunta)
        self.perguntas.put(("texto", pergunta, None))
        return self.respostas.get()

    def escolher(self, pergunta, opcoes):
        """Pergunta com opções fixas: a janela mostra um botão para cada uma."""
        self.write(f"\n{pergunta} ")
        self.perguntas.put(("opcoes", pergunta, opcoes))
        return self.respostas.get()


# ---------------------------------------------------------------------------
# COMPONENTES
# ---------------------------------------------------------------------------

class Cartao(ctk.CTkFrame):
    """Cartão clicável da tela inicial."""

    def __init__(self, master, icone, titulo, descricao, ao_clicar):
        super().__init__(master, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        self.ao_clicar = ao_clicar
        ctk.CTkLabel(self, text=icone, font=fonte(34)).pack(anchor="w", padx=22, pady=(22, 6))
        ctk.CTkLabel(self, text=titulo, font=fonte(18, True), anchor="w").pack(anchor="w", padx=22)
        ctk.CTkLabel(self, text=descricao, font=fonte(13), text_color=SUAVE, wraplength=230,
                     justify="left", anchor="w").pack(anchor="w", padx=22, pady=(6, 14))
        ctk.CTkLabel(self, text="Abrir  →", font=fonte(13, True), text_color=DESTAQUE).pack(
            anchor="w", padx=22, pady=(0, 20))
        self._ligar(self)

    def _ligar(self, widget):
        widget.bind("<Button-1>", lambda e: self.ao_clicar())
        widget.bind("<Enter>", lambda e: self.configure(fg_color=CARTAO_HOVER, border_color=DESTAQUE))
        widget.bind("<Leave>", lambda e: self.configure(fg_color=CARTAO, border_color=BORDA))
        try:
            widget.configure(cursor="hand2")
        except Exception:
            pass
        for filho in widget.winfo_children():
            self._ligar(filho)


class CaixaValor(ctk.CTkFrame):
    """Cartão de resultado: rótulo, valor grande e observação."""

    def __init__(self, master, rotulo, observacao, cor=DESTAQUE):
        super().__init__(master, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA)
        ctk.CTkLabel(self, text=rotulo, font=fonte(13), text_color=SUAVE).pack(anchor="w", padx=18, pady=(16, 0))
        self.valor = ctk.CTkLabel(self, text="—", font=fonte(26, True), text_color=cor)
        self.valor.pack(anchor="w", padx=18, pady=(2, 0))
        self.obs = ctk.CTkLabel(self, text=observacao, font=fonte(12), text_color=SUAVE)
        self.obs.pack(anchor="w", padx=18, pady=(0, 16))


def titulo_tela(master, titulo, subtitulo):
    ctk.CTkLabel(master, text=titulo, font=fonte(26, True), anchor="w").pack(anchor="w", padx=36, pady=(30, 0))
    ctk.CTkLabel(master, text=subtitulo, font=fonte(14), text_color=SUAVE, anchor="w").pack(
        anchor="w", padx=36, pady=(4, 20))


def campo(master, rotulo, **kwargs):
    ctk.CTkLabel(master, text=rotulo, font=fonte(13, True), anchor="w").pack(anchor="w", pady=(10, 4))
    entrada = ctk.CTkEntry(master, height=38, font=fonte(14), **kwargs)
    entrada.pack(fill="x")
    return entrada


# ---------------------------------------------------------------------------
# TELAS
# ---------------------------------------------------------------------------

class TelaInicio(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text="Olá! O que vamos fazer hoje?", font=fonte(28, True), anchor="w").pack(
            anchor="w", padx=36, pady=(34, 0))
        ctk.CTkLabel(self, text=data_por_extenso(date.today()).capitalize(), font=fonte(14),
                     text_color=SUAVE).pack(anchor="w", padx=36, pady=(4, 26))

        grade = ctk.CTkFrame(self, fg_color="transparent")
        grade.pack(fill="x", padx=28)
        cartoes = [
            ("🧮", "Calculadora de descontos", "Valores em 12x, 3x e à vista no Pix a partir do total e do frete.",
             "calculadora"),
            ("🛒", "Realizar compras", "Pedido da Tray → OCs no Bling → cards no Trello, passo a passo.",
             "compras"),
            ("📝", "Descrição em HTML", "Observação padrão do pedido, com os itens puxados do Bling.", "html"),
        ]
        for coluna, (icone, titulo, descricao, tela) in enumerate(cartoes):
            grade.grid_columnconfigure(coluna, weight=1, uniform="cartoes")
            Cartao(grade, icone, titulo, descricao, lambda t=tela: app.mostrar(t)).grid(
                row=0, column=coluna, sticky="nsew", padx=8)

        ctk.CTkLabel(self, text="Integrações", font=fonte(15, True)).pack(anchor="w", padx=36, pady=(34, 8))
        linha = ctk.CTkFrame(self, fg_color="transparent")
        linha.pack(anchor="w", padx=30)
        for nome, ok in estado_integracoes().items():
            chip = ctk.CTkFrame(linha, fg_color=CARTAO, corner_radius=20, border_width=1, border_color=BORDA)
            chip.pack(side="left", padx=6)
            ctk.CTkLabel(chip, text="●", font=fonte(14), text_color=VERDE if ok else SUAVE).pack(
                side="left", padx=(14, 6), pady=6)
            situacao = ok if isinstance(ok, str) else ("configurado" if ok else "não configurado")
            ctk.CTkLabel(chip, text=f"{nome}: {situacao}", font=fonte(13)).pack(side="left", padx=(0, 14))

        ctk.CTkLabel(self, text="Checklists de separação no Trello", font=fonte(15, True)).pack(
            anchor="w", padx=36, pady=(30, 4))
        ctk.CTkLabel(self, text="O Assistente confere as OCs no Bling e atualiza o texto ao lado de cada peça "
                                "(prazo, atraso, recebida). Os itens continuam desmarcados para a equipe marcar.",
                     font=fonte(13), text_color=SUAVE, wraplength=820, justify="left").pack(anchor="w", padx=36)
        linha_ck = ctk.CTkFrame(self, fg_color="transparent")
        linha_ck.pack(anchor="w", padx=36, pady=(10, 0))
        self.botao_checklists = ctk.CTkButton(linha_ck, text="Atualizar agora", width=150, height=36,
                                              font=fonte(13), fg_color="transparent", border_width=1,
                                              border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                              command=app.atualizar_checklists)
        self.botao_checklists.pack(side="left")
        self.status_checklists = ctk.CTkLabel(linha_ck, text="", font=fonte(13), text_color=SUAVE)
        self.status_checklists.pack(side="left", padx=12)
        self.status_a_separar = ctk.CTkLabel(self, text="A Separar: medindo...", font=fonte(13), text_color=SUAVE,
                                             wraplength=820, justify="left", anchor="w")
        self.status_a_separar.pack(anchor="w", padx=36, pady=(8, 0))


class TelaCalculadora(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        titulo_tela(self, "Calculadora de descontos", "Digite o total dos produtos e o frete. O frete não tem desconto.")

        form = ctk.CTkFrame(self, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        form.pack(fill="x", padx=36)
        linha = ctk.CTkFrame(form, fg_color="transparent")
        linha.pack(fill="x", padx=22, pady=(12, 0))
        linha.grid_columnconfigure((0, 1), weight=1, uniform="campos")
        esq, dir_ = ctk.CTkFrame(linha, fg_color="transparent"), ctk.CTkFrame(linha, fg_color="transparent")
        esq.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        dir_.grid(row=0, column=1, sticky="ew", padx=(10, 0))
        self.produtos = campo(esq, "Total dos produtos", placeholder_text="Ex.: 1.500,50")
        self.frete = campo(dir_, "Frete", placeholder_text="Ex.: 30,00")
        for entrada in (self.produtos, self.frete):
            entrada.bind("<Return>", lambda e: self.calcular())

        rodape = ctk.CTkFrame(form, fg_color="transparent")
        rodape.pack(fill="x", padx=22, pady=18)
        ctk.CTkButton(rodape, text="Calcular", height=40, width=150, font=fonte(14, True),
                      command=self.calcular).pack(side="left")
        self.copiar = ctk.CTkButton(rodape, text="Copiar valores", height=40, width=150, font=fonte(14),
                                    fg_color="transparent", border_width=1, text_color=DESTAQUE,
                                    command=self.copiar_valores, state="disabled")
        self.copiar.pack(side="left", padx=10)
        self.aviso = ctk.CTkLabel(rodape, text="", font=fonte(13), text_color=VERMELHO)
        self.aviso.pack(side="left", padx=10)

        resultados = ctk.CTkFrame(self, fg_color="transparent")
        resultados.pack(fill="x", padx=28, pady=22)
        resultados.grid_columnconfigure((0, 1, 2), weight=1, uniform="valores")
        self.caixas = {
            "12x": CaixaValor(resultados, "Até 12x sem juros", "5% de desconto nos produtos"),
            "3x": CaixaValor(resultados, "Até 3x sem juros", "9,75% de desconto nos produtos"),
            "pix": CaixaValor(resultados, "À vista no Pix", "14,5% de desconto nos produtos", VERDE),
        }
        for coluna, caixa in enumerate(self.caixas.values()):
            caixa.grid(row=0, column=coluna, sticky="nsew", padx=8)
        self.resumo = ""

    def ao_mostrar(self):
        self.produtos.focus_set()

    def calcular(self):
        try:
            produtos = fi.converter_numero(self.produtos.get().strip())
            frete = fi.converter_numero(self.frete.get().strip() or "0")
        except ValueError:
            self.aviso.configure(text="Digite apenas números, por exemplo: 1.500,50")
            return
        if produtos < 0 or frete < 0:
            self.aviso.configure(text="Os valores não podem ser negativos.")
            return
        self.aviso.configure(text="")
        valores = fi.valores_desconto(produtos, frete)
        for chave, caixa in self.caixas.items():
            caixa.valor.configure(text=fi.formatar_reais(valores[chave]))
        self.resumo = (f"Até 12x sem juros: {fi.formatar_reais(valores['12x'])}\n"
                       f"Até 3x sem juros: {fi.formatar_reais(valores['3x'])}\n"
                       f"À vista no Pix: {fi.formatar_reais(valores['pix'])}")
        self.copiar.configure(state="normal", text="Copiar valores")

    def copiar_valores(self):
        self.app.copiar(self.resumo)
        self.copiar.configure(text="Copiado ✓")


class TelaHTML(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        titulo_tela(self, "Descrição em HTML",
                    "Comece pelo número do pedido: os itens vêm do Bling e o HTML vai para a Tray.")
        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        corpo.grid_columnconfigure(0, weight=5, uniform="colunas")
        corpo.grid_columnconfigure(1, weight=6, uniform="colunas")
        corpo.grid_rowconfigure(0, weight=1)

        # --- formulário ---
        form = ctk.CTkScrollableFrame(corpo, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        form.grid(row=0, column=0, sticky="nsew", padx=8)
        interno = ctk.CTkFrame(form, fg_color="transparent")
        interno.pack(fill="both", expand=True, padx=14, pady=(4, 16))

        ctk.CTkLabel(interno, text="Nº do pedido na Tray", font=fonte(13, True)).pack(anchor="w", pady=(10, 4))
        linha = ctk.CTkFrame(interno, fg_color="transparent")
        linha.pack(fill="x")
        self.numero = ctk.CTkEntry(linha, height=38, font=fonte(14), placeholder_text="Ex.: 1002")
        self.numero.pack(side="left", fill="x", expand=True)
        self.numero.bind("<Return>", lambda e: self.buscar_itens())
        self.botao_buscar = ctk.CTkButton(linha, text="Buscar itens no Bling", height=38, font=fonte(13, True),
                                          command=self.buscar_itens)
        self.botao_buscar.pack(side="left", padx=(8, 0))
        self.status_busca = ctk.CTkLabel(interno, text="", font=fonte(12), text_color=SUAVE, anchor="w")
        self.status_busca.pack(anchor="w")

        ctk.CTkLabel(interno, text="Tipo de cliente", font=fonte(13, True)).pack(anchor="w", pady=(8, 4))
        self.tipo = ctk.CTkSegmentedButton(interno, values=["Pessoa física", "Pessoa jurídica"], height=34,
                                           font=fonte(13), command=lambda _: self.alternar_pj())
        self.tipo.set("Pessoa física")
        self.tipo.pack(fill="x")

        self.pj = ctk.CTkFrame(interno, fg_color="transparent")
        self.faturado = campo(self.pj, "Pedido faturado (quantos dias)", placeholder_text="Ex.: 28")
        ctk.CTkLabel(self.pj, text="Checklist realizado?", font=fonte(13, True)).pack(anchor="w", pady=(10, 4))
        self.checklist = ctk.CTkSegmentedButton(self.pj, values=["Sim", "Não"], height=34, font=fonte(13))
        self.checklist.set("Sim")
        self.checklist.pack(fill="x")
        self.pasta = campo(self.pj, "Pasta")
        self.info_nf = campo(self.pj, "Informações adicionais de nota fiscal")

        self.depois_pj = ctk.CTkFrame(interno, fg_color="transparent")
        self.depois_pj.pack(fill="x")
        self.dias = campo(self.depois_pj, "Prazo combinado (dias úteis)", placeholder_text="Ex.: 10")
        ctk.CTkLabel(self.depois_pj, text="Itens do pedido (um por linha)", font=fonte(13, True)).pack(
            anchor="w", pady=(10, 4))
        self.itens = ctk.CTkTextbox(self.depois_pj, height=110, font=fonte(14), border_width=1, wrap="word")
        self.itens.pack(fill="x")
        ctk.CTkLabel(self.depois_pj, text="Personalização (uma por linha)", font=fonte(13, True)).pack(
            anchor="w", pady=(10, 4))
        self.personalizacao = ctk.CTkTextbox(self.depois_pj, height=80, font=fonte(14), border_width=1, wrap="word")
        self.personalizacao.pack(fill="x")
        ctk.CTkButton(self.depois_pj, text="Gerar HTML", height=42, font=fonte(14, True),
                      command=self.gerar).pack(fill="x", pady=(18, 0))
        self.aviso = ctk.CTkLabel(self.depois_pj, text="", font=fonte(13), text_color=VERMELHO)
        self.aviso.pack(anchor="w", pady=(6, 0))

        # --- resultado ---
        lado = ctk.CTkFrame(corpo, fg_color="transparent")
        lado.grid(row=0, column=1, sticky="nsew", padx=8)
        datas = ctk.CTkFrame(lado, fg_color="transparent")
        datas.pack(fill="x")
        datas.grid_columnconfigure((0, 1), weight=1, uniform="datas")
        self.embarque = CaixaValor(datas, "Embarque máximo", "prazo menos o transporte", PRAZO)
        self.entrega = CaixaValor(datas, "Entrega prevista", "dias úteis a partir de hoje")
        self.embarque.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entrega.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        caixa = ctk.CTkFrame(lado, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        caixa.pack(fill="both", expand=True, pady=(16, 0))
        ctk.CTkLabel(caixa, text="HTML gerado", font=fonte(14, True)).pack(anchor="w", padx=18, pady=(14, 6))
        self.saida = ctk.CTkTextbox(caixa, font=fonte(12, familia="Consolas"), wrap="word", border_width=1)
        self.saida.pack(fill="both", expand=True, padx=18)
        rodape = ctk.CTkFrame(caixa, fg_color="transparent")
        rodape.pack(fill="x", padx=18, pady=14)
        self.botao_copiar = ctk.CTkButton(rodape, text="Copiar HTML", height=38, font=fonte(13, True),
                                          command=self.copiar_html, state="disabled")
        self.botao_copiar.pack(side="left")
        self.status_tray = ctk.CTkLabel(rodape, text="", font=fonte(12), text_color=SUAVE, wraplength=330,
                                        justify="left")
        self.status_tray.pack(side="left", padx=12)

    def ao_mostrar(self):
        self.numero.focus_set()

    def alternar_pj(self):
        if self.tipo.get() == "Pessoa jurídica":
            self.pj.pack(fill="x", before=self.depois_pj)
        else:
            self.pj.pack_forget()

    def buscar_itens(self):
        numero = self.numero.get().strip()
        if not numero:
            self.status_busca.configure(text="Digite o número do pedido.", text_color=VERMELHO)
            return
        self.botao_buscar.configure(state="disabled", text="Buscando...")
        self.status_busca.configure(text="Consultando o Bling...", text_color=SUAVE)

        def terminou(itens, erro):
            self.botao_buscar.configure(state="normal", text="Buscar itens no Bling")
            if erro or not itens:
                self.status_busca.configure(text=f"Não encontrei itens para o pedido {numero}: digite à mão.",
                                            text_color=AMBAR)
                return
            self.itens.delete("1.0", "end")
            self.itens.insert("1.0", "\n".join(itens.split("; ")))
            self.status_busca.configure(text=f"Itens do pedido {numero} puxados do Bling ✓", text_color=VERDE)

        self.app.em_segundo_plano(lambda: fi.itens_do_pedido_bling(numero), terminou)

    def gerar(self):
        try:
            dias = int(self.dias.get().strip())
            if dias < 0:
                raise ValueError
        except ValueError:
            self.aviso.configure(text="Prazo combinado: digite o número de dias úteis (ex.: 10).")
            return
        self.aviso.configure(text="")
        separar = lambda caixa: [p.strip() for p in re.split(r"[;\n]", caixa.get("1.0", "end")) if p.strip()]
        tipo = "J" if self.tipo.get() == "Pessoa jurídica" else "F"
        extras = {"faturado": self.faturado.get().strip(), "checklist": self.checklist.get(),
                  "pasta": self.pasta.get().strip(), "info_nf": self.info_nf.get().strip()}
        html, embarque, entrega = fi.montar_descricao_html(tipo, dias, separar(self.itens),
                                                           separar(self.personalizacao), extras)
        self.embarque.valor.configure(text=embarque.strftime("%d/%m/%Y"))
        self.entrega.valor.configure(text=entrega.strftime("%d/%m/%Y"))
        self.saida.delete("1.0", "end")
        self.saida.insert("1.0", html)
        self.html = html
        self.botao_copiar.configure(state="normal", text="Copiar HTML")

        numero = self.numero.get().strip()
        if not numero:
            self.status_tray.configure(text="Sem número do pedido: copie e cole nas observações na Tray.",
                                       text_color=SUAVE)
            return
        self.status_tray.configure(text="Gravando na Tray...", text_color=SUAVE)

        def gravar():
            if fi.tray() is None:
                return None
            return fi.na_tray(f"gravar o HTML nas observações do pedido {numero}",
                              "adicionar_observacao", numero, html)

        def terminou(resultado, erro):
            if resultado is None and not erro:
                self.status_tray.configure(text="Tray ainda não configurada: copie e cole nas observações do "
                                                "pedido.", text_color=SUAVE)
            elif resultado:
                self.status_tray.configure(text=f"Gravado nas observações do pedido {numero} na Tray ✓",
                                           text_color=VERDE)
            else:
                self.status_tray.configure(text="Não consegui gravar na Tray: copie e cole manualmente.",
                                           text_color=AMBAR)

        self.app.em_segundo_plano(gravar, terminou)

    def copiar_html(self):
        self.app.copiar(self.html)
        self.botao_copiar.configure(text="Copiado ✓")


def _sobre_mensagem(m):
    if m.get("tipo") == "logistica":
        return f"card da Logística · pedido {m['pedido']}"
    return f"OC {m['oc_numero']} · pedido {m['pedido']}"


class TelaMensagens(ctk.CTkFrame):
    """Mensagens do dia para os fornecedores (régua de 14 / 7 dias úteis e cobrança diária)."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        titulo_tela(self, "Mensagens do dia",
                    "Lembretes e cobranças aos fornecedores e à Logística pelo WhatsApp, "
                    "conforme a data de embarque do pedido.")
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=36, pady=(0, 12))
        ctk.CTkButton(barra, text="Atualizar lista", height=38, width=140, font=fonte(13),
                      fg_color="transparent", border_width=1, border_color=DESTAQUE, text_color=DESTAQUE,
                      hover_color=CARTAO_HOVER, command=app.atualizar_checklists).pack(side="left")
        self.botao_enviar = ctk.CTkButton(barra, text="Enviar pelo WhatsApp agora", height=38, width=220,
                                          font=fonte(13, True), command=lambda: app.enviar_whatsapp())
        self.botao_enviar.pack(side="left", padx=8)
        ctk.CTkButton(barra, text="Conectar WhatsApp", height=38, width=160, font=fonte(13),
                      fg_color="transparent", border_width=1, border_color=DESTAQUE, text_color=DESTAQUE,
                      hover_color=CARTAO_HOVER, command=app.conectar_whatsapp).pack(side="left")
        self.status = ctk.CTkLabel(barra, text="", font=fonte(13), text_color=SUAVE)
        self.status.pack(side="left", padx=12)
        self.modo = ctk.CTkLabel(self, text="", font=fonte(12), text_color=AMBAR, anchor="w")
        self.modo.pack(anchor="w", padx=36, pady=(0, 6))
        self.atualizar_modo()

        linha_visao = ctk.CTkFrame(self, fg_color="transparent")
        linha_visao.pack(fill="x", padx=36, pady=(0, 8))
        self.visao = ctk.CTkSegmentedButton(linha_visao, values=["Mensagens de hoje", "Histórico de envios"],
                                            font=fonte(13), height=34, command=self.trocar_visao)
        self.visao.set("Mensagens de hoje")
        self.visao.pack(side="left")
        self.botao_exportar = ctk.CTkButton(linha_visao, text="Exportar para Excel", height=34, width=160,
                                            font=fonte(13), fg_color="transparent", border_width=1,
                                            border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                            command=self.exportar_historico)
        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        self._mensagens = []
        self.mostrar_mensagens([])

    def atualizar_modo(self):
        try:
            import WHATSAPP
            c = WHATSAPP.cfg()
        except Exception:
            self.modo.configure(text="Envio automático indisponível neste computador (WhatsApp Web não instalado).")
            return
        if c["modo_teste"]:
            texto = ("MODO TESTE: as mensagens vão para os números de teste ("
                     + ", ".join(c["numeros_teste"] or ["nenhum"]) + "), não para os fornecedores.")
        else:
            texto = "Envio para os fornecedores ativado."
        texto += (f" Envio automático: ligado, a partir das {c['horario']} em dias úteis."
                  if c["envio_automatico"] else " Envio automático: desligado (use o botão).")
        self.modo.configure(text=texto, text_color=AMBAR if c["modo_teste"] else SUAVE)

    # ----- visões: mensagens de hoje / histórico -----

    def trocar_visao(self, _=None):
        if self.visao.get() == "Histórico de envios":
            self.botao_exportar.pack(side="left", padx=10)
            self.mostrar_historico()
        else:
            self.botao_exportar.pack_forget()
            self.mostrar_mensagens(self._mensagens)

    def exportar_historico(self):
        try:
            caminho = fi.exportar_historico_csv()
            os.startfile(caminho)  # abre no Excel
            self.status.configure(text=f"Histórico exportado: {os.path.basename(caminho)}", text_color=VERDE)
        except Exception as erro:
            self.status.configure(text=f"Não consegui exportar o histórico: {erro}", text_color=AMBAR)

    def mostrar_historico(self):
        for filho in self.lista.winfo_children():
            filho.destroy()
        envios = fi.carregar_historico(limite=200)
        if not envios:
            vazio = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA)
            vazio.pack(fill="x", padx=8, pady=6)
            ctk.CTkLabel(vazio, text="Nenhum envio registrado ainda", font=fonte(15, True)).pack(
                anchor="w", padx=18, pady=(14, 2))
            ctk.CTkLabel(vazio, text="Cada mensagem enviada (automática ou marcada como enviada) fica registrada aqui.",
                         font=fonte(13), text_color=SUAVE).pack(anchor="w", padx=18, pady=(0, 14))
            return
        for e in envios:
            cartao = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=12, border_width=1, border_color=BORDA)
            cartao.pack(fill="x", padx=8, pady=4)
            topo = ctk.CTkFrame(cartao, fg_color="transparent")
            topo.pack(fill="x", padx=16, pady=(10, 2))
            quando = datetime.strptime(e["data_hora"], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
            ctk.CTkLabel(topo, text=quando, font=fonte(13, True)).pack(side="left")
            ctk.CTkLabel(topo, text=f"  {e['fornecedor']} · OC {e['oc']} · pedido {e['pedido']}",
                         font=fonte(13)).pack(side="left")
            selos = [("ENVIADA" if e["resultado"] == "enviada" else "FALHOU",
                      VERDE if e["resultado"] == "enviada" else VERMELHO)]
            if e["modo"] == "teste":
                selos.append(("TESTE", AMBAR))
            selos.append((e["canal"].replace("WhatsApp ", "").upper(), SUAVE))
            for texto, cor in reversed(selos):
                ctk.CTkLabel(topo, text=texto, font=fonte(11, True), text_color=cor).pack(side="right", padx=4)
            detalhe = f"{e['etapa']} · para {e['destino'] or 'sem número'}"
            if e.get("motivo"):
                detalhe += f" · {e['motivo']}"
            ctk.CTkLabel(cartao, text=detalhe, font=fonte(12), text_color=SUAVE, anchor="w").pack(
                fill="x", padx=16)
            ctk.CTkLabel(cartao, text=e["texto"], font=fonte(12), wraplength=820, justify="left", anchor="w").pack(
                fill="x", padx=16, pady=(2, 10))

    def mostrar_mensagens(self, mensagens):
        self._mensagens = mensagens
        if self.visao.get() == "Histórico de envios":  # a lista do dia atualiza por trás; recarrega o histórico
            self.mostrar_historico()
            return
        for filho in self.lista.winfo_children():
            filho.destroy()
        if not mensagens:
            vazio = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA)
            vazio.pack(fill="x", padx=8, pady=6)
            ctk.CTkLabel(vazio, text="Nenhuma mensagem para hoje", font=fonte(15, True)).pack(
                anchor="w", padx=18, pady=(14, 2))
            ctk.CTkLabel(vazio, text="Quando uma OC estiver a 14 ou 7 dias úteis do embarque, ou um card da "
                                     "Logística a 2 dias úteis da data máxima de embarque, ou atrasados, "
                                     "a mensagem aparece aqui pronta para enviar.",
                         font=fonte(13), text_color=SUAVE, wraplength=820, justify="left").pack(
                anchor="w", padx=18, pady=(0, 14))
            return
        for mensagem in mensagens:
            self._cartao(mensagem)

    def _cartao(self, m):
        cor = {"14": SUAVE, "7": AMBAR, "2": AMBAR, "hoje": DESTAQUE, "atraso": VERMELHO}[m["etapa"]]
        cartao = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA)
        cartao.pack(fill="x", padx=8, pady=6)
        topo = ctk.CTkFrame(cartao, fg_color="transparent")
        topo.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkLabel(topo, text=m["fornecedor_nome"], font=fonte(15, True)).pack(side="left")
        ctk.CTkLabel(topo, text=f"  {m['rotulo']}", font=fonte(13, True), text_color=cor).pack(side="left")
        ctk.CTkLabel(topo, text=_sobre_mensagem(m), font=fonte(13), text_color=SUAVE).pack(side="right")
        ctk.CTkLabel(cartao, text=m["texto"], font=fonte(13), wraplength=820, justify="left", anchor="w").pack(
            fill="x", padx=18, pady=(2, 8))
        botoes = ctk.CTkFrame(cartao, fg_color="transparent")
        botoes.pack(fill="x", padx=18, pady=(0, 14))
        if m["whatsapp"]:
            ctk.CTkButton(botoes, text="Abrir no WhatsApp", height=36, font=fonte(13, True),
                          command=lambda: webbrowser.open(fi.link_whatsapp(m))).pack(side="left")
        else:
            ctk.CTkLabel(botoes, text=("Sem WhatsApp: informe o número em whatsapp_logistica no config.json."
                                       if m.get("tipo") == "logistica" else
                                       "Sem WhatsApp: cadastre o celular no contato do fornecedor no Bling."),
                         font=fonte(12), text_color=AMBAR).pack(side="left")
        if m.get("link"):
            ctk.CTkButton(botoes, text="Abrir card", height=36, width=110, font=fonte(13), fg_color="transparent",
                          border_width=1, border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                          command=lambda: webbrowser.open(m["link"])).pack(side="left", padx=(8, 0))
        ctk.CTkButton(botoes, text="Copiar texto", height=36, width=120, font=fonte(13), fg_color="transparent",
                      border_width=1, border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                      command=lambda: self.app.copiar(m["texto"])).pack(side="left", padx=8)
        ctk.CTkButton(botoes, text="Marcar como enviada", height=36, width=170, font=fonte(13), fg_color=VERDE,
                      hover_color=("#17643F", "#3AA874"),
                      command=lambda: self._enviada(m, cartao)).pack(side="right")

    def _enviada(self, mensagem, cartao):
        fi.registrar_mensagem_enviada(mensagem)
        fi.registrar_historico(mensagem, "WhatsApp manual", "real", mensagem.get("whatsapp"), "enviada",
                               "confirmado pela equipe")
        cartao.destroy()
        self.app.mensagens = [x for x in self.app.mensagens if x is not mensagem]
        self.app.atualizar_contagem_mensagens()
        if not self.app.mensagens:
            self.mostrar_mensagens([])


class JanelaCardsDemo(ctk.CTkToplevel):
    """Demonstração: mostra os cards que o pedido "criou" no Trello simulado, como ficariam no quadro:
    lista, título, data, checklist de separação e a ficha anexada (clique na ficha para abrir em tamanho real)."""

    LARGURA_FICHA = 470

    def __init__(self, master, cards):
        super().__init__(master)
        self.title("Cards criados no Trello (demonstração)")
        self.geometry("1080x820")
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))  # aparece na frente, depois se comporta normal
        self._imagens = []  # mantém as imagens vivas enquanto a janela estiver aberta
        ctk.CTkLabel(self, text="Cards criados no Trello", font=fonte(20, True), anchor="w").pack(
            fill="x", padx=24, pady=(18, 0))
        ctk.CTkLabel(self, text="Simulação: é assim que os cards aparecem no quadro. Nada foi enviado ao Trello.",
                     font=fonte(13), text_color=SUAVE, anchor="w").pack(fill="x", padx=24, pady=(2, 10))
        area = ctk.CTkScrollableFrame(self, fg_color="transparent", orientation="horizontal" if len(cards) > 2 else "vertical")
        area.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        if not cards:
            ctk.CTkLabel(area, text="Nenhum card criado ainda: processe um pedido (ex.: 1002).", font=fonte(14)).pack(
                anchor="w", padx=8, pady=8)
            return
        for coluna, card in enumerate(cards):
            self._card(area, card).grid(row=0, column=coluna, sticky="n", padx=8, pady=4)

    def _card(self, master, card):
        import demo
        caixa = ctk.CTkFrame(master, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA,
                             width=self.LARGURA_FICHA + 40)
        ctk.CTkLabel(caixa, text=f"Lista: {card['lista']}", font=fonte(12, True), text_color=DESTAQUE, anchor="w").pack(
            fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(caixa, text=card["nome"], font=fonte(15, True), wraplength=self.LARGURA_FICHA, justify="left",
                     anchor="w").pack(fill="x", padx=18)
        if card.get("prazo"):
            dia = datetime.strptime(card["prazo"], "%Y-%m-%d").strftime("%d/%m/%Y")
            ctk.CTkLabel(caixa, text=f"📅  Data de entrega: {dia}", font=fonte(13), anchor="w").pack(
                fill="x", padx=18, pady=(6, 0))
        for checklist in card.get("checklists") or []:
            itens = checklist.get("checkItems") or []
            ctk.CTkLabel(caixa, text=f"☑  Checklist de separação (0/{len(itens)})", font=fonte(13, True),
                         anchor="w").pack(fill="x", padx=18, pady=(10, 2))
            for item in itens:
                ctk.CTkLabel(caixa, text=f"☐  {item['name']}", font=fonte(12), wraplength=self.LARGURA_FICHA,
                             justify="left", anchor="w").pack(fill="x", padx=26)
        for nome, conteudo in (card.get("imagens") or {}).items():
            ctk.CTkLabel(caixa, text=f"📎  {nome}", font=fonte(13, True), anchor="w").pack(fill="x", padx=18, pady=(12, 4))
            try:
                from io import BytesIO
                from PIL import Image
                imagem = Image.open(BytesIO(conteudo))
                altura = int(imagem.height * self.LARGURA_FICHA / imagem.width)
                foto = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(self.LARGURA_FICHA, altura))
                self._imagens.append(foto)
                caminho = os.path.join(demo.PASTA_DEMO, "fichas", nome)
                botao = ctk.CTkButton(caixa, image=foto, text="", fg_color="transparent", hover_color=CARTAO_HOVER,
                                      command=lambda c=caminho: os.startfile(c) if os.path.isfile(c) else None)
                botao.pack(padx=12, pady=(0, 14))
            except Exception as erro:
                ctk.CTkLabel(caixa, text=f"(não consegui mostrar a ficha: {erro})", font=fonte(12),
                             text_color=AMBAR).pack(fill="x", padx=18, pady=(0, 14))
        return caixa


class TelaCompras(ctk.CTkFrame):
    """Mostra só a pergunta da vez + o que o fluxo informou logo antes dela (produto em revisão,
    resumo da OC, avisos). O registro completo fica escondido atrás de um botão."""

    LINHAS_CONTEXTO = 12

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.rodando = False
        self.aguardando = None
        self.buffer = []  # o que o fluxo escreveu desde a última pergunta
        titulo_tela(self, "Realizar compras", "Pedido da Tray → OCs no Bling → Trello, uma pergunta por vez.")

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=36, pady=(0, 12))
        self.botao_iniciar = ctk.CTkButton(barra, text="▶  Processar um pedido", height=40, width=210,
                                           font=fonte(14, True), command=self.iniciar)
        self.botao_iniciar.pack(side="left")
        self.botao_registro = ctk.CTkButton(barra, text="Ver registro completo", height=40, width=180,
                                            font=fonte(13), fg_color="transparent", border_width=1,
                                            border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                            command=self.alternar_registro)
        self.botao_registro.pack(side="left", padx=10)
        if fi.MODO_DEMO:  # na demonstração, dá para ver como os cards ficaram no Trello simulado
            ctk.CTkButton(barra, text="🗂  Ver cards criados", height=40, width=180, font=fonte(13),
                          fg_color="transparent", border_width=1, border_color=DESTAQUE, text_color=DESTAQUE,
                          hover_color=CARTAO_HOVER, command=self.ver_cards_demo).pack(side="left")

        # --- cartão da pergunta atual ---
        self.cartao = ctk.CTkFrame(self, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        self.cartao.pack(fill="x", padx=36, pady=(0, 24))
        self.contexto = ctk.CTkTextbox(self.cartao, font=fonte(13), wrap="word", fg_color=LATERAL,
                                       corner_radius=10, border_width=0)
        for tag, cor in (("ok", "#2E9E6B"), ("alerta", "#C98A1B"), ("erro", "#D9534F")):
            self.contexto.tag_config(tag, foreground=cor)
        self.contexto.configure(state="disabled")
        self.pergunta = ctk.CTkLabel(self.cartao, text="", font=fonte(18, True), anchor="w", wraplength=880,
                                     justify="left")
        self.pergunta.pack(fill="x", padx=20, pady=(18, 12))

        # Pergunta de texto livre (número do pedido, datas, valores...)
        self.linha_texto = ctk.CTkFrame(self.cartao, fg_color="transparent")
        self.entrada = ctk.CTkEntry(self.linha_texto, height=42, font=fonte(14), placeholder_text="Digite a resposta...")
        self.entrada.pack(side="left", fill="x", expand=True)
        self.entrada.bind("<Return>", lambda e: self.responder(self.entrada.get()))
        ctk.CTkButton(self.linha_texto, text="Enviar", width=100, height=42, font=fonte(13, True),
                      command=lambda: self.responder(self.entrada.get())).pack(side="left", padx=(8, 0))
        self.botao_padrao = ctk.CTkButton(self.linha_texto, text="", height=42, font=fonte(13),
                                          fg_color="transparent", border_width=1, border_color=DESTAQUE,
                                          text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                          command=lambda: self.responder(""))

        # Pergunta com opções fixas: um botão por opção
        self.linha_opcoes = ctk.CTkFrame(self.cartao, fg_color="transparent")

        # --- registro completo (escondido) ---
        self.console = ctk.CTkTextbox(self, font=fonte(12, familia="Consolas"), wrap="word", corner_radius=14,
                                      border_width=1, border_color=BORDA, fg_color=CARTAO)
        for tag, cor in (("resposta", "#2E9E6B"), ("alerta", "#C98A1B"), ("erro", "#D9534F")):
            self.console.tag_config(tag, foreground=cor)
        self.console.configure(state="disabled")
        self.registro_visivel = False

        # --- pedidos da Tray esperando compra (cards) ---
        self.painel = ctk.CTkFrame(self, fg_color="transparent")
        topo = ctk.CTkFrame(self.painel, fg_color="transparent")
        topo.pack(fill="x")
        self.titulo_pedidos = ctk.CTkLabel(topo, text="Pedidos na Tray para comprar", font=fonte(15, True), anchor="w")
        self.titulo_pedidos.pack(side="left")
        self.botao_atualizar = ctk.CTkButton(topo, text="↻  Atualizar", width=120, height=32, font=fonte(12),
                                             fg_color="transparent", border_width=1, border_color=DESTAQUE,
                                             text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                             command=lambda: self.carregar_pedidos(forcar=True))
        self.botao_atualizar.pack(side="right")
        self.lista_pedidos = ctk.CTkScrollableFrame(self.painel, fg_color="transparent")
        self.lista_pedidos.pack(fill="both", expand=True, pady=(8, 0))
        for coluna in range(3):
            self.lista_pedidos.grid_columnconfigure(coluna, weight=1, uniform="cards")
        self.painel.pack(fill="both", expand=True, padx=36, pady=(0, 24))
        self._carregado_em = 0
        self._carregando = False

        self.ocioso("Escolha um pedido abaixo ou clique em “Processar um pedido” para digitar o número.")

    # ----- estados -----

    def ao_mostrar(self):
        if self.aguardando == "texto":
            self.entrada.focus_set()
        if not self.rodando:
            self.carregar_pedidos()

    # ----- pedidos da Tray (cards) -----

    def carregar_pedidos(self, forcar=False):
        """Busca na Tray (em segundo plano, só leitura) os pedidos nos status de compra."""
        if self.rodando or self._carregando or (not forcar and time.time() - self._carregado_em < 60):
            return
        self._carregando = True
        self.titulo_pedidos.configure(text="Buscando pedidos na Tray...")
        self.botao_atualizar.configure(state="disabled")

        def terminou(pedidos, erro):
            self._carregando = False
            self.botao_atualizar.configure(state="normal")
            if erro:
                self.titulo_pedidos.configure(text="Não consegui buscar os pedidos na Tray (veja o registro completo).")
                return
            self._carregado_em = time.time()
            self.mostrar_pedidos(pedidos)

        self.app.em_segundo_plano(fi.pedidos_para_comprar, terminou)

    def mostrar_pedidos(self, pedidos):
        for filho in self.lista_pedidos.winfo_children():
            filho.destroy()
        self.titulo_pedidos.configure(text=f"Pedidos na Tray para comprar ({len(pedidos)})")
        if not pedidos:
            ctk.CTkLabel(self.lista_pedidos, text="Nenhum pedido nos status de compra da Tray (config: compras.status_tray).",
                         font=fonte(13), text_color=SUAVE).grid(row=0, column=0, columnspan=3, sticky="w", pady=8)
            return
        for i, pedido in enumerate(pedidos):
            self._card_pedido(pedido).grid(row=i // 3, column=i % 3, sticky="nsew", padx=6, pady=6)

    ALTURA_CARD = 300
    ITENS_NO_CARD = 4
    LETRAS_POR_ITEM = 46

    def _card_pedido(self, p):
        """Card de tamanho fixo: até 4 produtos (um por linha) e '+ N item(ns)' para o resto.
        Borda vermelha: mais de 1 dia útil esperando a compra. Borda âmbar: já tem OC/card (risco de duplicar)."""
        def data_br(texto):
            texto = str(texto or "")[:10]
            return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) == 10 and not texto.startswith("0000") else "—"

        def linha(texto):
            texto = f"• {texto}"
            return texto if len(texto) <= self.LETRAS_POR_ITEM else texto[:self.LETRAS_POR_ITEM - 1].rstrip() + "…"

        duplicar = p.get("ja_tem_oc") or p.get("ja_tem_card")
        dias = int(p.get("dias_esperando") or 0)
        atrasado = dias > 1
        borda = VERMELHO if atrasado else AMBAR if duplicar else BORDA
        card = ctk.CTkFrame(self.lista_pedidos, fg_color=CARTAO, corner_radius=14, border_width=2 if atrasado else 1,
                            border_color=borda, height=self.ALTURA_CARD)
        card.pack_propagate(False)  # todos do mesmo tamanho, qualquer que seja a quantidade de itens
        ctk.CTkLabel(card, text=f"Pedido {p['numero']}", font=fonte(15, True), anchor="w").pack(
            fill="x", padx=14, pady=(12, 0))
        try:
            total = fi.formatar_reais(float(p.get("total") or 0))
        except (TypeError, ValueError):
            total = ""
        ctk.CTkLabel(card, text=f"{p.get('status') or ''} · {data_br(p.get('data'))} · {total}", font=fonte(12),
                     text_color=SUAVE, anchor="w").pack(fill="x", padx=14)
        itens = p.get("itens") or []
        linhas = [linha(i) for i in itens[:self.ITENS_NO_CARD]] or ["(itens não lidos)"]
        if len(itens) > self.ITENS_NO_CARD:
            linhas.append(f"+ {len(itens) - self.ITENS_NO_CARD} item(ns)")
        linhas += [""] * (self.ITENS_NO_CARD + 1 - len(linhas))  # mesmo espaço em todos os cards
        ctk.CTkLabel(card, text="\n".join(linhas), font=fonte(12), anchor="nw", justify="left").pack(
            fill="x", padx=14, pady=(6, 0))
        ctk.CTkLabel(card, text=f"Entrega prevista (Tray): {data_br(p.get('entrega'))}", font=fonte(12),
                     text_color=SUAVE, anchor="w").pack(fill="x", padx=14, pady=(4, 0))
        avisos = []
        if atrasado:
            avisos.append((f"⚠ Há {dias} dias úteis aguardando compra", VERMELHO))
        textos = [t for t, ok in (("Já tem OC anotada na Tray", p.get("ja_tem_oc")),
                                  ("Já tem card no Trello", p.get("ja_tem_card"))) if ok]
        if textos:
            avisos.append(("⚠ " + " · ".join(textos), AMBAR))
        for texto, cor in avisos:
            ctk.CTkLabel(card, text=texto, font=fonte(12, True), text_color=cor, anchor="w").pack(fill="x", padx=14)
        estilo = ({"fg_color": "transparent", "border_width": 1, "border_color": AMBAR, "text_color": AMBAR,
                   "hover_color": CARTAO_HOVER} if duplicar else {})
        ctk.CTkButton(card, text="Processar mesmo assim" if duplicar else "Processar", height=36, font=fonte(13, True),
                      command=lambda n=p["numero"]: self.iniciar(n), **estilo).pack(side="bottom", fill="x",
                                                                                    padx=14, pady=12)
        return card

    def ocioso(self, texto):
        self.aguardando = None
        self.linha_texto.pack_forget()
        self._limpar_opcoes()
        self.pergunta.configure(text=texto)

    def _limpar_opcoes(self):
        for botao in self.linha_opcoes.winfo_children():
            botao.destroy()
        self.linha_opcoes.pack_forget()

    def alternar_registro(self):
        self.registro_visivel = not self.registro_visivel
        if self.registro_visivel:
            self.cartao.pack_configure(pady=(0, 12))
            self.console.pack(fill="both", expand=True, padx=36, pady=(0, 24))
            self.console.see("end")
            self.botao_registro.configure(text="Ocultar registro")
        else:
            self.console.pack_forget()
            self.cartao.pack_configure(pady=(0, 24))
            self.botao_registro.configure(text="Ver registro completo")

    # ----- texto -----

    @staticmethod
    def rotulo_padrao(pergunta):
        """Texto do botão de 'Enter' quando a pergunta tem um valor padrão (ou None)."""
        achado = re.search(r"\[Enter = (.*?)\]", pergunta)
        if achado:
            valor = achado.group(1).strip()
            return f"Usar: {valor[:40]}{'…' if len(valor) > 40 else ''}"
        texto = fi.sem_acento(pergunta)
        for trecho, rotulo in (("enter para pular", "Pular"), ("enter cancela", "Cancelar"),
                               ("enter para cancelar", "Cancelar"), ("enter para usar so o padrao", "Usar só o padrão"),
                               ("enter para preencher tudo", "Preencher à mão")):
            if trecho in texto:
                return rotulo
        return None

    @staticmethod
    def tag_da_linha(linha):
        if "ERRO" in linha:
            return "erro"
        if "ATENÇÃO" in linha or "AVISO" in linha:
            return "alerta"
        if any(t in linha for t in ("OC criada", "Card criado", "Pedido mudado", "- OK.", "✓")):
            return "ok"
        return None

    def escrever(self, texto, tag=None, contexto=True):
        """Tudo vai para o registro completo; o que o fluxo escreve também vai para o contexto da próxima pergunta."""
        if tag is None:
            tag = self.tag_da_linha(texto)
            tag = None if tag == "ok" else tag  # o registro completo só destaca alertas e erros
        self.console.configure(state="normal")
        self.console.insert("end", texto, tag)
        self.console.see("end")
        self.console.configure(state="disabled")
        if contexto and self.rodando:
            self.buffer.append(texto)

    def _mostrar_contexto(self, pergunta=""):
        """Mostra no cartão as linhas que o fluxo escreveu desde a última pergunta (sem a pergunta em si)."""
        texto = "".join(self.buffer)
        self.buffer = []
        if pergunta:
            posicao = texto.rfind(pergunta)
            if posicao >= 0:
                texto = texto[:posicao]
        linhas = []
        for linha in (l.rstrip() for l in texto.splitlines()):
            if linha.strip() or (linhas and linhas[-1].strip()):
                linhas.append(linha)
        while linhas and not linhas[-1].strip():
            linhas.pop()

        self.contexto.configure(state="normal")
        self.contexto.delete("1.0", "end")
        for i, linha in enumerate(linhas):
            if i:
                self.contexto.insert("end", "\n")  # sem quebra no fim: senão sobra uma linha vazia visível
            self.contexto.insert("end", linha.strip() if linha.startswith("    ") else linha, self.tag_da_linha(linha))
        self.contexto.configure(state="disabled")
        if linhas:
            self.contexto.pack(fill="x", padx=18, pady=(16, 0), before=self.pergunta)
            self._ajustar_altura_contexto(len(linhas))
        else:
            self.contexto.pack_forget()

    def _ajustar_altura_contexto(self, linhas_logicas):
        """Deixa a caixa do tamanho do texto (contando as linhas que quebram), até o limite,
        e mostra o começo do texto."""
        import tkinter.font as tkfont
        caixa = self.contexto._textbox
        visuais = linhas_logicas
        try:
            self.update_idletasks()
            visuais = max(int(caixa.count("1.0", "end", "displaylines")[0]), linhas_logicas, 1)
            altura_linha = tkfont.Font(font=caixa.cget("font")).metrics("linespace")
            escala = self.contexto._get_widget_scaling()
            linhas = min(visuais, self.LINHAS_CONTEXTO)
            altura = int((linhas * altura_linha) / escala) + 20
            maxima = int((self.LINHAS_CONTEXTO * altura_linha) / escala) + 20
            self.contexto.configure(height=altura)
            # Ajuste fino: cresce até o texto caber inteiro (ou até o limite)
            for _ in range(8):
                self.update_idletasks()
                caixa.yview_moveto(0)
                if caixa.yview()[1] >= 1.0 or altura >= maxima:
                    break
                altura = min(altura + int(altura_linha / escala / 2) + 2, maxima)
                self.contexto.configure(height=altura)
        except Exception:
            self.contexto.configure(height=min(linhas_logicas + 1, self.LINHAS_CONTEXTO) * 24 + 20)
        # Cabe tudo: mostra do começo. Texto muito longo: mostra o fim (o mais recente, logo antes da pergunta).
        self.contexto.see("1.0" if visuais <= self.LINHAS_CONTEXTO else "end")

    # ----- fluxo -----

    def iniciar(self, numero=None):
        """numero: pedido escolhido num card; sem ele, o fluxo pergunta o número."""
        if self.rodando:
            return
        self.rodando = True
        self.buffer = []
        self._mostrar_contexto()
        self.painel.pack_forget()
        self.botao_iniciar.configure(state="disabled", text="Pedido em andamento...")
        self.pergunta.configure(text="Carregando...")
        if self.console.get("1.0", "end").strip():
            self.escrever("\n", contexto=False)
        if fi.MODO_DEMO:
            import demo
            cards_antes = len(demo.CARDS)

        def fluxo():
            try:
                fi.processar_pedido(numero)
                if fi.MODO_DEMO:
                    import demo
                    print("\n[demonstração] O que foi 'criado' até agora (só na memória):\n" + demo.resumo())
            except Exception as erro:
                print(f"\n=== ERRO ===\n{erro}")

        def terminou(_, __):
            self._mostrar_contexto()
            self.rodando = False
            self.botao_iniciar.configure(state="normal", text="▶  Processar outro pedido")
            self.ocioso("Pedido finalizado. Escolha o próximo pedido abaixo ou clique em “Processar outro pedido”.")
            self.escrever("\n——— fim do pedido ———\n", "resposta", contexto=False)
            self.painel.pack(fill="both", expand=True, padx=36, pady=(0, 24), after=self.cartao)
            self.carregar_pedidos(forcar=True)  # o pedido processado muda de status e sai da lista
            if fi.MODO_DEMO and len(demo.CARDS) > cards_antes:  # demonstração: já mostra os cards criados
                self.ver_cards_demo(demo.CARDS[cards_antes:])

        self.app.em_segundo_plano(fluxo, terminou)

    def ver_cards_demo(self, cards=None):
        """Demonstração: janela com os cards criados (sem argumento: todos os desta sessão)."""
        import demo
        JanelaCardsDemo(self, demo.CARDS[demo._INICIAIS:] if cards is None else cards)

    def perguntar(self, pergunta):
        """Pergunta de texto livre: campo + Enviar (+ botão do valor padrão, se houver)."""
        self._mostrar_contexto(pergunta)
        self._limpar_opcoes()
        linhas = pergunta.strip().splitlines()
        titulo = re.sub(r"\s*\[Enter = .*?\]", "", linhas[-1].strip()) if linhas else "Continuar"
        self.pergunta.configure(text=titulo)
        rotulo = self.rotulo_padrao(pergunta)
        if rotulo:
            self.botao_padrao.configure(text=rotulo)
            self.botao_padrao.pack(side="left", padx=(8, 0))
        else:
            self.botao_padrao.configure(text="")
            self.botao_padrao.pack_forget()
        self.linha_texto.pack(fill="x", padx=20, pady=(0, 18))
        self.entrada.configure(state="normal")
        self.entrada.delete(0, "end")
        self.entrada.focus_set()
        self.aguardando = "texto"

    def perguntar_opcoes(self, pergunta, opcoes):
        """Pergunta com opções fixas: um botão para cada uma."""
        self._mostrar_contexto(pergunta)
        self.linha_texto.pack_forget()
        self._limpar_opcoes()
        self.pergunta.configure(text=pergunta.strip())
        colunas = min(len(opcoes), 3) or 1
        for coluna in range(6):
            self.linha_opcoes.grid_columnconfigure(coluna, weight=1 if coluna < colunas else 0,
                                                   uniform="opcoes" if coluna < colunas else "")
        for i, (chave, rotulo) in enumerate(opcoes):
            nome = fi.sem_acento(rotulo)
            if nome in ("sim",):
                estilo = {"fg_color": VERDE, "hover_color": ("#17643F", "#3AA874")}
            elif nome in ("nao", "cancelar", "nenhum destes"):
                estilo = {"fg_color": ("#6B7280", "#4B5563"), "hover_color": ("#555C68", "#3F4753")}
            else:
                estilo = {}
            ctk.CTkButton(self.linha_opcoes, text=rotulo, height=46, font=fonte(14, True),
                          command=lambda c=chave, r=rotulo: self.escolher(c, r), **estilo).grid(
                row=i // colunas, column=i % colunas, sticky="ew", padx=4, pady=4)
        self.linha_opcoes.pack(fill="x", padx=16, pady=(0, 16))
        self.aguardando = "opcoes"

    def escolher(self, chave, rotulo):
        if self.aguardando != "opcoes":
            return
        self.aguardando = None
        self._limpar_opcoes()
        self.pergunta.configure(text="Processando...")
        self.escrever(f"→ {rotulo}\n", "resposta", contexto=False)
        self.app.ponte.respostas.put(chave)

    def responder(self, texto):
        if self.aguardando != "texto":
            return
        self.aguardando = None
        self.linha_texto.pack_forget()
        self.pergunta.configure(text="Processando...")
        self.escrever((texto or f"↵ {self.botao_padrao.cget('text') or 'Enter'}") + "\n", "resposta",
                      contexto=False)
        self.entrada.delete(0, "end")
        self.app.ponte.respostas.put(texto)


# ---------------------------------------------------------------------------
# JANELA PRINCIPAL
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    NAVEGACAO = [
        ("inicio", "🏠   Início"),
        ("calculadora", "🧮   Calculadora"),
        ("compras", "🛒   Compras"),
        ("mensagens", "💬   Mensagens"),
        ("html", "📝   Descrição HTML"),
    ]

    def __init__(self):
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        aplicar_tema_laranja()
        super().__init__()
        self.title(TITULO)
        self.geometry("1200x780")
        self.minsize(1040, 680)
        try:
            self.iconbitmap(recurso("icone.ico"))
        except Exception:
            pass

        self.ponte = Ponte()
        self.terminados = queue.Queue()  # tarefas em segundo plano que terminaram
        sys.stdout = sys.stderr = self.ponte
        builtins.input = self.ponte.input
        fi._escolha_externa = self.ponte.escolher

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)  # linha 0: faixa da demonstração (vazia no uso normal)
        self._montar_lateral()
        if fi.MODO_DEMO:
            faixa = ctk.CTkFrame(self, fg_color=CARTAO_HOVER, corner_radius=0)
            faixa.grid(row=0, column=1, sticky="ew")
            ctk.CTkLabel(faixa, text="MODO DEMONSTRAÇÃO  ·  loja, produtos e pedidos fictícios  ·  nada é enviado ao "
                                     "Bling, Trello, Tray ou WhatsApp  ·  pedidos de exemplo: 1001, 1002 e 1003",
                         font=fonte(13, True), text_color=DESTAQUE).pack(anchor="w", padx=24, pady=9)
        self.area = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.area.grid(row=1, column=1, sticky="nsew")
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(0, weight=1)
        self.telas = {
            "inicio": TelaInicio(self.area, self),
            "calculadora": TelaCalculadora(self.area, self),
            "compras": TelaCompras(self.area, self),
            "mensagens": TelaMensagens(self.area, self),
            "html": TelaHTML(self.area, self),
        }
        self.mensagens = []
        self.aviso_mensagens_dado = None  # dia em que o aviso / envio automático já aconteceu
        self.enviando_whatsapp = False
        self.atual = None
        self.mostrar("inicio")
        self.after(80, self._receber)
        self.atualizando_checklists = False
        self.after(5000, self._checklists_automatico)

    INTERVALO_CHECKLISTS_MS = 60 * 60 * 1000  # de hora em hora, enquanto o Assistente estiver aberto

    def _checklists_automatico(self):
        # Sempre roda: mede a lista A Separar mesmo sem cards com OC em acompanhamento
        # (sem acompanhamento, a parte do Bling nem é chamada).
        self.atualizar_checklists(automatico=True)
        self.after(self.INTERVALO_CHECKLISTS_MS, self._checklists_automatico)

    def atualizar_checklists(self, automatico=False):
        """Confere as OCs no Bling, atualiza o texto das checklists no Trello e monta as mensagens do dia
        aos fornecedores (tudo em segundo plano)."""
        if self.atualizando_checklists:
            return
        self.atualizando_checklists = True
        inicio, tela_msg = self.telas["inicio"], self.telas["mensagens"]
        inicio.botao_checklists.configure(text="Atualizando...")
        inicio.status_checklists.configure(text="Conferindo as OCs no Bling...", text_color=SUAVE)
        tela_msg.status.configure(text="Conferindo as OCs no Bling...", text_color=SUAVE)

        def conferir():
            try:
                a_separar = fi.resumo_a_separar(fi.organizar_a_separar(aplicar=True))
            except Exception as erro:
                a_separar = f"A Separar: não consegui medir agora ({erro})."
            resumo, mensagens = fi.atualizar_checklists(), fi.mensagens_do_dia()
            try:
                mensagens += fi.mensagens_logistica()
            except Exception as erro:
                a_separar += f" | Lembretes da Logística: não consegui montar agora ({erro})."
            return resumo, mensagens, a_separar

        def terminou(resultado, erro):
            self.atualizando_checklists = False
            inicio.botao_checklists.configure(text="Atualizar agora")
            agora = datetime.now().strftime("%H:%M")
            if erro:
                inicio.status_checklists.configure(text=f"Não consegui atualizar às {agora}: {erro}",
                                                   text_color=AMBAR)
                tela_msg.status.configure(text=f"Não consegui atualizar às {agora}.", text_color=AMBAR)
                return
            resumo, self.mensagens, a_separar = resultado
            inicio.status_checklists.configure(text=f"{resumo} (às {agora})", text_color=SUAVE)
            inicio.status_a_separar.configure(text=f"{a_separar} (às {agora})",
                                              text_color=AMBAR if "parados há" in a_separar and " 0 parados" not in a_separar else SUAVE)
            tela_msg.status.configure(text=f"Atualizado às {agora}", text_color=SUAVE)
            tela_msg.mostrar_mensagens(self.mensagens)
            self.atualizar_contagem_mensagens()
            if automatico and self.mensagens and self.aviso_mensagens_dado != date.today():
                modo = self._modo_envio()
                if modo != "esperar":  # antes do horário: a conferência da próxima hora tenta de novo
                    self.aviso_mensagens_dado = date.today()
                    if modo == "automatico":
                        self.enviar_whatsapp(automatico=True)
                    else:
                        self.avisar_mensagens(len(self.mensagens))

        self.em_segundo_plano(conferir, terminou)

    @staticmethod
    def _modo_envio():
        """'automatico' (manda sozinho agora), 'esperar' (ligado, mas ainda não deu o horário) ou 'manual'."""
        try:
            import WHATSAPP
            c = WHATSAPP.cfg()
        except Exception:
            return "manual"
        if not c["envio_automatico"]:
            return "manual"
        agora = datetime.now()
        inicio = datetime.strptime(c["horario"], "%H:%M").time()
        if agora.weekday() < 5 and agora.time() < inicio:
            return "esperar"
        return "automatico" if WHATSAPP.em_horario_comercial(agora) else "manual"

    def enviar_whatsapp(self, automatico=False):
        """Manda as mensagens do dia pelo WhatsApp Web do Assistente (em segundo plano)."""
        tela = self.telas["mensagens"]
        if self.enviando_whatsapp:
            return
        pendentes = list(self.mensagens)
        if not pendentes:
            tela.status.configure(text="Nenhuma mensagem para enviar.", text_color=SUAVE)
            return
        self.enviando_whatsapp = True
        tela.botao_enviar.configure(text="Enviando...")
        tela.status.configure(text=f"Enviando {len(pendentes)} pelo WhatsApp (o navegador do Assistente vai abrir)...",
                              text_color=SUAVE)

        def trabalho():
            import WHATSAPP
            return WHATSAPP.enviar_lote(pendentes, ao_enviar=fi.registrar_mensagem_enviada), WHATSAPP.cfg()["modo_teste"]

        def terminou(resultado, erro):
            self.enviando_whatsapp = False
            tela.botao_enviar.configure(text="Enviar pelo WhatsApp agora")
            agora = datetime.now().strftime("%H:%M")
            if erro:
                tela.status.configure(text=f"O envio falhou às {agora}: {erro}", text_color=AMBAR)
                if automatico:
                    self.avisar_mensagens(len(self.mensagens))
                return
            (enviadas, falhas), teste = resultado
            if not teste:  # no modo teste nada é dado como enviado ao fornecedor
                self.mensagens = [m for m in self.mensagens if all(m is not e for e in enviadas)]
                self.atualizar_contagem_mensagens()
            tela.mostrar_mensagens(self.mensagens)  # (se o histórico estiver aberto, ele é recarregado)
            texto = f"{len(enviadas)} {'enviada' if len(enviadas) == 1 else 'enviadas'}{' (teste)' if teste else ''} às {agora}"
            if falhas:
                texto += f" · {len(falhas)} não {'foi' if len(falhas) == 1 else 'foram'}: {falhas[0][1]}"
            tela.status.configure(text=texto, text_color=AMBAR if falhas else VERDE)
            if automatico and falhas:
                self.avisar_mensagens(len(self.mensagens))

        self.em_segundo_plano(trabalho, terminou)

    def conectar_whatsapp(self):
        """Abre o WhatsApp Web do Assistente para ler o QR code (uma vez; a sessão fica salva)."""
        tela = self.telas["mensagens"]
        if self.enviando_whatsapp:
            return
        self.enviando_whatsapp = True
        tela.status.configure(text="Abrindo o WhatsApp Web: leia o QR code com o celular do número de compras "
                                   "(até 3 minutos)...", text_color=SUAVE)

        def trabalho():
            import WHATSAPP
            return WHATSAPP.conectar(180)

        def terminou(conectado, erro):
            self.enviando_whatsapp = False
            if erro:
                tela.status.configure(text=f"WhatsApp não conectado: {erro}", text_color=AMBAR)
            elif not conectado:
                tela.status.configure(text="WhatsApp não conectado. Tente de novo e leia o QR code a tempo.",
                                      text_color=AMBAR)
            else:
                tela.status.configure(text="WhatsApp conectado. A sessão ficou salva neste computador.",
                                      text_color=VERDE)

        self.em_segundo_plano(trabalho, terminou)

    def atualizar_contagem_mensagens(self):
        quantidade = len(self.mensagens)
        self.botoes_nav["mensagens"].configure(
            text=f"💬   Mensagens ({quantidade})" if quantidade else "💬   Mensagens")

    MAX_NO_AVISO = 6

    def avisar_mensagens(self, quantidade):
        """Pop-up: pedidos chegando na data ou atrasados, com 'Enviar no WhatsApp' em cada um.
        O botão abre a conversa com o texto pronto; depois de enviar, 'Já enviei' tira da lista."""
        aviso = ctk.CTkToplevel(self)
        aviso.title(TITULO)
        aviso.resizable(False, False)
        aviso.attributes("-topmost", True)
        texto = "1 mensagem" if quantidade == 1 else f"{quantidade} mensagens"
        ctk.CTkLabel(aviso, text=f"Hoje há {texto} para fornecedores e Logística", font=fonte(16, True)).pack(
            padx=24, pady=(20, 2), anchor="w")
        ctk.CTkLabel(aviso, text="Clique em “Enviar no WhatsApp”, envie e depois confirme em “Já enviei”.",
                     font=fonte(12), text_color=SUAVE).pack(padx=24, anchor="w")
        lista = ctk.CTkFrame(aviso, fg_color="transparent")
        lista.pack(fill="x", padx=18, pady=(10, 0))
        cores = {"14": SUAVE, "7": AMBAR, "2": AMBAR, "hoje": DESTAQUE, "atraso": VERMELHO}

        for m in self.mensagens[:self.MAX_NO_AVISO]:
            linha = ctk.CTkFrame(lista, fg_color=CARTAO, corner_radius=10, border_width=1, border_color=BORDA)
            linha.pack(fill="x", pady=3)
            textos = ctk.CTkFrame(linha, fg_color="transparent")
            textos.pack(side="left", padx=12, pady=8)
            ctk.CTkLabel(textos, text=(f"Logística · card do pedido {m['pedido']}" if m.get("tipo") == "logistica"
                                       else f"{m['fornecedor_nome']} · OC {m['oc_numero']}"), font=fonte(13, True),
                         anchor="w").pack(anchor="w")
            ctk.CTkLabel(textos, text=f"{m['rotulo']} · pedido {m['pedido']}", font=fonte(12),
                         text_color=cores[m["etapa"]], anchor="w").pack(anchor="w")

            def ja_enviei(mensagem=m, linha=linha):
                fi.registrar_mensagem_enviada(mensagem)
                fi.registrar_historico(mensagem, "WhatsApp manual", "real", mensagem.get("whatsapp"), "enviada",
                                       "confirmado pela equipe")
                self.mensagens = [x for x in self.mensagens if x is not mensagem]
                self.telas["mensagens"].mostrar_mensagens(self.mensagens)
                self.atualizar_contagem_mensagens()
                linha.destroy()

            ctk.CTkButton(linha, text="Já enviei", width=90, height=32, font=fonte(12), fg_color=VERDE,
                          hover_color=("#17643F", "#3AA874"), command=ja_enviei).pack(side="right", padx=(4, 10))
            if m["whatsapp"]:
                ctk.CTkButton(linha, text="Enviar no WhatsApp", width=150, height=32, font=fonte(12, True),
                              command=lambda mensagem=m: webbrowser.open(fi.link_whatsapp(mensagem))).pack(side="right")
            else:
                ctk.CTkLabel(linha, text="sem WhatsApp" if m.get("tipo") == "logistica" else "sem WhatsApp no Bling",
                             font=fonte(12), text_color=AMBAR).pack(
                    side="right", padx=6)
        if quantidade > self.MAX_NO_AVISO:
            ctk.CTkLabel(aviso, text=f"…e mais {quantidade - self.MAX_NO_AVISO} na tela Mensagens.", font=fonte(12),
                         text_color=SUAVE).pack(padx=24, anchor="w", pady=(4, 0))

        botoes = ctk.CTkFrame(aviso, fg_color="transparent")
        botoes.pack(fill="x", padx=24, pady=16)

        def abrir():
            aviso.destroy()
            self.deiconify()
            self.lift()
            self.mostrar("mensagens")

        ctk.CTkButton(botoes, text="Ver todas", height=36, width=110, font=fonte(13), fg_color="transparent",
                      border_width=1, border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                      command=abrir).pack(side="left")
        ctk.CTkButton(botoes, text="Fechar", height=36, width=90, font=fonte(13), fg_color="transparent",
                      border_width=1, border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                      command=aviso.destroy).pack(side="left", padx=10)

    def _montar_lateral(self):
        lateral = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=LATERAL)
        lateral.grid(row=0, column=0, rowspan=2, sticky="nsw")
        lateral.grid_propagate(False)
        marca = ctk.CTkFrame(lateral, fg_color="transparent")
        marca.pack(fill="x", padx=20, pady=(26, 30))
        ctk.CTkLabel(marca, text="B", width=44, height=44, corner_radius=12, fg_color=DESTAQUE,
                     text_color="#FFFFFF", font=fonte(24, True)).pack(side="left")
        textos = ctk.CTkFrame(marca, fg_color="transparent")
        textos.pack(side="left", padx=12)
        ctk.CTkLabel(textos, text="Assistente", font=fonte(17, True), anchor="w").pack(anchor="w")
        ctk.CTkLabel(textos, text="do Vendedor", font=fonte(13), text_color=SUAVE, anchor="w").pack(anchor="w")

        self.botoes_nav = {}
        for chave, texto in self.NAVEGACAO:
            botao = ctk.CTkButton(lateral, text=texto, anchor="w", height=42, corner_radius=10, font=fonte(14),
                                  fg_color="transparent", text_color=("#1F2937", "#E5E7EB"),
                                  hover_color=CARTAO_HOVER, command=lambda c=chave: self.mostrar(c))
            botao.pack(fill="x", padx=14, pady=3)
            self.botoes_nav[chave] = botao

        rodape = ctk.CTkFrame(lateral, fg_color="transparent")
        rodape.pack(side="bottom", fill="x", padx=16, pady=18)
        ctk.CTkLabel(rodape, text="Aparência", font=fonte(12), text_color=SUAVE).pack(anchor="w")
        tema = ctk.CTkSegmentedButton(rodape, values=["Claro", "Escuro", "Sistema"], font=fonte(12),
                                      command=lambda v: ctk.set_appearance_mode(
                                          {"Claro": "light", "Escuro": "dark"}.get(v, "system")))
        tema.set("Sistema")
        tema.pack(fill="x", pady=(4, 0))

    def mostrar(self, chave):
        if self.atual:
            self.telas[self.atual].grid_forget()
        self.telas[chave].grid(row=0, column=0, sticky="nsew")
        self.atual = chave
        for nome, botao in self.botoes_nav.items():
            ativo = nome == chave
            botao.configure(fg_color=DESTAQUE if ativo else "transparent",
                            text_color="#FFFFFF" if ativo else ("#1F2937", "#E5E7EB"),
                            hover_color=DESTAQUE if ativo else CARTAO_HOVER)
        tela = self.telas[chave]
        if hasattr(tela, "ao_mostrar"):
            self.after(50, tela.ao_mostrar)

    def em_segundo_plano(self, funcao, ao_terminar=None):
        """Roda a função numa thread (para a janela não travar) e chama ao_terminar(resultado, erro)."""
        def correr():
            resultado, erro = None, None
            try:
                resultado = funcao()
            except Exception as e:
                erro = e
                print(f"\n=== ERRO ===\n{e}")
            if ao_terminar:  # a janela chama ao_terminar no próprio loop (Tk não é seguro entre threads)
                self.terminados.put((ao_terminar, resultado, erro))
        threading.Thread(target=correr, daemon=True).start()

    def _receber(self):
        """Leva para a janela o que o fluxo imprimiu e as perguntas que ele fez."""
        compras = self.telas["compras"]
        try:
            while True:
                compras.escrever(self.ponte.saida.get_nowait())
        except queue.Empty:
            pass
        try:
            while True:
                tipo, pergunta, opcoes = self.ponte.perguntas.get_nowait()
                if compras.rodando:
                    if self.atual != "compras":
                        self.mostrar("compras")
                    if tipo == "opcoes":
                        compras.perguntar_opcoes(pergunta, opcoes)
                    else:
                        compras.perguntar(pergunta)
                else:  # pergunta fora das compras (ex.: autorização do Bling ao buscar itens)
                    self.ponte.respostas.put(self._perguntar_em_dialogo(pergunta, opcoes))
        except queue.Empty:
            pass
        try:
            while True:
                ao_terminar, resultado, erro = self.terminados.get_nowait()
                try:
                    ao_terminar(resultado, erro)
                except Exception as falha:  # um erro na tela não pode parar o loop da janela
                    print(f"\n=== ERRO ===\n{falha}")
        except queue.Empty:
            pass
        self.after(80, self._receber)

    def _perguntar_em_dialogo(self, pergunta, opcoes):
        """Fora da tela de Compras: uma caixinha de texto (com as opções listadas, se houver)."""
        texto = pergunta.strip()
        if opcoes:
            texto += "\n\n" + "\n".join(f"{chave or 'Enter'} = {rotulo}" for chave, rotulo in opcoes)
        resposta = (ctk.CTkInputDialog(title=TITULO, text=texto).get_input() or "").strip()
        if opcoes:
            achada = [c for c, r in opcoes if fi.sem_acento(resposta) in (fi.sem_acento(c), fi.sem_acento(r))]
            return achada[0] if achada else opcoes[-1][0]
        return resposta

    def copiar(self, texto):
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.update()


def diagnosticar_whatsapp():
    """'Assistente do Vendedor.exe --diagnostico-whatsapp': abre o navegador do WhatsApp escondido e anota
    o resultado em diagnostico_whatsapp.txt (para conferir o .exe sem precisar clicar em nada)."""
    import traceback
    from configuracao import pasta_base
    caminho = os.path.join(pasta_base(), "diagnostico_whatsapp.txt")
    try:
        import WHATSAPP  # noqa: F401  (ajusta o caminho do navegador no .exe)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            navegador = p.chromium.launch(headless=True)
            pagina = navegador.new_page()
            pagina.set_content("<h1>ok</h1>")
            resultado = f"OK: navegador abriu ({pagina.inner_text('h1')}) | {os.environ.get('PLAYWRIGHT_BROWSERS_PATH')}"
            navegador.close()
    except Exception:
        resultado = "ERRO:\n" + traceback.format_exc()
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(resultado + "\n")


if __name__ == "__main__":
    if "--diagnostico-whatsapp" in sys.argv:
        diagnosticar_whatsapp()
    else:
        App().mainloop()
