"""Módulo Compras: o fluxo de compras e a Descrição HTML."""

import os
import re
import time
from datetime import datetime

import customtkinter as ctk

import ferramentas_internas as fi
from interface import (
    AMBAR, BORDA, CARTAO, CARTAO_HOVER, CaixaValor, DESTAQUE, LATERAL, PRAZO, SUAVE, VERDE, VERMELHO, campo,
    fonte, titulo_tela,
)


class TelaHTML(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        ctk.CTkButton(self, text="← Voltar para Compras", height=32, width=170, font=fonte(13),
                      fg_color="transparent", border_width=1, border_color=DESTAQUE, text_color=DESTAQUE,
                      hover_color=CARTAO_HOVER, command=lambda: app.mostrar("compras")).pack(
            anchor="w", padx=36, pady=(18, 0))
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
        ctk.CTkButton(barra, text="Descrição HTML", height=40, width=150, font=fonte(13), fg_color="transparent",
                      border_width=1, border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                      command=lambda: app.mostrar("html")).pack(side="left")

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
            ctk.CTkLabel(self.lista_pedidos, text="Nenhum pedido em “A Enviar” ou “Liberado”.",
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
