"""Cores, fontes, ponte print()/input() e componentes comuns das telas do Assistente."""

import os
import queue
import re
import sys
import threading

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


def _moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _numero(texto, padrao=0.0):
    texto = str(texto or "").strip().replace("R$", "").replace(" ", "")
    if not texto:
        return padrao
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    return float(texto)
