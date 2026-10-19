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
from datetime import date

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

        self.ocioso("Clique em “Processar um pedido” para começar.")

    # ----- estados -----

    def ao_mostrar(self):
        if self.aguardando == "texto":
            self.entrada.focus_set()

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

    def iniciar(self):
        self.rodando = True
        self.buffer = []
        self._mostrar_contexto()
        self.botao_iniciar.configure(state="disabled", text="Pedido em andamento...")
        self.pergunta.configure(text="Carregando...")
        if self.console.get("1.0", "end").strip():
            self.escrever("\n", contexto=False)

        def fluxo():
            try:
                fi.processar_pedido()
                if fi.MODO_DEMO:
                    import demo
                    print("\n[demonstração] O que foi 'criado' até agora (só na memória):\n" + demo.resumo())
            except Exception as erro:
                print(f"\n=== ERRO ===\n{erro}")

        def terminou(_, __):
            self._mostrar_contexto()
            self.rodando = False
            self.botao_iniciar.configure(state="normal", text="▶  Processar outro pedido")
            self.ocioso("Pedido finalizado. Clique em “Processar outro pedido” para continuar.")
            self.escrever("\n——— fim do pedido ———\n", "resposta", contexto=False)

        self.app.em_segundo_plano(fluxo, terminou)

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
        sys.stdout = sys.stderr = self.ponte
        builtins.input = self.ponte.input
        fi._escolha_externa = self.ponte.escolher

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._montar_lateral()
        if fi.MODO_DEMO:
            faixa = ctk.CTkFrame(self, fg_color=CARTAO_HOVER, corner_radius=0)
            faixa.grid(row=0, column=1, sticky="ew")
            ctk.CTkLabel(faixa, text="MODO DEMONSTRAÇÃO  ·  loja, produtos e pedidos fictícios  ·  nada é enviado ao "
                                     "Bling, Trello ou Tray  ·  pedidos de exemplo: 1001, 1002 e 1003",
                         font=fonte(13, True), text_color=DESTAQUE).pack(anchor="w", padx=24, pady=9)
        self.area = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.area.grid(row=1, column=1, sticky="nsew")
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(0, weight=1)
        self.telas = {
            "inicio": TelaInicio(self.area, self),
            "calculadora": TelaCalculadora(self.area, self),
            "compras": TelaCompras(self.area, self),
            "html": TelaHTML(self.area, self),
        }
        self.atual = None
        self.mostrar("inicio")
        self.after(80, self._receber)

    def _montar_lateral(self):
        lateral = ctk.CTkFrame(self, width=240, corner_radius=0, fg_color=LATERAL)
        lateral.grid(row=0, column=0, rowspan=2, sticky="nsw")
        lateral.grid_propagate(False)
        marca = ctk.CTkFrame(lateral, fg_color="transparent")
        marca.pack(fill="x", padx=20, pady=(26, 30))
        ctk.CTkLabel(marca, text="A", width=44, height=44, corner_radius=12, fg_color=DESTAQUE,
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
            if ao_terminar:
                self.after(0, lambda: ao_terminar(resultado, erro))
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


if __name__ == "__main__":
    App().mainloop()
