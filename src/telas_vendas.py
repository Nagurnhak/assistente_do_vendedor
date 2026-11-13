"""Módulo Vendas: Lançar pedido, Calculadora, Conferência e Mensagens."""

import os
import re
import webbrowser
from datetime import date, datetime

import customtkinter as ctk

import ferramentas_internas as fi
from interface import (
    AMBAR, BORDA, CARTAO, CARTAO_HOVER, CaixaValor, DESTAQUE, DESTAQUE_HOVER, LATERAL, SUAVE, TITULO, VERDE,
    VERMELHO, _moeda, _numero, campo, fonte, titulo_tela,
)


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
        self.visao = ctk.CTkSegmentedButton(linha_visao, values=["Mensagens de hoje", "Respostas",
                                                                 "Histórico de envios"],
                                            font=fonte(13), height=34, command=self.trocar_visao)
        self.visao.set("Mensagens de hoje")
        self.visao.pack(side="left")
        self.botao_exportar = ctk.CTkButton(linha_visao, text="Exportar para Excel", height=34, width=160,
                                            font=fonte(13), fg_color="transparent", border_width=1,
                                            border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                            command=self.exportar_historico)
        self.botao_ler = ctk.CTkButton(linha_visao, text="Ler respostas agora", height=34, width=170,
                                       font=fonte(13), fg_color="transparent", border_width=1,
                                       border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                       command=lambda: app.ler_respostas())
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
        reais = [nome for chave, nome in (("logistica", "Logística"), ("fabrica", "Fábrica"))
                 if chave in (c.get("envio_real") or [])]
        if c["modo_teste"] and reais:
            texto = (f"Automático para {' e '.join(reais)}. Demais fornecedores: só quando vocês clicam em "
                     "'Enviar pelo Assistente' (o clique envia de verdade).")
        elif c["modo_teste"]:
            texto = ("MODO TESTE: as mensagens vão para os números de teste ("
                     + ", ".join(c["numeros_teste"] or ["nenhum"]) + "), não para os fornecedores.")
        else:
            texto = "Envio para os fornecedores ativado."
        texto += (f" Envio automático: ligado, a partir das {c['horario']} em dias úteis."
                  if c["envio_automatico"] else " Envio automático: desligado (use o botão).")
        self.modo.configure(text=texto, text_color=AMBAR if c["modo_teste"] else SUAVE)

    # ----- visões: mensagens de hoje / histórico -----

    def trocar_visao(self, _=None):
        self.botao_exportar.pack_forget()
        self.botao_ler.pack_forget()
        if self.visao.get() == "Histórico de envios":
            self.botao_exportar.pack(side="left", padx=10)
            self.mostrar_historico()
        elif self.visao.get() == "Respostas":
            self.botao_ler.pack(side="left", padx=10)
            self.mostrar_respostas()
        else:
            self.mostrar_mensagens(self._mensagens)

    # ----- respostas da Logística e da Fábrica -----

    def mostrar_respostas(self):
        for filho in self.lista.winfo_children():
            filho.destroy()
        respostas = sorted(fi.carregar_respostas(), key=lambda r: (r["status"] != "nova", r.get("quando") or ""),
                           reverse=False)
        novas = [r for r in respostas if r["status"] == "nova"]
        feitas = sorted((r for r in respostas if r["status"] != "nova"), key=lambda r: r.get("aplicada_em") or "",
                        reverse=True)[:30]
        if not novas:
            vazio = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA)
            vazio.pack(fill="x", padx=8, pady=6)
            ctk.CTkLabel(vazio, text="Nenhuma resposta nova", font=fonte(15, True)).pack(
                anchor="w", padx=18, pady=(14, 2))
            ctk.CTkLabel(vazio, text="O Assistente lê as conversas com a Logística e a Fábrica a cada 2 horas, no "
                                     "horário comercial (ou no botão 'Ler respostas agora'). Cada resposta aparece "
                                     "aqui com a data sugerida; nada muda sem você confirmar.",
                         font=fonte(13), text_color=SUAVE, wraplength=820, justify="left").pack(
                anchor="w", padx=18, pady=(0, 14))
        for r in novas:
            self._cartao_resposta(r)
        if feitas:
            ctk.CTkLabel(self.lista, text="Já conferidas", font=fonte(13, True), text_color=SUAVE).pack(
                anchor="w", padx=12, pady=(14, 2))
            for r in feitas:
                quando = (r.get("aplicada_em") or "")[:16]
                linha = (f"{quando} · {r['quem']} · {r.get('ref_aplicada') or ', '.join(r.get('refs') or [])} · "
                         f"{'ignorada' if r['status'] == 'ignorada' else '; '.join(r.get('feito') or [])}")
                ctk.CTkLabel(self.lista, text=f"{linha}\n“{r['texto'][:160]}”", font=fonte(12), text_color=SUAVE,
                             wraplength=820, justify="left", anchor="w").pack(fill="x", padx=14, pady=2)

    def _cartao_resposta(self, r):
        cartao = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA)
        cartao.pack(fill="x", padx=8, pady=6)
        topo = ctk.CTkFrame(cartao, fg_color="transparent")
        topo.pack(fill="x", padx=18, pady=(14, 4))
        ctk.CTkLabel(topo, text=r["quem"], font=fonte(15, True)).pack(side="left")
        quando = r.get("quando") or ""
        if quando:
            quando = datetime.strptime(quando, "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")
        ctk.CTkLabel(topo, text=f"  {quando}", font=fonte(13), text_color=SUAVE).pack(side="left")
        refs = r.get("refs") or []
        sobre = ", ".join(x.replace("#P", "card do pedido ").replace("#OC", "OC ") for x in refs) or "sem referência"
        if r.get("ref_incerta") and refs:
            sobre += " (pela última mensagem enviada; confira)"
        ctk.CTkLabel(topo, text=sobre, font=fonte(13, True), text_color=AMBAR if r.get("ref_incerta") else DESTAQUE
                     ).pack(side="right")
        ctk.CTkLabel(cartao, text=f"“{r['texto']}”", font=fonte(14), wraplength=820, justify="left",
                     anchor="w").pack(fill="x", padx=18, pady=(2, 8))
        botoes = ctk.CTkFrame(cartao, fg_color="transparent")
        botoes.pack(fill="x", padx=18, pady=(0, 14))
        escolha_ref = ctk.CTkComboBox(botoes, values=refs or [""], width=130, height=34, font=fonte(13))
        escolha_ref.set(refs[0] if refs else "")
        if len(refs) != 1:  # várias referências citadas, ou nenhuma: escolhe/digita (ex.: #P1002 ou #OC5001)
            escolha_ref.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(botoes, text="Nova data:", font=fonte(13)).pack(side="left")
        campo = ctk.CTkEntry(botoes, width=110, height=34, font=fonte(13), placeholder_text="dd/mm/aaaa")
        if r.get("data_sugerida"):
            campo.insert(0, datetime.strptime(r["data_sugerida"], "%Y-%m-%d").strftime("%d/%m/%Y"))
        campo.pack(side="left", padx=6)
        aviso = ctk.CTkLabel(cartao, text="", font=fonte(12), text_color=AMBAR, anchor="w")

        def aplicar(acao):
            nova = None
            if acao == "data":
                try:
                    nova = datetime.strptime(campo.get().strip(), "%d/%m/%Y").date()
                except ValueError:
                    aviso.configure(text="Digite a data como dd/mm/aaaa.")
                    aviso.pack(fill="x", padx=18, pady=(0, 10))
                    return
            ref = (escolha_ref.get() or "").strip().upper().replace(" ", "")
            if ref and not ref.startswith("#"):
                ref = "#" + ref
            self.app.aplicar_resposta(r, acao, nova, ref or None)

        ctk.CTkButton(botoes, text="Aplicar data", height=36, width=130, font=fonte(13, True),
                      command=lambda: aplicar("data")).pack(side="left", padx=(4, 8))
        ctk.CTkButton(botoes, text="Já embarcou / pronto", height=36, width=170, font=fonte(13), fg_color=VERDE,
                      hover_color=("#17643F", "#3AA874"), command=lambda: aplicar("concluido")).pack(side="left")
        ctk.CTkButton(botoes, text="Ignorar", height=36, width=90, font=fonte(13), fg_color="transparent",
                      border_width=1, border_color=BORDA, text_color=SUAVE, hover_color=CARTAO_HOVER,
                      command=lambda: aplicar("ignorar")).pack(side="right")
        if r.get("sugestao") == "concluido":
            ctk.CTkLabel(cartao, text="Parece dizer que já foi embarcado / está pronto.", font=fonte(12),
                         text_color=VERDE, anchor="w").pack(fill="x", padx=18, pady=(0, 10))

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
        if self.visao.get() == "Respostas":
            self.mostrar_respostas()
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
            ctk.CTkButton(botoes, text="Enviar pelo Assistente", height=36, font=fonte(13, True),
                          command=lambda: self.app.enviar_whatsapp(somente=[m])).pack(side="left")
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


class TelaLancarPedido(ctk.CTkFrame):
    """Lança um pedido na Tray pela API (lógica em lancar_pedido.py)."""

    NOVO_ENDERECO = "➕  Outro endereço de entrega..."
    ESCOLHA_PARCEIRO = "Escolha o parceiro..."
    OUTRO_PARCEIRO = "Outro parceiro..."
    SEM_PARCEIRO = "(sem parceiro)"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.clientes, self.cliente = [], None
        self.enderecos, self.produtos_achados, self.itens = [], [], []
        self.parceiros_todos = []
        titulo_tela(self, "Lançar pedido",
                    "Cliente da Tray, produtos pelo nome e o pedido lançado direto pela API.")
        corpo = ctk.CTkFrame(self, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        corpo.grid_columnconfigure(0, weight=6, uniform="colunas")
        corpo.grid_columnconfigure(1, weight=5, uniform="colunas")
        corpo.grid_rowconfigure(0, weight=1)

        form = ctk.CTkScrollableFrame(corpo, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        form.grid(row=0, column=0, sticky="nsew", padx=8)
        f = ctk.CTkFrame(form, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=14, pady=(4, 16))

        # --- cliente ---
        self._secao(f, "1. Cliente")
        self.aba_cliente = ctk.CTkSegmentedButton(f, values=["Cliente cadastrado", "Cliente novo"], height=34,
                                                  font=fonte(13), command=lambda _: self.alternar_aba_cliente())
        self.aba_cliente.set("Cliente cadastrado")
        self.aba_cliente.pack(fill="x", pady=(4, 8))
        self.painel_existente = ctk.CTkFrame(f, fg_color="transparent")
        self.painel_existente.pack(fill="x")
        linha = ctk.CTkFrame(self.painel_existente, fg_color="transparent")
        linha.pack(fill="x")
        self.busca_cliente = ctk.CTkEntry(linha, height=38, font=fonte(14),
                                          placeholder_text="CNPJ, CPF, e-mail ou nome")
        self.busca_cliente.pack(side="left", fill="x", expand=True)
        self.busca_cliente.bind("<Return>", lambda e: self.buscar_cliente())
        self.botao_cliente = ctk.CTkButton(linha, text="Buscar", width=100, height=38, font=fonte(13, True),
                                           command=self.buscar_cliente)
        self.botao_cliente.pack(side="left", padx=(8, 0))
        self.escolha_cliente = ctk.CTkOptionMenu(self.painel_existente, values=["—"], height=36, font=fonte(13),
                                                 command=lambda _: self.escolher_cliente())
        self.escolha_cliente.pack(fill="x", pady=(8, 0))
        self.painel_novo = ctk.CTkFrame(f, fg_color="transparent")
        self._montar_cliente_novo(self.painel_novo)
        self.status_cliente = ctk.CTkLabel(f, text="", font=fonte(12), text_color=SUAVE, anchor="w",
                                           justify="left", wraplength=480)
        self.status_cliente.pack(anchor="w")

        ctk.CTkLabel(f, text="Endereço de entrega", font=fonte(13, True)).pack(anchor="w", pady=(10, 4))
        self.escolha_endereco = ctk.CTkOptionMenu(f, values=["—"], height=36, font=fonte(12),
                                                  command=lambda _: self.alternar_endereco())
        self.escolha_endereco.pack(fill="x")
        self.novo_endereco = ctk.CTkFrame(f, fg_color="transparent")
        self.campos_end = {}
        for chave, rotulo in (("recipient", "Destinatário"), ("address", "Rua"), ("number", "Número"),
                              ("complement", "Complemento"), ("neighborhood", "Bairro"), ("city", "Cidade"),
                              ("state", "UF"), ("zip_code", "CEP")):
            self.campos_end[chave] = campo(self.novo_endereco, rotulo)
        self.status_cobranca = ctk.CTkLabel(f, text="", font=fonte(12), text_color=SUAVE, anchor="w",
                                            justify="left", wraplength=480)
        self.status_cobranca.pack(anchor="w")

        # --- produtos ---
        self._secao(f, "2. Produtos")
        linha = ctk.CTkFrame(f, fg_color="transparent")
        linha.pack(fill="x")
        self.busca_produto = ctk.CTkEntry(linha, height=38, font=fonte(14),
                                          placeholder_text="Nome ou código (ex.: Cadeira Lina, 501)")
        self.busca_produto.pack(side="left", fill="x", expand=True)
        self.busca_produto.bind("<Return>", lambda e: self.buscar_produto())
        self.botao_produto = ctk.CTkButton(linha, text="Buscar", width=100, height=38, font=fonte(13, True),
                                           command=self.buscar_produto)
        self.botao_produto.pack(side="left", padx=(8, 0))
        self.escolha_produto = ctk.CTkOptionMenu(f, values=["—"], height=36, font=fonte(12),
                                                 command=lambda _: self.escolher_produto())
        self.escolha_produto.pack(fill="x", pady=(8, 0))
        linha = ctk.CTkFrame(f, fg_color="transparent")
        linha.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(linha, text="Qtd", font=fonte(13, True)).pack(side="left")
        self.quantidade = ctk.CTkEntry(linha, width=70, height=36, font=fonte(14))
        self.quantidade.insert(0, "1")
        self.quantidade.pack(side="left", padx=(6, 14))
        ctk.CTkLabel(linha, text="Preço unit.", font=fonte(13, True)).pack(side="left")
        self.preco = ctk.CTkEntry(linha, width=120, height=36, font=fonte(14), placeholder_text="0,00")
        self.preco.pack(side="left", padx=(6, 14))
        ctk.CTkButton(linha, text="Adicionar", height=36, font=fonte(13, True),
                      command=self.adicionar_item).pack(side="left", fill="x", expand=True)
        self.status_produto = ctk.CTkLabel(f, text="", font=fonte(12), text_color=SUAVE, anchor="w",
                                           justify="left", wraplength=480)
        self.status_produto.pack(anchor="w")
        ctk.CTkButton(f, text="✚  Criar produto personalizado (sob medida)", height=36, font=fonte(13),
                      fg_color="transparent", border_width=1, border_color=DESTAQUE, text_color=DESTAQUE,
                      hover_color=CARTAO_HOVER, command=self.criar_personalizado).pack(fill="x", pady=(8, 0))

        # --- pedido ---
        self._secao(f, "3. Pedido")
        import lancar_pedido as lp
        ctk.CTkLabel(f, text="Parceiro", font=fonte(13, True)).pack(anchor="w", pady=(4, 4))
        self.parceiro_fixo = ctk.CTkSegmentedButton(f, values=[n for _, n in lp.parceiros_fixos()]
                                                    + [self.OUTRO_PARCEIRO], height=36, font=fonte(13),
                                                    command=lambda _: self.alternar_parceiro())
        self.parceiro_fixo.pack(fill="x")
        # "Outro parceiro": só aí a lista completa é lida da Tray (é ela que deixava a tela lenta)
        self.painel_outro = ctk.CTkFrame(f, fg_color="transparent")
        self.filtro_parceiro = ctk.CTkEntry(self.painel_outro, height=36, font=fonte(13),
                                            placeholder_text="Filtrar pelo nome")
        self.filtro_parceiro.pack(fill="x", pady=(6, 0))
        self.filtro_parceiro.bind("<KeyRelease>", lambda e: self.filtrar_parceiros())
        self.escolha_parceiro = ctk.CTkOptionMenu(self.painel_outro, values=[self.ESCOLHA_PARCEIRO], height=36,
                                                  font=fonte(13))
        self.escolha_parceiro.pack(fill="x", pady=(6, 0))
        self.frete_nome = campo(f, "Frete (nome)")
        self.frete_nome.insert(0, "Frete Fixo")
        self.frete_valor = campo(f, "Valor do frete", placeholder_text="0,00")
        self.frete_valor.bind("<KeyRelease>", lambda e: self.atualizar_resumo())
        self.pagamento = campo(f, "Forma de pagamento", placeholder_text="Ex.: Faturado 28 dias")
        ctk.CTkLabel(f, text=f"Status inicial: {lp.STATUS_PADRAO.title()} (os demais, direto na Tray)",
                     font=fonte(13, True)).pack(anchor="w", pady=(10, 0))

        # --- resumo ---
        lado = ctk.CTkFrame(corpo, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        lado.grid(row=0, column=1, sticky="nsew", padx=8)
        ctk.CTkLabel(lado, text="Resumo do pedido", font=fonte(16, True)).pack(anchor="w", padx=18, pady=(16, 6))
        self.resumo_cliente = ctk.CTkLabel(lado, text="Nenhum cliente escolhido", font=fonte(13), text_color=SUAVE,
                                           anchor="w", justify="left", wraplength=400)
        self.resumo_cliente.pack(anchor="w", padx=18)
        self.lista_itens = ctk.CTkScrollableFrame(lado, fg_color="transparent", height=220)
        self.lista_itens.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.totais = ctk.CTkLabel(lado, text="", font=fonte(14), anchor="w", justify="left")
        self.totais.pack(anchor="w", padx=18, pady=(8, 0))
        self.botao_lancar = ctk.CTkButton(lado, text="Lançar pedido na Tray", height=44, font=fonte(15, True),
                                          command=self.confirmar)
        self.botao_lancar.pack(fill="x", padx=18, pady=(12, 6))
        self.resultado = ctk.CTkLabel(lado, text="", font=fonte(13), anchor="w", justify="left", wraplength=400)
        self.resultado.pack(anchor="w", padx=18)
        self.acoes = ctk.CTkFrame(lado, fg_color="transparent")
        self.acoes.pack(fill="x", padx=18, pady=(6, 16))
        self.carregado = False
        self.atualizar_resumo()

    @staticmethod
    def _secao(master, texto):
        ctk.CTkLabel(master, text=texto, font=fonte(15, True), text_color=DESTAQUE).pack(anchor="w", pady=(16, 2))

    def ao_mostrar(self):
        self.busca_cliente.focus_set()

    # --- cliente ---
    def buscar_cliente(self):
        texto = self.busca_cliente.get().strip()
        if not texto:
            return
        import lancar_pedido as lp
        self.botao_cliente.configure(state="disabled", text="...")
        self.status_cliente.configure(text="Procurando na Tray...", text_color=SUAVE)

        def terminou(achados, erro):
            self.botao_cliente.configure(state="normal", text="Buscar")
            if erro or not achados:
                self.status_cliente.configure(text="Nenhum cliente encontrado. Cadastre o cliente na Tray "
                                                   "antes de lançar.", text_color=AMBAR)
                return
            self.clientes = achados
            rotulos = [self._rotulo_cliente(c) for c in achados]
            self.escolha_cliente.configure(values=rotulos)
            self.escolha_cliente.set(rotulos[0])
            self.status_cliente.configure(text=f"{len(achados)} cliente(s) encontrado(s).", text_color=VERDE)
            self.escolher_cliente()

        self.app.em_segundo_plano(lambda: lp.buscar_clientes(texto), terminou)

    @staticmethod
    def _rotulo_cliente(c):
        return f"{c['nome']} · {c['documento'] or c['email']} (id {c['id']})"

    # --- cliente novo (dados que o cliente manda pelo WhatsApp) ---
    CAMPOS_NOVO = (("nome", "Nome / nome da empresa"), ("documento", "CPF ou CNPJ"),
                   ("razao", "Razão social (empresa)"), ("ie", "Inscrição estadual (ou Isento)"),
                   ("email", "E-mail"), ("celular", "Celular / WhatsApp"), ("cep", "CEP"),
                   ("rua", "Rua / avenida"), ("numero", "Número"), ("complemento", "Complemento"),
                   ("bairro", "Bairro"), ("cidade", "Cidade"), ("uf", "UF"), ("recebe", "Quem recebe a entrega"))

    def _montar_cliente_novo(self, painel):
        topo = ctk.CTkFrame(painel, fg_color="transparent")
        topo.pack(fill="x")
        ctk.CTkLabel(topo, text="Mensagem do cliente (cole do WhatsApp)", font=fonte(13, True)).pack(side="left")
        self.botao_modelo = ctk.CTkButton(topo, text="Copiar modelo p/ o cliente", height=30, width=190,
                                          font=fonte(12), fg_color="transparent", border_width=1,
                                          border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                          command=self.copiar_modelo)
        self.botao_modelo.pack(side="right")
        self.mensagem_cliente = ctk.CTkTextbox(painel, height=130, font=fonte(13), border_width=1, wrap="word")
        self.mensagem_cliente.pack(fill="x", pady=(6, 0))
        self.botao_preencher = ctk.CTkButton(painel, text="Preencher os campos", height=38, font=fonte(13, True),
                                             command=self.preencher_cliente_novo)
        self.botao_preencher.pack(fill="x", pady=(8, 0))
        self.campos_novo = {}
        grade = ctk.CTkFrame(painel, fg_color="transparent")
        grade.pack(fill="x", pady=(6, 0))
        grade.grid_columnconfigure((0, 1), weight=1, uniform="novo")
        for i, (chave, rotulo) in enumerate(self.CAMPOS_NOVO):
            bloco = ctk.CTkFrame(grade, fg_color="transparent")
            bloco.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 8) if i % 2 == 0 else (8, 0), pady=3)
            ctk.CTkLabel(bloco, text=rotulo, font=fonte(12, True), anchor="w").pack(anchor="w")
            self.campos_novo[chave] = ctk.CTkEntry(bloco, height=34, font=fonte(13))
            self.campos_novo[chave].pack(fill="x")
        self.campos_novo["cep"].bind("<FocusOut>", lambda e: self.buscar_cep_novo())
        self.botao_cadastrar = ctk.CTkButton(painel, text="Cadastrar cliente na Tray", height=40,
                                             font=fonte(14, True), command=self.cadastrar_cliente_novo)
        self.botao_cadastrar.pack(fill="x", pady=(10, 0))

    def alternar_aba_cliente(self):
        if self.aba_cliente.get() == "Cliente novo":
            self.painel_existente.pack_forget()
            self.painel_novo.pack(fill="x", before=self.status_cliente)
            self.mensagem_cliente.focus_set()
        else:
            self.painel_novo.pack_forget()
            self.painel_existente.pack(fill="x", before=self.status_cliente)

    def copiar_modelo(self):
        import lancar_pedido as lp
        self.app.copiar(lp.modelo_mensagem_cliente())
        self.botao_modelo.configure(text="Modelo copiado ✓")
        self.after(2500, lambda: self.botao_modelo.configure(text="Copiar modelo p/ o cliente"))

    def _valores_novo(self):
        return {k: e.get().strip() for k, e in self.campos_novo.items()}

    def _preencher_campos_novo(self, dados, so_vazios=False):
        for chave, entrada in self.campos_novo.items():
            valor = str(dados.get(chave) or "").strip()
            if valor and (not so_vazios or not entrada.get().strip()):
                entrada.delete(0, "end")
                entrada.insert(0, valor)

    def preencher_cliente_novo(self):
        import lancar_pedido as lp
        texto = self.mensagem_cliente.get("1.0", "end").strip()
        if not texto:
            self.status_cliente.configure(text="Cole a mensagem do cliente.", text_color=AMBAR)
            return
        self.botao_preencher.configure(state="disabled", text="Lendo a mensagem...")

        def trabalho():
            d = lp.interpretar_dados_cliente(texto)
            d = lp.completar_endereco(d, lp.consultar_cep(d.get("cep")))
            cnpj = lp.consultar_cnpj(d.get("documento")) if len(lp._so_numeros(d.get("documento"))) == 14 else {}
            if cnpj:
                d.setdefault("razao", cnpj["razao"])
                for chave in ("rua", "numero", "complemento", "bairro", "cidade", "uf", "cep"):
                    if not d.get(chave):
                        d[chave] = cnpj.get(chave)
            existente = lp.cliente_existente(d.get("documento"), d.get("email"))
            return d, cnpj, existente

        def terminou(resultado, erro):
            self.botao_preencher.configure(state="normal", text="Preencher os campos")
            if erro:
                self.status_cliente.configure(text=f"Não consegui ler a mensagem ({erro}).", text_color=VERMELHO)
                return
            d, cnpj, existente = resultado
            self._preencher_campos_novo(d)
            faltando = [rotulo for chave, rotulo in self.CAMPOS_NOVO
                        if chave in ("nome", "documento", "email", "cep", "rua", "numero", "bairro", "cidade", "uf")
                        and not self.campos_novo[chave].get().strip()]
            avisos = []
            if cnpj:
                avisos.append(f"CNPJ na Receita: {cnpj['razao']} ({cnpj['situacao']})")
            if existente:
                avisos.append(f"⚠ JÁ CADASTRADO: {existente['nome']} (id {existente['id']}). Use 'Cliente "
                              "cadastrado'.")
            if faltando:
                avisos.append("Faltando: " + ", ".join(faltando))
            self.status_cliente.configure(text="\n".join(avisos) or "Campos preenchidos ✓ Confira antes de "
                                                                    "cadastrar.",
                                          text_color=AMBAR if (existente or faltando) else VERDE)

        self.app.em_segundo_plano(trabalho, terminou)

    def buscar_cep_novo(self):
        import lancar_pedido as lp
        cep = self.campos_novo["cep"].get().strip()
        if len(lp._so_numeros(cep)) != 8:
            return
        self.app.em_segundo_plano(lambda: lp.consultar_cep(cep),
                                  lambda info, erro: info and self._preencher_campos_novo(info, so_vazios=True))

    def cadastrar_cliente_novo(self):
        from tkinter import messagebox
        import lancar_pedido as lp
        dados = self._valores_novo()
        if not messagebox.askyesno(TITULO, f"Cadastrar este cliente {'na DEMONSTRAÇÃO (nada é enviado)' if fi.MODO_DEMO else 'NA LOJA REAL da Tray'}?\n\n"
                                           + "\n".join(f"{rotulo}: {dados[chave]}" for chave, rotulo in self.CAMPOS_NOVO
                                                       if dados[chave])):
            return
        self.botao_cadastrar.configure(state="disabled", text="Cadastrando na Tray...")

        def terminou(cid, erro):
            self.botao_cadastrar.configure(state="normal", text="Cadastrar cliente na Tray")
            if erro:
                self.status_cliente.configure(text=f"Cliente NÃO cadastrado: {erro}", text_color=VERMELHO)
                return
            # o cliente novo já fica escolhido no pedido pelo id que a Tray devolveu (a busca logo depois do
            # cadastro às vezes ainda não o encontra)
            self.aba_cliente.set("Cliente cadastrado")
            self.alternar_aba_cliente()
            self.busca_cliente.delete(0, "end")
            self.busca_cliente.insert(0, lp._so_numeros(dados["documento"]))
            novo = {"id": cid, "nome": dados["nome"], "razao": dados.get("razao") or "",
                    "documento": lp._formatar_documento(lp._so_numeros(dados["documento"])),
                    "email": dados["email"]}
            self.clientes = [novo]
            rotulo = self._rotulo_cliente(novo)
            self.escolha_cliente.configure(values=[rotulo])
            self.escolha_cliente.set(rotulo)
            self.escolher_cliente()
            self.status_cliente.configure(text=f"Cliente cadastrado na Tray (id {cid}) e já escolhido neste pedido ✓ "
                                               "Agora é só incluir os produtos.", text_color=VERDE)

        self.app.em_segundo_plano(lambda: lp.cadastrar_cliente(dados), terminou)

    def escolher_cliente(self):
        rotulo = self.escolha_cliente.get()
        self.cliente = next((c for c in self.clientes if self._rotulo_cliente(c) == rotulo), None)
        if not self.cliente:
            return
        import lancar_pedido as lp
        self.escolha_endereco.configure(values=["Carregando..."])
        self.escolha_endereco.set("Carregando...")
        cid = self.cliente["id"]

        def terminou(enderecos, erro):
            self.enderecos = enderecos or []
            opcoes = [e["texto"] for e in self.enderecos] + [self.NOVO_ENDERECO]
            self.escolha_endereco.configure(values=opcoes)
            entrega = next((e for e in self.enderecos if e["tipo"] == "1"), None)
            self.escolha_endereco.set(entrega["texto"] if entrega else opcoes[0])
            cobranca = self._cobranca()
            self.status_cobranca.configure(
                text=f"Cobrança: {cobranca['texto']}" if cobranca else "Cliente sem endereço de cobrança na Tray.",
                text_color=SUAVE if cobranca else AMBAR)
            self.alternar_endereco()
            self.atualizar_resumo()

        self.app.em_segundo_plano(lambda: lp.enderecos_cliente(cid), terminou)

    def _cobranca(self):
        return next((e for e in self.enderecos if e["tipo"] == "0"), self.enderecos[0] if self.enderecos else None)

    def alternar_endereco(self):
        if self.escolha_endereco.get() == self.NOVO_ENDERECO:
            self.novo_endereco.pack(fill="x", after=self.escolha_endereco)
        else:
            self.novo_endereco.pack_forget()

    def _entrega(self):
        escolha = self.escolha_endereco.get()
        if escolha == self.NOVO_ENDERECO:
            dados = {k: e.get().strip() for k, e in self.campos_end.items()}
            faltando = [k for k in ("address", "number", "neighborhood", "city", "state", "zip_code") if not dados[k]]
            if faltando:
                raise ValueError("Preencha rua, número, bairro, cidade, UF e CEP do endereço de entrega.")
            dados["state"] = dados["state"].upper()[:2]
            return dados
        e = next((e for e in self.enderecos if e["texto"] == escolha), None)
        if not e:
            raise ValueError("Escolha o endereço de entrega.")
        return e

    # --- produtos ---
    def buscar_produto(self):
        texto = self.busca_produto.get().strip()
        if not texto:
            return
        import lancar_pedido as lp
        self.botao_produto.configure(state="disabled", text="...")
        self.status_produto.configure(text="Procurando no Bling e na Tray...", text_color=SUAVE)

        def terminou(achados, erro):
            self.botao_produto.configure(state="normal", text="Buscar")
            if erro or not achados:
                self.status_produto.configure(text="Nenhum produto encontrado.", text_color=AMBAR)
                return
            self.produtos_achados = achados
            rotulos = [self._rotulo_produto(p) for p in achados]
            self.escolha_produto.configure(values=rotulos)
            self.escolha_produto.set(rotulos[0])
            self.status_produto.configure(text=f"{len(achados)} produto(s). Escolha na lista.", text_color=VERDE)
            self.escolher_produto()

        self.app.em_segundo_plano(lambda: lp.buscar_produtos(texto), terminou)

    @staticmethod
    def _rotulo_produto(p):
        return f"{p['codigo']} · {fi.nome_curto(p['nome'])[:70]}"

    def _produto_escolhido(self):
        rotulo = self.escolha_produto.get()
        return next((p for p in self.produtos_achados if self._rotulo_produto(p) == rotulo), None)

    def escolher_produto(self):
        p = self._produto_escolhido()
        if not p:
            return
        import lancar_pedido as lp
        self.preco.delete(0, "end")
        self.preco.insert(0, f"{p['preco']:.2f}".replace(".", ","))
        self.status_produto.configure(text="Conferindo o preço na Tray...", text_color=SUAVE)

        def terminou(preco, erro):
            if self._produto_escolhido() is not p:
                return
            if erro or not preco:
                self.status_produto.configure(text="Preço do Bling (confira).", text_color=AMBAR)
                return
            self.preco.delete(0, "end")
            self.preco.insert(0, f"{preco:.2f}".replace(".", ","))
            self.status_produto.configure(text="Preço da Tray ✓ (pode ajustar antes de adicionar)",
                                          text_color=VERDE)

        self.app.em_segundo_plano(lambda: lp.preco_tray(p["product_id"], p["variant_id"]), terminou)

    def adicionar_item(self):
        p = self._produto_escolhido()
        if not p:
            self.status_produto.configure(text="Busque e escolha um produto.", text_color=AMBAR)
            return
        try:
            quantidade = int(_numero(self.quantidade.get(), 1))
            preco = _numero(self.preco.get())
            if quantidade <= 0 or preco < 0:
                raise ValueError
        except ValueError:
            self.status_produto.configure(text="Quantidade e preço precisam ser números.", text_color=VERMELHO)
            return
        self.itens.append({"product_id": p["product_id"], "variant_id": p["variant_id"], "codigo": p["codigo"],
                           "nome": fi.nome_curto(p["nome"]), "quantidade": quantidade, "preco": preco})
        self.quantidade.delete(0, "end")
        self.quantidade.insert(0, "1")
        self.status_produto.configure(text=f"Adicionado: {quantidade}x {fi.nome_curto(p['nome'])[:60]}",
                                      text_color=VERDE)
        self.atualizar_resumo()

    def remover_item(self, indice):
        del self.itens[indice]
        self.atualizar_resumo()

    def criar_personalizado(self):
        janela = ctk.CTkToplevel(self)
        janela.title("Produto personalizado")
        janela.geometry("520x640")
        janela.transient(self.winfo_toplevel())
        janela.after(100, janela.grab_set)
        caixa = ctk.CTkScrollableFrame(janela, fg_color="transparent")
        caixa.pack(fill="both", expand=True, padx=18, pady=12)
        ctk.CTkLabel(caixa, text="Cria o produto na Tray (marca Personalizados, como os sofás personalizados) "
                                 "e já inclui no pedido.", font=fonte(12), text_color=SUAVE, wraplength=450,
                     justify="left").pack(anchor="w")
        nome = campo(caixa, "Nome", placeholder_text="Ex.: Sofá Personalizado 1,64x1,20m em linho cinza")
        ctk.CTkLabel(caixa, text="Descrição (uma linha por parágrafo)", font=fonte(13, True)).pack(
            anchor="w", pady=(10, 4))
        descricao = ctk.CTkTextbox(caixa, height=110, font=fonte(13), border_width=1, wrap="word")
        descricao.pack(fill="x")
        preco = campo(caixa, "Preço de venda (unitário)", placeholder_text="0,00")
        quantidade = campo(caixa, "Quantidade")
        quantidade.insert(0, "1")
        linha = ctk.CTkFrame(caixa, fg_color="transparent")
        linha.pack(fill="x", pady=(10, 0))
        medidas = {}
        for chave, rotulo in (("largura_cm", "Larg. cm"), ("profundidade_cm", "Prof. cm"),
                              ("altura_cm", "Alt. cm"), ("peso_kg", "Peso kg")):
            bloco = ctk.CTkFrame(linha, fg_color="transparent")
            bloco.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ctk.CTkLabel(bloco, text=rotulo, font=fonte(12, True)).pack(anchor="w")
            medidas[chave] = ctk.CTkEntry(bloco, height=34, font=fonte(13))
            medidas[chave].pack(fill="x")
        medidas["peso_kg"].insert(0, "50")
        aviso = ctk.CTkLabel(caixa, text="", font=fonte(12), text_color=VERMELHO, wraplength=450, justify="left")
        aviso.pack(anchor="w", pady=(8, 0))
        botao = ctk.CTkButton(caixa, text="Criar na Tray e incluir no pedido", height=40, font=fonte(14, True))
        botao.pack(fill="x", pady=(8, 0))

        def criar():
            import lancar_pedido as lp
            try:
                n = nome.get().strip()
                valor = _numero(preco.get())
                qtd = int(_numero(quantidade.get(), 1))
                dims = {k: _numero(e.get()) for k, e in medidas.items()}
                if not n or valor <= 0 or qtd <= 0:
                    raise ValueError
            except ValueError:
                aviso.configure(text="Preencha o nome, o preço e a quantidade (números).")
                return
            botao.configure(state="disabled", text="Criando na Tray...")
            texto = descricao.get("1.0", "end")

            def terminou(pid, erro):
                if erro:
                    botao.configure(state="normal", text="Criar na Tray e incluir no pedido")
                    aviso.configure(text=f"Não consegui criar o produto: {erro}")
                    return
                self.itens.append({"product_id": pid, "variant_id": 0, "codigo": str(pid), "nome": n,
                                   "quantidade": qtd, "preco": valor})
                self.status_produto.configure(text=f"Produto {pid} criado na Tray e incluído no pedido ✓",
                                              text_color=VERDE)
                self.atualizar_resumo()
                janela.destroy()

            self.app.em_segundo_plano(lambda: lp.criar_produto_personalizado(n, valor, texto, quantidade=qtd,
                                                                                  **dims), terminou)

        botao.configure(command=criar)

    # --- pedido ---
    def alternar_parceiro(self):
        if self.parceiro_fixo.get() != self.OUTRO_PARCEIRO:
            self.painel_outro.pack_forget()
            return
        self.painel_outro.pack(fill="x", after=self.parceiro_fixo)
        self.filtro_parceiro.focus_set()
        if self.carregado:
            return
        self.carregado = True
        import lancar_pedido as lp
        self.escolha_parceiro.configure(values=["Carregando parceiros da Tray..."])
        self.escolha_parceiro.set("Carregando parceiros da Tray...")

        def terminou(lista, erro):
            if erro:
                self.carregado = False
                self.escolha_parceiro.configure(values=[self.ESCOLHA_PARCEIRO])
                self.escolha_parceiro.set(self.ESCOLHA_PARCEIRO)
                self.resultado.configure(text=f"Não consegui ler os parceiros da Tray ({erro}).",
                                         text_color=VERMELHO)
                return
            self.parceiros_todos = lista
            self.escolha_parceiro.set(self.ESCOLHA_PARCEIRO)
            self.filtrar_parceiros()

        self.app.em_segundo_plano(lp.parceiros, terminou)

    def filtrar_parceiros(self):
        filtro = fi.sem_acento(self.filtro_parceiro.get().strip()).lower()
        vistos = [p for p in self.parceiros_todos if filtro in fi.sem_acento(p[1]).lower()][:60]
        rotulos = [self.ESCOLHA_PARCEIRO, self.SEM_PARCEIRO] + [f"{nome} (id {pid})" for pid, nome in vistos]
        atual = self.escolha_parceiro.get()
        self.escolha_parceiro.configure(values=rotulos)
        if atual not in rotulos or (filtro and atual == rotulos[0]):
            self.escolha_parceiro.set(rotulos[2] if filtro and len(rotulos) > 2 else rotulos[0])

    def _parceiro(self):
        """(id ou None, nome) do parceiro escolhido; ValueError se ainda não escolheu."""
        import lancar_pedido as lp
        escolha = self.parceiro_fixo.get()
        fixo = next((p for p in lp.parceiros_fixos() if p[1] == escolha), None)
        if fixo:
            return fixo
        if escolha == self.OUTRO_PARCEIRO:
            outro = self.escolha_parceiro.get()
            if outro == self.SEM_PARCEIRO:
                return None, outro
            achado = re.search(r"\(id (\d+)\)$", outro)
            if achado:
                return achado[1], outro
        raise ValueError("Escolha o parceiro ou Outro parceiro.")

    def atualizar_resumo(self):
        for filho in self.lista_itens.winfo_children():
            filho.destroy()
        if not self.itens:
            ctk.CTkLabel(self.lista_itens, text="Nenhum produto ainda.", font=fonte(13), text_color=SUAVE).pack(
                anchor="w", padx=8)
        for i, it in enumerate(self.itens):
            linha = ctk.CTkFrame(self.lista_itens, fg_color="transparent")
            linha.pack(fill="x", pady=2)
            ctk.CTkButton(linha, text="✕", width=28, height=28, font=fonte(12), fg_color="transparent",
                          text_color=VERMELHO, hover_color=CARTAO_HOVER,
                          command=lambda i=i: self.remover_item(i)).pack(side="left")
            ctk.CTkLabel(linha, text=f"{it['quantidade']}x {it['nome'][:48]}\n{it['codigo']} · "
                                     f"{_moeda(it['preco'])} = {_moeda(it['preco'] * it['quantidade'])}",
                         font=fonte(12), anchor="w", justify="left").pack(side="left", padx=6)
        subtotal = sum(i["preco"] * i["quantidade"] for i in self.itens)
        try:
            frete = _numero(self.frete_valor.get())
        except ValueError:
            frete = 0.0
        self.totais.configure(text=f"Produtos: {_moeda(subtotal)}\nFrete: {_moeda(frete)}\n"
                                   f"Total: {_moeda(subtotal + frete)}")
        if self.cliente:
            self.resumo_cliente.configure(text=f"{self.cliente['nome']}\n{self.cliente['razao']}".strip(),
                                          text_color=("#1F2937", "#E5E7EB"))

    def confirmar(self):
        from tkinter import messagebox
        import lancar_pedido as lp
        try:
            if not self.cliente:
                raise ValueError("Busque e escolha o cliente.")
            if not self.itens:
                raise ValueError("Inclua pelo menos um produto.")
            entrega = self._entrega()
            cobranca = self._cobranca()
            if not cobranca:
                raise ValueError("O cliente não tem endereço de cobrança na Tray.")
            frete = _numero(self.frete_valor.get())
            if not self.frete_nome.get().strip() or not self.pagamento.get().strip():
                raise ValueError("Preencha o nome do frete e a forma de pagamento.")
            parceiro_id, parceiro_nome = self._parceiro()
        except ValueError as erro:
            self.resultado.configure(text=str(erro) or "Confira os valores digitados.", text_color=VERMELHO)
            return
        subtotal = sum(i["preco"] * i["quantidade"] for i in self.itens)
        itens = "\n".join(f"  • {i['quantidade']}x {i['nome'][:60]} - {_moeda(i['preco'])}" for i in self.itens)
        texto_entrega = entrega.get("texto") or ", ".join(
            x for x in (entrega["address"], entrega["number"], entrega["neighborhood"], entrega["zip_code"]) if x)
        if not messagebox.askyesno(TITULO, f"Lançar este pedido {'na DEMONSTRAÇÃO (nada é enviado)' if fi.MODO_DEMO else 'NA LOJA REAL da Tray'}?\n\n"
                                           f"Cliente: {self.cliente['nome']}\nEntrega: {texto_entrega}\n\n"
                                           f"{itens}\n\nFrete: {self.frete_nome.get().strip()} {_moeda(frete)}\n"
                                           f"Total: {_moeda(subtotal + frete)}\n"
                                           f"Pagamento: {self.pagamento.get().strip()}\n"
                                           f"Parceiro: {parceiro_nome}\n"
                                           f"Status: {lp.STATUS_PADRAO.title()}"):
            return
        self.botao_lancar.configure(state="disabled", text="Lançando na Tray...")
        self.resultado.configure(text="", text_color=SUAVE)
        args = (self.cliente["id"], cobranca, entrega, list(self.itens), parceiro_id,
                self.frete_nome.get().strip(), frete, self.pagamento.get().strip(), lp.STATUS_PADRAO)

        def terminou(r, erro):
            self.botao_lancar.configure(state="normal", text="Lançar pedido na Tray")
            for filho in self.acoes.winfo_children():
                filho.destroy()
            if erro:
                self.resultado.configure(text=f"O pedido NÃO foi lançado: {erro}", text_color=VERMELHO)
                return
            texto = f"Pedido {r['numero']} lançado ✓" + (f" · total {_moeda(r['total'])}" if r["total"] else "")
            if r["avisos"]:
                texto += "\n\n" + "\n".join(f"⚠ {a}" for a in r["avisos"])
            self.resultado.configure(text=texto, text_color=AMBAR if r["avisos"] else VERDE)
            self.app.copiar(r["numero"])
            ctk.CTkButton(self.acoes, text="Seguir para Compras", height=36, font=fonte(13, True),
                          command=lambda: self._ir_compras(r["numero"])).pack(side="left")
            if not r["entrega_ok"]:
                ctk.CTkButton(self.acoes, text="Abrir painel da Tray", height=36, font=fonte(13),
                              fg_color="transparent", border_width=1, border_color=DESTAQUE, text_color=DESTAQUE,
                              hover_color=CARTAO_HOVER, command=lambda: webbrowser.open(lp.link_painel())).pack(
                    side="left", padx=8)
            self.itens = []
            self.atualizar_resumo()

        self.app.em_segundo_plano(lambda: lp.lancar(*args), terminou)

    def _ir_compras(self, numero):
        self.app.mostrar("compras")
        self.app.telas["compras"].iniciar(numero)


class TelaConferencia(ctk.CTkFrame):
    """Pedidos do vendedor em 'Solicitada ao depósito' / 'Em separação': itens, OCs (chegou / em aberto, com
    cobrança ao fornecedor) e a previsão do pedido (observações > Trello > Tray), para avisar o cliente a tempo."""

    CORES_ESTADO = {"chegou": VERDE, "atrasada": VERMELHO, "aberta": AMBAR, "cancelada": SUAVE}

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        import conferencia
        self.app = app
        titulo_tela(self, "Conferência de pedidos",
                    "Pedidos em “Mercadoria solicitada ao depósito central” e “Pedido em separação”: "
                    "o que já chegou, o que falta e a previsão de cada um.")
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=36, pady=(0, 12))
        ctk.CTkLabel(barra, text="Vendedor:", font=fonte(13, True)).pack(side="left")
        self.ids = {nome: pid for pid, nome in conferencia.vendedores()}
        self.vendedor = ctk.CTkSegmentedButton(barra, values=list(self.ids), font=fonte(13), height=34,
                                               command=lambda _: self.carregar())
        self.vendedor.pack(side="left", padx=8)
        self.so_atrasados = ctk.CTkCheckBox(barra, text="Só atrasados", font=fonte(13), command=self.desenhar)
        self.so_atrasados.pack(side="left", padx=8)
        self.botao_atualizar = ctk.CTkButton(barra, text="↻  Atualizar", width=120, height=34, font=fonte(13),
                                             fg_color="transparent", border_width=1, border_color=DESTAQUE,
                                             text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                                             command=lambda: self.carregar(forcar=True))
        self.botao_atualizar.pack(side="left", padx=4)
        self.status = ctk.CTkLabel(barra, text="", font=fonte(13), text_color=SUAVE, wraplength=520, justify="left")
        self.status.pack(side="left", padx=12)
        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        self.pedidos = []
        self._carregando = None  # vendedor sendo buscado agora
        self._vazio("Escolha o vendedor", "Os pedidos aparecem do mais urgente (previsão mais próxima ou vencida) "
                                          "para o mais folgado.")

    # ----- carregar / desenhar -----

    def carregar(self, forcar=False):
        import conferencia
        nome = self.vendedor.get()
        if not nome or self._carregando == nome:
            return
        self._carregando = nome
        self.botao_atualizar.configure(state="disabled")
        self.status.configure(text="Buscando os pedidos na Tray, as OCs no Bling e os cards no Trello "
                                   "(pode levar até 1 minuto)...", text_color=SUAVE)

        def terminou(pedidos, erro):
            if self._carregando == nome:
                self._carregando = None
                self.botao_atualizar.configure(state="normal")
            if nome != self.vendedor.get():  # trocou de vendedor no meio: a outra busca desenha
                return
            if erro:
                self.status.configure(text=f"Não consegui buscar os pedidos: {erro}", text_color=AMBAR)
                return
            self.pedidos = pedidos
            self.desenhar()

        self.app.em_segundo_plano(lambda: conferencia.conferir(self.ids[nome], forcar=forcar), terminou)

    @staticmethod
    def _tem_atraso(p):
        return p["atrasado"] or any(o["estado"] == "atrasada" for o in p["ocs"])

    def desenhar(self):
        for filho in self.lista.winfo_children():
            filho.destroy()
        if not self.vendedor.get():
            return
        vencidos = sum(p["atrasado"] for p in self.pedidos)
        ocs = sum(o["estado"] == "atrasada" for p in self.pedidos for o in p["ocs"])
        self.status.configure(text=f"{len(self.pedidos)} {'pedido' if len(self.pedidos) == 1 else 'pedidos'} · "
                                   f"{vencidos} com previsão vencida · {ocs} "
                                   f"{'OC atrasada' if ocs == 1 else 'OCs atrasadas'} "
                                   f"(às {datetime.now():%H:%M})", text_color=AMBAR if vencidos or ocs else SUAVE)
        mostrar = [p for p in self.pedidos if self._tem_atraso(p)] if self.so_atrasados.get() else self.pedidos
        if not mostrar:
            self._vazio("Nenhum pedido aqui", "Nenhum pedido deste vendedor nesses status"
                        + (" com atraso." if self.so_atrasados.get() else "."))
        for p in mostrar:
            self._card(p)

    def _vazio(self, titulo, texto):
        vazio = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=14, border_width=1, border_color=BORDA)
        vazio.pack(fill="x", padx=8, pady=6)
        ctk.CTkLabel(vazio, text=titulo, font=fonte(15, True)).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(vazio, text=texto, font=fonte(13), text_color=SUAVE, wraplength=820, justify="left").pack(
            anchor="w", padx=18, pady=(0, 14))

    def _card(self, p):
        import conferencia
        card = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=14, border_width=2 if p["atrasado"] else 1,
                            border_color=VERMELHO if p["atrasado"] else BORDA)
        card.pack(fill="x", padx=8, pady=6)
        topo = ctk.CTkFrame(card, fg_color="transparent")
        topo.pack(fill="x", padx=18, pady=(14, 2))
        ctk.CTkLabel(topo, text=f"Pedido {p['numero']}", font=fonte(15, True)).pack(side="left")
        ctk.CTkLabel(topo, text=f"  {p['cliente']}", font=fonte(13)).pack(side="left")
        ctk.CTkLabel(topo, text=f"{p['status']} · comprado em {conferencia.data_br(p['data'])}", font=fonte(12, True),
                     text_color=SUAVE).pack(side="right")

        linha = ctk.CTkFrame(card, fg_color="transparent")
        linha.pack(fill="x", padx=18, pady=(2, 6))
        if p["previsao"]:
            texto = f"Previsão: {p['previsao']:%d/%m/%Y}"
            if p["atrasado"]:
                dias = fi.dias_uteis_de_atraso(p["previsao"])
                texto += f" · vencida há {dias} {'dia útil' if dias == 1 else 'dias úteis'}" if dias else " · vencida"
            origem = f"  ({p['fonte']}{': ' + p['fonte_detalhe'] if p['fonte_detalhe'] else ''})"
        else:
            texto, origem = "Previsão: sem data", "  (nada nas observações, no Trello nem na Tray)"
        ctk.CTkLabel(linha, text=texto, font=fonte(14, True),
                     text_color=VERMELHO if p["atrasado"] else DESTAQUE).pack(side="left")
        ctk.CTkLabel(linha, text=origem, font=fonte(12), text_color=SUAVE).pack(side="left")
        outras = " · ".join(f"{f}: {d:%d/%m/%Y}" for f, d in p["datas"] if d and f != p["fonte"])
        if outras:
            ctk.CTkLabel(linha, text=outras, font=fonte(12), text_color=SUAVE).pack(side="right")

        for item in p["itens"]:
            sufixo, cor = "", ("#1F2937", "#E5E7EB")
            if item["oc"]:
                estado = {"chegou": "chegou", "atrasada": "atrasada", "aberta": "em aberto",
                          "cancelada": "cancelada"}[item["estado"]]
                sufixo, cor = f"  —  OC {item['oc']} {estado}", self.CORES_ESTADO[item["estado"]]
            ctk.CTkLabel(card, text=f"• {item['texto']}{sufixo}", font=fonte(13), text_color=cor, wraplength=860,
                         justify="left", anchor="w").pack(fill="x", padx=18)

        if p["ocs"]:
            ctk.CTkLabel(card, text="OCs do pedido", font=fonte(13, True), anchor="w").pack(fill="x", padx=18,
                                                                                         pady=(8, 2))
        for oc in p["ocs"]:
            linha_oc = ctk.CTkFrame(card, fg_color=LATERAL, corner_radius=10)
            linha_oc.pack(fill="x", padx=18, pady=2)
            ctk.CTkLabel(linha_oc, text=f"OC {oc['numero']} · {oc['fornecedor_nome']}", font=fonte(13, True)).pack(
                side="left", padx=(12, 8), pady=6)
            ctk.CTkLabel(linha_oc, text=("✓ " if oc["estado"] == "chegou" else "") + oc["texto"], font=fonte(13),
                         text_color=self.CORES_ESTADO[oc["estado"]]).pack(side="left")
            if oc.get("etapa"):
                self._etapa(linha_oc, oc["etapa"], oc.get("etapa_card")).pack(side="left", padx=(12, 0))
            if oc["estado"] in ("aberta", "atrasada"):
                ctk.CTkButton(linha_oc, text="Cobrar fornecedor", width=150, height=30, font=fonte(12, True),
                              fg_color=VERMELHO if oc["estado"] == "atrasada" else DESTAQUE,
                              hover_color=DESTAQUE_HOVER,
                              command=lambda o=oc: self.cobrar(p, o)).pack(side="right", padx=8, pady=4)
        for extra in p.get("fabrica_extra") or []:
            linha_fab = ctk.CTkFrame(card, fg_color=LATERAL, corner_radius=10)
            linha_fab.pack(fill="x", padx=18, pady=2)
            nome = extra["nome"] if len(extra["nome"]) <= 70 else extra["nome"][:69].rstrip() + "…"
            ctk.CTkLabel(linha_fab, text=f"Card da fábrica: {nome}", font=fonte(13)).pack(side="left", padx=(12, 8),
                                                                                          pady=6)
            self._etapa(linha_fab, extra["etapa"], extra["card"]).pack(side="left")
        if p["ocs_nao_achadas"]:
            ctk.CTkLabel(card, text=f"⚠ Anotada(s) no pedido mas não achada(s) no Bling: OC "
                                    f"{', '.join(p['ocs_nao_achadas'])}", font=fonte(12), text_color=AMBAR,
                         anchor="w").pack(fill="x", padx=18, pady=(2, 0))
        if not p["ocs"]:
            ctk.CTkLabel(card, text="Nenhuma OC ligada a este pedido (itens de estoque, ou pedido de antes do "
                                    "Assistente anotar as OCs).", font=fonte(12), text_color=SUAVE, anchor="w").pack(
                fill="x", padx=18, pady=(6, 0))

        acoes = ctk.CTkFrame(card, fg_color="transparent")
        acoes.pack(fill="x", padx=18, pady=(10, 14))
        ctk.CTkLabel(acoes, text="Nova previsão:", font=fonte(13)).pack(side="left")
        campo_data = ctk.CTkEntry(acoes, width=110, height=34, font=fonte(13), placeholder_text="dd/mm/aaaa")
        campo_data.pack(side="left", padx=6)
        aviso = ctk.CTkLabel(card, text="", font=fonte(12), anchor="w")
        ctk.CTkButton(acoes, text="Salvar na Tray", width=130, height=34, font=fonte(13, True),
                      command=lambda: self.salvar_previsao(p, campo_data, aviso)).pack(side="left", padx=(0, 8))
        ctk.CTkButton(acoes, text="Avisar cliente", width=130, height=34, font=fonte(13), fg_color="transparent",
                      border_width=1, border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                      command=lambda: self.avisar_cliente(p, campo_data)).pack(side="left")
        if p["card"]:
            ctk.CTkButton(acoes, text="Abrir card", width=110, height=34, font=fonte(13), fg_color="transparent",
                          border_width=1, border_color=BORDA, text_color=SUAVE, hover_color=CARTAO_HOVER,
                          command=lambda: webbrowser.open(p["card"])).pack(side="right")

    @staticmethod
    def _etapa(master, etapa, link):
        """'🏭 Marcenaria: Corte': a lista do Trello da fábrica em que o card está (clique abre o card)."""
        rotulo = ctk.CTkLabel(master, text=f"🏭 {etapa}", font=fonte(12, True), text_color=DESTAQUE,
                              fg_color=CARTAO, corner_radius=8)
        if link:
            rotulo.configure(cursor="hand2")
            rotulo.bind("<Button-1>", lambda e: webbrowser.open(link))
        return rotulo

    # ----- ações -----

    @staticmethod
    def _ler_data(campo):
        try:
            return datetime.strptime(campo.get().strip(), "%d/%m/%Y").date()
        except ValueError:
            return None

    def salvar_previsao(self, p, campo, aviso):
        import conferencia
        nova = self._ler_data(campo)
        if not nova:
            aviso.configure(text="Digite a nova previsão como dd/mm/aaaa.", text_color=AMBAR)
            aviso.pack(fill="x", padx=18, pady=(0, 10))
            return
        aviso.configure(text="Gravando nas observações do pedido na Tray...", text_color=SUAVE)
        aviso.pack(fill="x", padx=18, pady=(0, 10))
        vendedor = self.vendedor.get()

        def terminou(texto, erro):
            if erro:
                aviso.configure(text=f"Não gravei na Tray: {erro}", text_color=VERMELHO)
                return
            p.update(previsao=nova, fonte="Observações", fonte_detalhe=texto.split(":")[0],
                     atrasado=nova < date.today())
            p["datas"] = [("Observações", nova)] + [(f, d) for f, d in p["datas"] if f != "Observações"]
            self.pedidos.sort(key=lambda x: (x["previsao"] is None, x["previsao"] or date.max, x["numero"]))
            self.desenhar()
            self.status.configure(text=f"Pedido {p['numero']}: nova previsão {nova:%d/%m/%Y} gravada na Tray. "
                                       "Use “Avisar cliente” para mandar a data.", text_color=VERDE)

        self.app.em_segundo_plano(lambda: conferencia.registrar_nova_previsao(p["numero"], nova, vendedor),
                                  terminou)

    def avisar_cliente(self, p, campo):
        import conferencia
        texto = conferencia.texto_aviso_cliente(p, self.vendedor.get(), self._ler_data(campo))
        telefone = p["telefone"]
        explicacao = (f"Abre a conversa com {p['cliente'] or 'o cliente'} ({telefone}) no SEU WhatsApp, com o texto "
                      "pronto. Revise antes de enviar." if telefone else
                      "O cliente não tem celular no cadastro da Tray: copie o texto ou escolha o contato no WhatsApp.")
        self._dialogo(f"Avisar o cliente · pedido {p['numero']}", explicacao, texto, [
            ("Abrir no WhatsApp", lambda t: webbrowser.open(conferencia.link_whatsapp_cliente(telefone, t)), True),
            ("Copiar texto", self.app.copiar, False),
        ])

    def cobrar(self, p, oc):
        import conferencia
        mensagem = conferencia.mensagem_cobranca(p, oc)
        botoes = [("Copiar texto", self.app.copiar, False)]
        if oc["whatsapp"]:
            def enviar(texto):
                if self.app.enviando_whatsapp:
                    self.status.configure(text="O WhatsApp do Assistente está em uso agora; tente de novo em "
                                               "instantes.", text_color=AMBAR)
                    return
                mensagem["texto"] = texto
                self.app.enviar_whatsapp(somente=[mensagem])
                self.status.configure(text=f"Cobrança da OC {oc['numero']} saindo pelo WhatsApp do Assistente "
                                           "(o resultado fica em Mensagens › Histórico de envios).", text_color=VERDE)
            botoes.insert(0, ("Enviar pelo Assistente", enviar, True))
            explicacao = (f"Vai para {oc['fornecedor_nome']} ({oc['whatsapp']}) pelo WhatsApp do Assistente. "
                          "A resposta com a nova data aparece em Mensagens › Respostas.")
        else:
            explicacao = (f"{oc['fornecedor_nome']} está sem celular no cadastro do Bling: copie o texto e mande "
                          "pelo seu WhatsApp (ou cadastre o celular no contato do Bling).")
        self._dialogo(f"Cobrar fornecedor · OC {oc['numero']}", explicacao, mensagem["texto"], botoes)

    def _dialogo(self, titulo, explicacao, texto, botoes):
        """Janela com o texto editável e os botões [(rótulo, ação(texto), principal)]."""
        janela = ctk.CTkToplevel(self)
        janela.title(TITULO)
        janela.geometry("640x430")
        janela.transient(self.app)
        janela.after(150, janela.lift)
        ctk.CTkLabel(janela, text=titulo, font=fonte(16, True), anchor="w").pack(fill="x", padx=20, pady=(18, 2))
        ctk.CTkLabel(janela, text=explicacao, font=fonte(12), text_color=SUAVE, wraplength=590, justify="left",
                     anchor="w").pack(fill="x", padx=20)
        caixa = ctk.CTkTextbox(janela, font=fonte(13), wrap="word")
        caixa.pack(fill="both", expand=True, padx=20, pady=10)
        caixa.insert("1.0", texto)
        linha = ctk.CTkFrame(janela, fg_color="transparent")
        linha.pack(fill="x", padx=20, pady=(0, 16))
        for rotulo, acao, principal in botoes:
            def clicar(acao=acao):
                acao(caixa.get("1.0", "end").strip())
                janela.destroy()
            estilo = {} if principal else {"fg_color": "transparent", "border_width": 1, "border_color": DESTAQUE,
                                           "text_color": DESTAQUE, "hover_color": CARTAO_HOVER}
            ctk.CTkButton(linha, text=rotulo, height=36, font=fonte(13, principal), command=clicar,
                          **estilo).pack(side="left", padx=(0, 8))
        ctk.CTkButton(linha, text="Fechar", width=90, height=36, font=fonte(13), fg_color="transparent",
                      border_width=1, border_color=BORDA, text_color=SUAVE, hover_color=CARTAO_HOVER,
                      command=janela.destroy).pack(side="right")
