"""Módulo Cadastro: varredura das tabelas de fornecedor e correção de valores."""

import os
from datetime import datetime

import customtkinter as ctk

import ferramentas_internas as fi
from interface import (
    AMBAR, BORDA, CARTAO, CARTAO_HOVER, DESTAQUE, SUAVE, TITULO, VERDE, VERMELHO, fonte, titulo_tela,
)


class TelaCadastro(ctk.CTkFrame):
    """Varredura das tabelas de fornecedor e correção de valores (grava no Bling e envia para a Tray)."""

    LIMITE_LINHAS = 150  # linhas desenhadas na lista (o Excel traz tudo)
    VISOES = {"Desatualizados": ("desatualizado", "sob_consulta"), "Em dia": ("em_dia",),
              "Sem item na Tray": ("sem_tray",), "Kits": ("kit",), "Novos na tabela": "novos", "Fora da tabela": "fora",
              "Código inválido": "invalidos"}

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.resultado = None
        self.marcados = {}
        self.ocupado = False
        titulo_tela(self, "Cadastro",
                    "Jogue a tabela do fornecedor: o Assistente compara com o Bling e a Tray e corrige os valores.")

        barra = ctk.CTkFrame(self, fg_color=CARTAO, corner_radius=16, border_width=1, border_color=BORDA)
        barra.pack(fill="x", padx=36)
        linha = ctk.CTkFrame(barra, fg_color="transparent")
        linha.pack(fill="x", padx=18, pady=14)
        try:
            import cadastro
            nomes = list(cadastro.fornecedores())
        except Exception:
            nomes = ["Fornecedor A"]
        self.fornecedor = ctk.CTkOptionMenu(linha, values=nomes, width=150, height=38, font=fonte(13),
                                            command=lambda _: (self.carregar_calculo(), self._tabela_demo()))
        self.fornecedor.pack(side="left")
        ctk.CTkButton(linha, text="Escolher tabela...", height=38, width=150, font=fonte(13),
                      fg_color="transparent", border_width=1, border_color=DESTAQUE, text_color=DESTAQUE,
                      hover_color=CARTAO_HOVER, command=self.escolher_arquivo).pack(side="left", padx=10)
        self.botao_varrer = ctk.CTkButton(linha, text="Fazer varredura", height=38, width=150,
                                          font=fonte(13, True), command=self.varrer, state="disabled")
        self.botao_varrer.pack(side="left")

        # Cálculo desta tabela: desconto sobre o preço de tabela, IPI, frete e margem de venda.
        linha_calc = ctk.CTkFrame(barra, fg_color="transparent")
        linha_calc.pack(fill="x", padx=18, pady=(0, 8))
        self.campos_calc = {}
        for chave, rotulo in (("desconto", "Desconto %"), ("desconto_promocional", "Desc. vermelho %"),
                              ("ipi", "IPI %"), ("frete", "Frete %"), ("margem", "Margem (x)")):
            ctk.CTkLabel(linha_calc, text=rotulo, font=fonte(12, True)).pack(side="left", padx=(0, 6))
            entrada = ctk.CTkEntry(linha_calc, width=64, height=32, font=fonte(13), justify="center")
            entrada.pack(side="left", padx=(0, 16))
            entrada.bind("<KeyRelease>", lambda e: self.mostrar_exemplo())
            self.campos_calc[chave] = entrada
        self.exemplo = ctk.CTkLabel(barra, text="", font=fonte(12), text_color=SUAVE, anchor="w")
        self.exemplo.pack(anchor="w", padx=18, pady=(0, 6))
        self.carregar_calculo()
        self.arquivo = None
        self.rotulo_arquivo = ctk.CTkLabel(barra, text="Nenhuma tabela escolhida.", font=fonte(12),
                                           text_color=SUAVE, anchor="w")
        self.rotulo_arquivo.pack(anchor="w", padx=18, pady=(0, 4))
        self.status = ctk.CTkLabel(barra, text="", font=fonte(13), text_color=SUAVE, anchor="w",
                                   wraplength=820, justify="left")
        self.status.pack(anchor="w", padx=18, pady=(0, 14))
        self._tabela_demo()

        self.resumo = ctk.CTkLabel(self, text="", font=fonte(13), anchor="w", justify="left")
        self.resumo.pack(anchor="w", padx=36, pady=(14, 6))

        acoes = ctk.CTkFrame(self, fg_color="transparent")
        acoes.pack(fill="x", padx=36, pady=(0, 8))
        self.visao = ctk.CTkSegmentedButton(acoes, values=list(self.VISOES), font=fonte(12), height=34,
                                            command=lambda _: self.trocar_visao())
        self.visao.set("Desatualizados")
        self.visao.pack(side="left")
        self.busca = ctk.CTkEntry(acoes, placeholder_text="Filtrar por nome ou código", width=210, height=34,
                                  font=fonte(12))
        self.busca.pack(side="left", padx=10)
        self.busca.bind("<KeyRelease>", lambda e: self.desenhar())

        botoes = ctk.CTkFrame(self, fg_color="transparent")
        botoes.pack(fill="x", padx=36, pady=(0, 8))
        self.botao_aplicar = ctk.CTkButton(botoes, text="Aplicar marcados (Bling + Tray)", height=38, width=240,
                                           font=fonte(13, True), command=self.aplicar, state="disabled")
        self.botao_aplicar.pack(side="left")
        for texto, valor in (("Marcar todos", True), ("Desmarcar", False)):
            ctk.CTkButton(botoes, text=texto, height=38, width=110, font=fonte(12), fg_color="transparent",
                          border_width=1, border_color=DESTAQUE, text_color=DESTAQUE, hover_color=CARTAO_HOVER,
                          command=lambda v=valor: self.marcar_todos(v)).pack(side="left", padx=(8, 0))
        self.botao_excel = ctk.CTkButton(botoes, text="Relatório em Excel", height=38, width=150, font=fonte(12),
                                         fg_color="transparent", border_width=1, border_color=DESTAQUE,
                                         text_color=DESTAQUE, hover_color=CARTAO_HOVER, command=self.exportar,
                                         state="disabled")
        self.botao_excel.pack(side="left", padx=8)

        self.lista = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.lista.pack(fill="both", expand=True, padx=28, pady=(0, 20))

    # ----- entrada -----

    def carregar_calculo(self):
        try:
            import cadastro
            perfil = cadastro.fornecedores().get(self.fornecedor.get(), {})
        except Exception:
            perfil = {}
        for chave, entrada in self.campos_calc.items():
            entrada.delete(0, "end")
            if chave == "desconto_promocional" and chave not in perfil:
                continue  # vazio = fornecedor sem regra de preço em vermelho
            valor = perfil.get(chave, 1.0 if chave == "margem" else 0.0)
            texto = f"{valor:g}" if chave == "margem" else f"{valor * 100:g}"
            entrada.insert(0, texto.replace(".", ","))
        self.mostrar_exemplo()

    def ler_calculo(self):
        """{'desconto', 'ipi', 'frete' em fração; 'margem' em vezes; 'desconto_promocional' em fração ou
        None (vazio)} ou ValueError com a mensagem."""
        valores = {}
        for chave, entrada in self.campos_calc.items():
            if chave == "desconto_promocional" and not entrada.get().strip():
                valores[chave] = None
                continue
            try:
                numero = fi.converter_numero(entrada.get().strip() or "0")
            except ValueError:
                raise ValueError(f"Valor inválido em {chave}: use números, ex.: 3,75") from None
            valores[chave] = numero if chave == "margem" else numero / 100
        if valores["margem"] <= 0:
            raise ValueError("A margem precisa ser maior que zero (ex.: 2 para dobrar o custo).")
        if not 0 <= valores["desconto"] < 1:
            raise ValueError("O desconto precisa ficar entre 0 e 100%.")
        return valores

    def mostrar_exemplo(self):
        try:
            import cadastro
            calculo = {k: v for k, v in self.ler_calculo().items() if v is not None}
            compra, custo, venda = cadastro.calcular(1000, calculo)
        except Exception as erro:
            self.exemplo.configure(text=str(erro), text_color=VERMELHO)
            return
        r = fi.formatar_reais
        texto = (f"Exemplo: tabela R$ 1.000,00 → compra {r(compra)} → custo {r(custo)} → venda {r(venda)}")
        if "desconto_promocional" in calculo:
            texto += f"   |   em vermelho: venda {r(cadastro.calcular(1000, calculo, True)[2])}"
        self.exemplo.configure(text=texto, text_color=SUAVE)

    def _tabela_demo(self):
        """Na demonstração, a tabela fictícia do fornecedor já vem escolhida."""
        if fi.MODO_DEMO:
            import demo
            self.arquivo = demo.tabela_exemplo(self.fornecedor.get())
            self.rotulo_arquivo.configure(text=f"Tabela fictícia: {os.path.basename(self.arquivo)}")
            self.botao_varrer.configure(state="normal")

    def escolher_arquivo(self):
        from tkinter import filedialog
        caminho = filedialog.askopenfilename(title="Tabela do fornecedor",
                                             filetypes=[("Planilhas Excel", "*.xlsx *.xlsm"), ("Todos", "*.*")])
        if caminho:
            self.arquivo = caminho
            self.rotulo_arquivo.configure(text=caminho)
            self.botao_varrer.configure(state="normal")

    def avisar(self, texto):
        """Chamado da thread de trabalho: a janela atualiza o status no próprio loop."""
        self.app.terminados.put((lambda t, _e: self.status.configure(text=t, text_color=SUAVE), texto, None))

    def varrer(self):
        if self.ocupado or not self.arquivo:
            return
        import cadastro
        fornecedor = self.fornecedor.get()
        try:
            calculo = self.ler_calculo()
            cadastro.salvar_calculo(fornecedor, calculo)  # a próxima tabela já abre com estes valores
        except Exception as erro:
            self.status.configure(text=str(erro), text_color=VERMELHO)
            return
        self.ocupado = True
        self.botao_varrer.configure(state="disabled", text="Varrendo...")
        self.botao_aplicar.configure(state="disabled")

        def terminou(resultado, erro):
            self.ocupado = False
            self.botao_varrer.configure(state="normal", text="Fazer varredura")
            if erro:
                self.status.configure(text=f"Não consegui fazer a varredura: {erro}", text_color=VERMELHO)
                return
            self.resultado = resultado
            # Começa tudo desmarcado: quem aplica escolhe o que conferiu (ou "Marcar todos").
            marcaveis = [i for i in resultado["itens"] if i["status"] in ("desatualizado", "sob_consulta")]
            marcaveis += [f for f in resultado["fora"] if f.get("bling_ativo") or f.get("tray_ativo")]
            self.marcados = {id(i): ctk.BooleanVar(value=False) for i in marcaveis}
            r = resultado["resumo"]
            self.resumo.configure(text=(
                f"{r['tabela']} itens na tabela  ·  {r['em_dia']} em dia  ·  {r['desatualizado']} desatualizados  ·  "
                f"{r['sob_consulta']} sob consulta (só custo)  ·  {r['sem_tray']} sem item na Tray  ·  {r.get('kit', 0)} kits (conferir à mão)  ·  "
                f"{r['novos']} novos (sem cadastro)  ·  {r['fora']} fora da tabela  ·  "
                f"{r['codigo_invalido']} com código inválido no Bling"), wraplength=900)
            agora = datetime.now().strftime("%H:%M")
            self.status.configure(text=f"Varredura concluída às {agora}. Confira os valores antes de aplicar.",
                                  text_color=VERDE)
            self.botao_aplicar.configure(state="normal")
            self.botao_excel.configure(state="normal")
            self.visao.set("Desatualizados")
            self.trocar_visao()

        self.app.em_segundo_plano(lambda: cadastro.varredura(self.arquivo, fornecedor, self.avisar, calculo),
                                  terminou)

    def trocar_visao(self):
        """Na aba 'Fora da tabela' o botão principal inativa; nas outras, aplica os valores."""
        if not self.ocupado:
            texto = ("Inativar marcados (Bling + Tray)" if self.visao.get() == "Fora da tabela"
                     else "Aplicar marcados (Bling + Tray)")
            self.botao_aplicar.configure(text=texto)
        self.desenhar()

    # ----- lista -----

    def _linhas(self):
        if not self.resultado:
            return []
        filtro = self.VISOES[self.visao.get()]
        if isinstance(filtro, str):
            linhas = self.resultado[filtro]
        else:
            linhas = [i for i in self.resultado["itens"] if i["status"] in filtro]
        from cadastro import _sem_acento
        termo = _sem_acento(self.busca.get()) if self.busca.get().strip() else ""
        if termo:
            linhas = [l for l in linhas if termo in _sem_acento(
                f"{l['codigo']} {l.get('descricao_tabela') or l.get('descricao') or ''} {l.get('bling_nome', '')}")]
        return linhas

    def desenhar(self):
        for filho in self.lista.winfo_children():
            filho.destroy()
        linhas = self._linhas()
        if not linhas:
            ctk.CTkLabel(self.lista, text="Nada para mostrar aqui." if self.resultado else
                         "Escolha a tabela e clique em Fazer varredura.", font=fonte(13),
                         text_color=SUAVE).pack(anchor="w", padx=10, pady=10)
            return
        r = fi.formatar_reais
        for l in linhas[:self.LIMITE_LINHAS]:
            card = ctk.CTkFrame(self.lista, fg_color=CARTAO, corner_radius=12, border_width=1, border_color=BORDA)
            card.pack(fill="x", padx=8, pady=4)
            topo = ctk.CTkFrame(card, fg_color="transparent")
            topo.pack(fill="x", padx=14, pady=(10, 0))
            if id(l) in self.marcados:
                ctk.CTkCheckBox(topo, text="", width=24, variable=self.marcados[id(l)]).pack(side="left")
            nome = l.get("tray_nome") or l.get("bling_nome") or l.get("descricao", "")
            ctk.CTkLabel(topo, text=f"{nome}", font=fonte(13, True), anchor="w").pack(side="left")
            ctk.CTkLabel(topo, text=f"cód. {l['codigo']}", font=fonte(12), text_color=SUAVE).pack(side="right")
            if "custo_novo" in l and "bling_custo" in l:
                partes = [f"Tabela {r(l['preco_tabela'])}{' (promocional)' if l.get('promocional') else ''}",
                          f"Custo: Bling {r(l['bling_custo'])} · Tray {r(l['tray_custo'] or 0)} → {r(l['custo_novo'])}"]
                if l["sob_consulta"]:
                    partes.append("Venda: sob consulta (não muda)")
                else:
                    atual = l["tray_venda"] or l["bling_venda"]
                    variacao = f" ({(l['venda_nova'] / atual - 1) * 100:+.1f}%)" if atual else ""
                    partes.append(f"Venda: Bling {r(l['bling_venda'])} · Tray {r(l['tray_venda'] or 0)} → "
                                  f"{r(l['venda_nova'])}{variacao}")
                texto = "   |   ".join(partes)
            elif "preco" in l:
                texto = f"{l['descricao']}   |   Tabela {r(l['preco'])} → custo {r(l['custo_novo'])} · venda {r(l['venda_nova'])}"
            elif self.visao.get() == "Código inválido":
                texto = (f"Código no Bling \"{l.get('codigo_bling') or l['codigo']}\": {l.get('motivo') or 'não é da tabela'}"
                         f" (produto Bling {l['bling_produto_id']}). Confira o código no Bling.")
            else:
                situacao = ("ativo" if l.get("tray_ativo") else "já inativo") if l.get("tray_id") else "sem item na Tray"
                texto = (f"Código não está mais na tabela: provável saída de linha. "
                         f"Bling: {'ativo' if l.get('bling_ativo') else 'inativo'} · Tray: {situacao}.")
            ctk.CTkLabel(card, text=texto, font=fonte(12), text_color=SUAVE, anchor="w", justify="left",
                         wraplength=860).pack(anchor="w", padx=14, pady=(2, 10))
        if len(linhas) > self.LIMITE_LINHAS:
            ctk.CTkLabel(self.lista, text=f"Mostrando {self.LIMITE_LINHAS} de {len(linhas)}. Use o filtro ou o "
                                          "relatório em Excel para ver todos.", font=fonte(12),
                         text_color=SUAVE).pack(anchor="w", padx=10, pady=8)

    def marcar_todos(self, valor):
        alvo = {id(l) for l in self._linhas()}
        for chave, var in self.marcados.items():
            if chave in alvo:
                var.set(valor)

    # ----- ações -----

    def exportar(self):
        if not self.resultado:
            return
        import cadastro
        from configuracao import pasta_base
        nome = f"varredura_{self.resultado['fornecedor']}_{datetime.now():%Y-%m-%d_%H%M}.xlsx"
        try:
            caminho = cadastro.exportar_excel(self.resultado, os.path.join(pasta_base(), nome))
            os.startfile(caminho)
        except Exception as erro:
            self.status.configure(text=f"Não consegui gerar o Excel: {erro}", text_color=AMBAR)

    def aplicar(self):
        if self.ocupado or not self.resultado:
            return
        if self.visao.get() == "Fora da tabela":
            return self.inativar()
        import cadastro
        from tkinter import messagebox
        itens = [i for i in self.resultado["itens"] if id(i) in self.marcados and self.marcados[id(i)].get()]
        if not itens:
            self.status.configure(text="Nenhum item marcado.", text_color=AMBAR)
            return
        so_custo = sum(1 for i in itens if i["sob_consulta"])
        if not messagebox.askyesno(TITULO, f"Aplicar os valores novos em {len(itens)} itens?\n\n"
                                           f"Grava no Bling (compra, custo e venda) e envia para a Tray.\n"
                                           f"{so_custo} deles são sob consulta: só o custo muda."):
            return
        self.ocupado = True
        self.botao_aplicar.configure(state="disabled", text="Aplicando...")

        def terminou(resultado, erro):
            self.ocupado = False
            self.botao_aplicar.configure(state="normal", text="Aplicar marcados (Bling + Tray)")
            if erro:
                self.status.configure(text=f"Parou com erro: {erro}", text_color=VERMELHO)
                return
            ok, falhas = resultado
            for item in itens:
                if not any(item is f[0] for f in falhas):
                    item["status"] = "em_dia"
                    self.marcados.pop(id(item), None)
            texto = f"{ok} itens atualizados no Bling e na Tray e conferidos no Bling."
            if falhas:
                texto += (f" {len(falhas)} com problema (ex.: cód. {falhas[0][0]['codigo']}: {falhas[0][1][:120]})."
                          " Faça uma nova varredura para ver o que ficou pendente.")
            self.status.configure(text=texto, text_color=AMBAR if falhas else VERDE)
            self.desenhar()

        self.app.em_segundo_plano(lambda: cadastro.aplicar(itens, self.avisar), terminou)

    def inativar(self):
        import cadastro
        from tkinter import messagebox
        itens = [f for f in self.resultado["fora"] if id(f) in self.marcados and self.marcados[id(f)].get()]
        if not itens:
            self.status.configure(text="Nenhum item marcado.", text_color=AMBAR)
            return
        if not messagebox.askyesno(TITULO, f"Inativar {len(itens)} itens que saíram da tabela?\n\n"
                                           "Ficam inativos no Bling e indisponíveis na Tray (nada é apagado)."):
            return
        self.ocupado = True
        self.botao_aplicar.configure(state="disabled", text="Inativando...")

        def terminou(resultado, erro):
            self.ocupado = False
            self.botao_aplicar.configure(state="normal")
            self.trocar_visao()
            if erro:
                self.status.configure(text=f"Parou com erro: {erro}", text_color=VERMELHO)
                return
            ok, falhas = resultado
            for item in itens:
                if not any(item is f[0] for f in falhas):
                    item["bling_ativo"] = item["tray_ativo"] = False
                    self.marcados.pop(id(item), None)
            texto = f"{ok} itens inativados no Bling e na Tray."
            if falhas:
                texto += f" {len(falhas)} com erro (ex.: cód. {falhas[0][0]['codigo']}: {falhas[0][1][:120]})."
            self.status.configure(text=texto, text_color=AMBAR if falhas else VERDE)
            self.desenhar()

        self.app.em_segundo_plano(lambda: cadastro.inativar(itens, self.avisar), terminou)
