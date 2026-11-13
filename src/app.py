"""
Assistente do Vendedor - janela do aplicativo.

Módulos (a lateral abre o módulo; as telas de cada um viram abas no topo):
    Início    cartões dos módulos + situação das integrações (aqui em app.py)
    Vendas    telas_vendas.py: Lançar pedido, Calculadora, Conferência e Mensagens
    Compras   telas_compras.py: o fluxo de compras e, por um botão dentro dele, a Descrição HTML
    Cadastro  telas_cadastro.py: varredura das tabelas de fornecedor e correção de valores

Cores, fontes e componentes comuns ficam em interface.py. A lógica continua no ferramentas_internas.py.
O fluxo de compras usa print()/input(): aqui eles são ligados ao painel da tela
de Compras (o fluxo roda numa thread separada para a janela não travar).

Rode:  py app.py
"""

import builtins
import os
import queue
import sys
import threading
import time
from datetime import date, datetime

import customtkinter as ctk

import ferramentas_internas as fi
from interface import (
    AMBAR, BORDA, CARTAO, CARTAO_HOVER, Cartao, DESTAQUE, LATERAL, Ponte, SUAVE, TITULO, VERDE, VERMELHO,
    aplicar_tema_laranja, data_por_extenso, estado_integracoes, fonte, recurso,
)
from telas_vendas import TelaCalculadora, TelaConferencia, TelaLancarPedido, TelaMensagens
from telas_compras import TelaCompras, TelaHTML
from telas_cadastro import TelaCadastro


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
            ("💼", "Vendas", "Lançar pedido, calculadora, conferência de pedidos e mensagens.", "vendas"),
            ("🛒", "Compras", "Pedido da Tray → OCs no Bling → cards no Trello, passo a passo.", "compras"),
            ("🏷️", "Cadastro", "Tabela do fornecedor → confere e corrige valores no Bling e na Tray.", "cadastro"),
        ]
        por_linha = 3
        for i, (icone, titulo, descricao, tela) in enumerate(cartoes):
            grade.grid_columnconfigure(i % por_linha, weight=1, uniform="cartoes")
            Cartao(grade, icone, titulo, descricao, lambda m=tela: app.abrir_modulo(m)).grid(
                row=i // por_linha, column=i % por_linha, sticky="nsew", padx=8, pady=6)

        ctk.CTkLabel(self, text="Integrações", font=fonte(15, True)).pack(anchor="w", padx=36, pady=(34, 8))
        linha = ctk.CTkFrame(self, fg_color="transparent")
        linha.pack(anchor="w", padx=30)
        for nome, ok in estado_integracoes().items():
            chip = ctk.CTkFrame(linha, fg_color=CARTAO, corner_radius=20, border_width=1, border_color=BORDA)
            chip.pack(side="left", padx=6)
            ctk.CTkLabel(chip, text="●", font=fonte(14), text_color=VERDE if ok else SUAVE).pack(
                side="left", padx=(14, 6), pady=6)
            ctk.CTkLabel(chip, text=f"{nome}: {ok if isinstance(ok, str) else 'configurado' if ok else 'não configurado'}",
                         font=fonte(13)).pack(side="left", padx=(0, 14))

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


class App(ctk.CTk):
    # módulo: (texto na lateral, telas; com mais de uma, viram abas no topo)
    MODULOS = {
        "inicio": ("🏠   Início", ["inicio"]),
        "vendas": ("💼   Vendas", ["lancar", "calculadora", "conferencia", "mensagens"]),
        "compras": ("🛒   Compras", ["compras"]),
        "cadastro": ("🏷   Cadastro", ["cadastro"]),
    }
    ROTULOS_ABAS = {"lancar": "Lançar pedido", "calculadora": "Calculadora", "conferencia": "Conferência",
                    "mensagens": "Mensagens"}
    MODULO_DA_TELA = {**{tela: modulo for modulo, (_, telas) in MODULOS.items() for tela in telas},
                      "html": "compras"}  # o HTML abre por um botão dentro de Compras

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
        self.ultima_aba = {}  # módulo -> última aba aberta
        self.quantidade_mensagens = 0
        self._montar_lateral()
        if fi.MODO_DEMO:
            faixa = ctk.CTkFrame(self, fg_color=CARTAO_HOVER, corner_radius=0)
            faixa.grid(row=0, column=1, sticky="ew")
            ctk.CTkLabel(faixa, text="MODO DEMONSTRAÇÃO  ·  loja, clientes e pedidos fictícios  ·  nada é enviado ao "
                                     "Bling, Trello, Tray ou WhatsApp",
                         font=fonte(13, True), text_color=DESTAQUE).pack(anchor="w", padx=24, pady=9)
        self.area = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.area.grid(row=1, column=1, sticky="nsew")
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_rowconfigure(1, weight=1)
        self.abas = ctk.CTkSegmentedButton(self.area, values=[""], font=fonte(14), height=38,
                                           command=self._trocar_aba)
        self.telas = {
            "inicio": TelaInicio(self.area, self),
            "calculadora": TelaCalculadora(self.area, self),
            "lancar": TelaLancarPedido(self.area, self),
            "compras": TelaCompras(self.area, self),
            "conferencia": TelaConferencia(self.area, self),
            "mensagens": TelaMensagens(self.area, self),
            "html": TelaHTML(self.area, self),
            "cadastro": TelaCadastro(self.area, self),
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
        self.after(10 * 60 * 1000, self._respostas_automatico)  # depois do envio da manhã

    INTERVALO_RESPOSTAS_S = 2 * 60 * 60

    def _respostas_automatico(self):
        """Lê as respostas a cada 2 horas, em horário comercial, se houver envio real para alguém."""
        try:
            import WHATSAPP
            if not WHATSAPP.em_horario_comercial() or not fi.numeros_para_ler(WHATSAPP.cfg()):
                return
        except Exception:
            return
        if time.time() - getattr(self, "ultima_leitura", 0) >= self.INTERVALO_RESPOSTAS_S:
            self.ler_respostas(automatico=True)

    def ler_respostas(self, automatico=False):
        """Lê no WhatsApp do Assistente as respostas da Logística e da Fábrica (só leitura, em segundo plano)."""
        tela = self.telas["mensagens"]
        if self.enviando_whatsapp:
            if not automatico:
                tela.status.configure(text="Aguarde: o WhatsApp do Assistente está em uso.", text_color=AMBAR)
            return
        numeros = fi.numeros_para_ler(WHATSAPP.cfg())
        if not numeros:
            tela.status.configure(text="Nenhum número com envio real para ler respostas.", text_color=AMBAR)
            return
        self.enviando_whatsapp = True
        self.ultima_leitura = time.time()
        tela.status.configure(text="Lendo as respostas no WhatsApp (o navegador do Assistente vai abrir)...",
                              text_color=SUAVE)

        def trabalho():
            import WHATSAPP
            lidas = WHATSAPP.ler_respostas(numeros)
            return fi.registrar_respostas(lidas, desde=WHATSAPP.cfg().get("envio_real_desde"))

        def terminou(novas, erro):
            self.enviando_whatsapp = False
            agora = datetime.now().strftime("%H:%M")
            if erro:
                tela.status.configure(text=f"Não consegui ler as respostas às {agora}: {erro}", text_color=AMBAR)
                return
            pendentes = sum(r["status"] == "nova" for r in fi.carregar_respostas())
            tela.status.configure(text=f"Respostas lidas às {agora}: {novas} {'nova' if novas == 1 else 'novas'}"
                                       f" · {pendentes} para conferir", text_color=VERDE if not pendentes else AMBAR)
            self.atualizar_contagem_mensagens()
            if tela.visao.get() == "Respostas":
                tela.mostrar_respostas()

        self.em_segundo_plano(trabalho, terminou)

    def aplicar_resposta(self, resposta, acao, nova, ref):
        tela = self.telas["mensagens"]
        tela.status.configure(text="Aplicando...", text_color=SUAVE)

        def terminou(feito, erro):
            if erro:
                tela.status.configure(text=f"Não apliquei: {erro}", text_color=VERMELHO)
                return
            tela.status.configure(text=("Resposta ignorada." if acao == "ignorar" else "Feito: " + "; ".join(feito)),
                                  text_color=VERDE)
            self.atualizar_contagem_mensagens()
            tela.mostrar_respostas()
            if acao != "ignorar":
                self.atualizar_checklists()  # a régua do dia passa a usar a data nova

        self.em_segundo_plano(lambda: fi.aplicar_resposta(resposta["id"], acao, nova, ref), terminou)

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
                                              text_color=AMBAR if "atrasados" in a_separar and " 0 atrasados" not in a_separar else SUAVE)
            tela_msg.status.configure(text=f"Atualizado às {agora}", text_color=SUAVE)
            tela_msg.mostrar_mensagens(self.mensagens)
            self.atualizar_contagem_mensagens()
            if automatico and self.mensagens:
                modo = self._modo_envio()
                # Logística e Fábrica (whatsapp_envio.automatico_para) vão sozinhas, a cada conferência de hora
                # em hora (o que já foi não se repete); os demais fornecedores só pelo botão / pelo aviso do dia.
                sozinhas = [m for m in self.mensagens if self._envia_sozinha(m)] if modo == "automatico" else []
                if sozinhas:
                    self.enviar_whatsapp(automatico=True, somente=sozinhas)
                if modo != "esperar" and self.aviso_mensagens_dado != date.today():
                    self.aviso_mensagens_dado = date.today()  # antes do horário: a próxima hora tenta de novo
                    resto = [m for m in self.mensagens if all(m is not s for s in sozinhas)]
                    if resto:
                        self.avisar_mensagens(len(resto), resto)

        self.em_segundo_plano(conferir, terminou)

    @staticmethod
    def _envia_sozinha(m):
        try:
            import WHATSAPP
            c = WHATSAPP.cfg()
        except Exception:
            return False
        return (WHATSAPP.categoria(m) in (c.get("automatico_para") or ["logistica", "fabrica"])
                and not WHATSAPP.e_teste(m, c))

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

    def enviar_whatsapp(self, automatico=False, somente=None):
        """Manda as mensagens do dia (ou só as de 'somente') pelo WhatsApp Web do Assistente (em segundo plano)."""
        tela = self.telas["mensagens"]
        if self.enviando_whatsapp:
            if not automatico:
                fila = getattr(self, "fila_envio", [])
                fila += [m for m in (self.mensagens if somente is None else somente) if all(m is not f for f in fila)]
                self.fila_envio = fila
                tela.status.configure(text=f"{len(fila)} na fila: envio logo após o atual.", text_color=SUAVE)
            return
        pendentes = list(self.mensagens if somente is None else somente)
        if not pendentes:
            tela.status.configure(text="Nenhuma mensagem para enviar.", text_color=SUAVE)
            return
        self.enviando_whatsapp = True
        tela.botao_enviar.configure(text="Enviando...")
        tela.status.configure(text=f"Enviando {len(pendentes)} pelo WhatsApp (o navegador do Assistente vai abrir)...",
                              text_color=SUAVE)

        def trabalho():
            import WHATSAPP
            enviadas, falhas = WHATSAPP.enviar_lote(pendentes, ao_enviar=fi.registrar_mensagem_enviada,
                                                    real=not automatico)
            reais = enviadas if not automatico else [m for m in enviadas if not WHATSAPP.e_teste(m)]
            return (enviadas, falhas), reais

        def terminou(resultado, erro):
            self.enviando_whatsapp = False
            tela.botao_enviar.configure(text="Enviar pelo WhatsApp agora")
            agora = datetime.now().strftime("%H:%M")
            if erro:
                tela.status.configure(text=f"O envio falhou às {agora}: {erro}", text_color=AMBAR)
                if automatico:
                    self.avisar_mensagens(len(self.mensagens))
                return
            (enviadas, falhas), reais = resultado
            if reais:  # as de teste não são dadas como enviadas ao destino
                self.mensagens = [m for m in self.mensagens if all(m is not e for e in reais)]
                self.atualizar_contagem_mensagens()
            tela.mostrar_mensagens(self.mensagens)  # (se o histórico estiver aberto, ele é recarregado)
            teste = len(enviadas) - len(reais)
            texto = (f"{len(enviadas)} {'enviada' if len(enviadas) == 1 else 'enviadas'}"
                     f"{f' ({teste} de teste)' if teste else ''} às {agora}")
            if falhas:
                texto += f" · {len(falhas)} não {'foi' if len(falhas) == 1 else 'foram'}: {falhas[0][1]}"
            tela.status.configure(text=texto, text_color=AMBAR if falhas else VERDE)
            if automatico and falhas:
                self.avisar_mensagens(len(self.mensagens))
            fila, self.fila_envio = getattr(self, "fila_envio", []), []
            fila = [m for m in fila if any(m is x for x in self.mensagens)]  # o que ainda não foi
            if fila:
                self.enviar_whatsapp(somente=fila)

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
        try:
            quantidade = len(self.mensagens) + sum(r["status"] == "nova" for r in fi.carregar_respostas())
        except Exception:
            quantidade = len(self.mensagens)
        self.quantidade_mensagens = quantidade
        texto = self.MODULOS["vendas"][0]
        self.botoes_nav["vendas"].configure(text=f"{texto} ({quantidade})" if quantidade else texto)
        if self.atual and self.MODULO_DA_TELA[self.atual] == "vendas":
            self._montar_abas("vendas")

    def avisar_mensagens(self, quantidade, lista_mensagens=None):
        """Sem pop-up (desde 29/10, travava): as mensagens ficam só na tela Mensagens, com a contagem no menu."""
        self.atualizar_contagem_mensagens()
        self.telas["mensagens"].status.configure(
            text=f"{quantidade} {'mensagem' if quantidade == 1 else 'mensagens'} para enviar nesta tela.",
            text_color=AMBAR)

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
        for chave, (texto, _) in self.MODULOS.items():
            botao = ctk.CTkButton(lateral, text=texto, anchor="w", height=42, corner_radius=10, font=fonte(14),
                                  fg_color="transparent", text_color=("#1F2937", "#E5E7EB"),
                                  hover_color=CARTAO_HOVER, command=lambda c=chave: self.abrir_modulo(c))
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

    def abrir_modulo(self, modulo):
        """Abre o módulo na última aba usada (na primeira vez, na primeira aba)."""
        self.mostrar(self.ultima_aba.get(modulo, self.MODULOS[modulo][1][0]))

    def _rotulo_aba(self, tela):
        rotulo = self.ROTULOS_ABAS[tela]
        return f"{rotulo} ({self.quantidade_mensagens})" if tela == "mensagens" and self.quantidade_mensagens else rotulo

    def _montar_abas(self, modulo):
        """Mostra as abas do módulo (módulo de uma tela só não tem barra de abas)."""
        telas = self.MODULOS[modulo][1]
        if len(telas) < 2:
            self.abas.grid_forget()
            return
        self.abas.configure(values=[self._rotulo_aba(t) for t in telas])
        self.abas.set(self._rotulo_aba(self.atual))
        self.abas.grid(row=0, column=0, sticky="w", padx=36, pady=(20, 0))

    def _trocar_aba(self, rotulo):
        modulo = self.MODULO_DA_TELA[self.atual]
        self.mostrar(next(t for t in self.MODULOS[modulo][1] if self._rotulo_aba(t) == rotulo))

    def mostrar(self, chave):
        if self.atual:
            self.telas[self.atual].grid_forget()
        self.telas[chave].grid(row=1, column=0, sticky="nsew")
        self.atual = chave
        modulo = self.MODULO_DA_TELA[chave]
        if chave in self.MODULOS[modulo][1]:
            self.ultima_aba[modulo] = chave
        self._montar_abas(modulo)
        for nome, botao in self.botoes_nav.items():
            ativo = nome == modulo
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


def ja_esta_aberto():
    """Trava de instância única neste computador: dois Assistentes disputariam o token do Bling e poderiam
    repetir mensagens. Se já houver um aberto, traz a janela dele para a frente. O Windows solta a trava
    sozinho quando o programa fecha, mesmo se ele cair."""
    global _trava_instancia
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _trava_instancia = kernel32.CreateMutexW(None, False, "Local\\AssistenteDoVendedor")
    if ctypes.get_last_error() != 183:  # ERROR_ALREADY_EXISTS
        return False
    janela = ctypes.windll.user32.FindWindowW(None, TITULO)
    if janela:
        ctypes.windll.user32.ShowWindow(janela, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(janela)
    return True


if __name__ == "__main__":
    if "--diagnostico-whatsapp" in sys.argv:
        diagnosticar_whatsapp()
    elif not ja_esta_aberto():
        App().mainloop()
