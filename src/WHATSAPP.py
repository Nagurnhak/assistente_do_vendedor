"""
Envio das mensagens da régua pelo WhatsApp Web, num navegador próprio controlado pelo Assistente.

- A sessão (o QR code lido uma vez) fica na pasta whatsapp_sessao, ao lado do programa.
- Ritmo de uso normal: intervalo aleatório entre mensagens, limite por dia e só em horário comercial.
- Modo teste (config.json -> whatsapp_envio.modo_teste): tudo vai para os números de teste, com a
  indicação de para quem iria. Nada é anotado como enviado ao fornecedor.
- Qualquer falha (sessão caiu, número sem WhatsApp, tela mudou) devolve a mensagem para o envio manual.

Requer:  py -m pip install --user playwright  e  py -m playwright install chromium
"""

import json
import os
import random
import sys
import time
from datetime import date, datetime
from urllib.parse import quote

from configuracao import carregar_config, pasta_base

# No .exe (PyInstaller) o Playwright procura o navegador dentro do próprio programa; aponta para o
# Chromium instalado no computador por 'py -m playwright install chromium'.
if getattr(sys, "frozen", False):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "ms-playwright")

PASTA_SESSAO = os.path.join(pasta_base(), "whatsapp_sessao")
ARQUIVO_TESTE = os.path.join(pasta_base(), "whatsapp_teste.json")
URL = "https://web.whatsapp.com"

# Seletores do WhatsApp Web (mudam de vez em quando; ficam todos aqui para ajustar fácil)
SEL_LOGADO = "#side, #pane-side, div[aria-label='Lista de conversas'], div[aria-label='Chat list']"
SEL_QR = "canvas[aria-label*='QR'], canvas[aria-label*='Scan'], div[data-ref]"
SEL_CAIXA = "footer div[contenteditable='true']"
TEXTOS_NUMERO_INVALIDO = ("inválido", "invalido", "invalid", "não está no whatsapp", "isn't on whatsapp")

PADRAO = {
    "modo_teste": True,
    "numeros_teste": [],
    "envio_automatico": False,
    "horario": "09:00",
    "horario_limite": "18:00",
    "limite_diario": 40,
    "intervalo_segundos": [30, 90],
}


def cfg():
    try:
        dados = carregar_config().get("whatsapp_envio") or {}
    except Exception:
        dados = {}
    return {**PADRAO, **dados}


def em_horario_comercial(agora=None):
    agora = agora or datetime.now()
    c = cfg()
    inicio, fim = (datetime.strptime(c[h], "%H:%M").time() for h in ("horario", "horario_limite"))
    return agora.weekday() < 5 and inicio <= agora.time() <= fim


class SessaoWhatsApp:
    """Abre o navegador do Assistente com o WhatsApp Web (sessão salva). Use com 'with'."""

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        try:
            self.contexto = self._pw.chromium.launch_persistent_context(
                PASTA_SESSAO, headless=False, viewport={"width": 1100, "height": 760}, locale="pt-BR")
        except Exception as erro:
            self._pw.stop()  # não deixa o controlador do navegador preso em segundo plano
            raise RuntimeError(f"não consegui abrir o navegador do WhatsApp ({str(erro).splitlines()[0]})") from None
        self.pagina = self.contexto.pages[0] if self.contexto.pages else self.contexto.new_page()
        self.pagina.bring_to_front()
        return self

    def __exit__(self, *erro):
        try:
            self.contexto.close()
        finally:
            self._pw.stop()

    def esperar_login(self, espera_qr_segundos=0):
        """True se o WhatsApp Web estiver conectado. Com espera_qr_segundos, dá tempo de ler o QR code."""
        self.pagina.goto(URL)
        limite = time.time() + 45 + espera_qr_segundos
        while time.time() < limite:
            if self.pagina.locator(SEL_LOGADO).count():
                return True
            if self.pagina.locator(SEL_QR).count() and not espera_qr_segundos:
                return False  # pediu QR code: a sessão não está conectada
            time.sleep(1)
        return False

    def enviar(self, numero, texto):
        """Abre a conversa com o texto pronto e envia. Devolve (ok, motivo)."""
        self.pagina.goto(f"{URL}/send?phone={numero}&text={quote(texto)}")
        limite = time.time() + 60
        while time.time() < limite:
            if self.pagina.locator(SEL_CAIXA).count():
                break
            corpo = (self.pagina.locator("body").inner_text() or "").lower()
            if any(t in corpo for t in TEXTOS_NUMERO_INVALIDO):
                return False, "número sem WhatsApp"
            if self.pagina.locator(SEL_QR).count():
                return False, "WhatsApp desconectado (precisa ler o QR code)"
            time.sleep(1)
        else:
            return False, "a conversa não abriu (a tela do WhatsApp pode ter mudado)"
        caixa = self.pagina.locator(SEL_CAIXA).last
        time.sleep(random.uniform(1.5, 3.0))
        if not (caixa.inner_text() or "").strip():
            return False, "o texto não apareceu na conversa"
        caixa.press("Enter")
        limite = time.time() + 20
        while time.time() < limite:  # a caixa esvazia quando a mensagem sai
            if not (self.pagina.locator(SEL_CAIXA).last.inner_text() or "").strip():
                time.sleep(2)
                return True, "enviada"
            time.sleep(0.5)
        return False, "não consegui confirmar o envio"


def conectar(espera_segundos=180):
    """Abre o WhatsApp Web para ler o QR code com o celular do número de compras."""
    with SessaoWhatsApp() as sessao:
        return sessao.esperar_login(espera_qr_segundos=espera_segundos)


def _testes_de_hoje():
    try:
        with open(ARQUIVO_TESTE, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (FileNotFoundError, ValueError):
        dados = {}
    return dados if dados.get("dia") == date.today().isoformat() else {"dia": date.today().isoformat(), "chaves": []}


def _anotar_teste(dados, chave):
    dados["chaves"].append(chave)
    with open(ARQUIVO_TESTE, "w", encoding="utf-8") as f:
        json.dump(dados, f)


def _sobre(m):
    """'da OC 1234' ou 'da Logística (pedido 1002)'."""
    return f"da Logística (pedido {m.get('pedido')})" if m.get("tipo") == "logistica" else f"da OC {m['oc_numero']}"


def enviar_lote(mensagens, ao_enviar=None, aviso=print):
    """Envia as mensagens do dia. ao_enviar(mensagem) é chamado a cada envio real (para anotar como enviada).
    Devolve (enviadas, falhas), falhas = [(mensagem, motivo)] para irem ao envio manual."""
    c = cfg()
    if not em_horario_comercial():
        return [], [(m, "fora do horário comercial") for m in mensagens]
    enviadas, falhas = [], []
    testes = _testes_de_hoje() if c["modo_teste"] else None
    numeros_teste = [n for n in (c["numeros_teste"] or []) if n]
    if c["modo_teste"] and not numeros_teste:
        return [], [(m, "modo teste sem número de teste no config.json") for m in mensagens]
    with SessaoWhatsApp() as sessao:
        if not sessao.esperar_login():
            return [], [(m, "WhatsApp desconectado (use 'Conectar WhatsApp')") for m in mensagens]
        for i, m in enumerate(mensagens):
            if len(enviadas) >= c["limite_diario"]:
                falhas.append((m, "limite de mensagens do dia atingido"))
                continue
            if c["modo_teste"]:
                chave = f"{m['oc_id']}:{m['chave']}"
                if chave in testes["chaves"]:
                    continue
                destinos = numeros_teste
                texto = (f"[TESTE do Assistente · iria para {m['fornecedor_nome']} "
                         f"({m.get('whatsapp') or 'sem número'})]\n{m['texto']}")
            else:
                if not m.get("whatsapp"):
                    falhas.append((m, "sem WhatsApp no cadastro"))
                    continue
                destinos, texto = [m["whatsapp"]], m["texto"]
            resultados = []
            for destino in destinos:
                if resultados:
                    time.sleep(random.uniform(*c["intervalo_segundos"]))
                ok, motivo = sessao.enviar(destino, texto)
                resultados.append((ok, motivo))
                try:  # histórico permanente de envios (aparece na tela Mensagens -> Histórico)
                    from ferramentas_internas import registrar_historico
                    registrar_historico({**m, "texto": texto}, "WhatsApp automático",
                                        "teste" if c["modo_teste"] else "real", destino,
                                        "enviada" if ok else "falhou", "" if ok else motivo)
                except Exception as erro:
                    aviso(f"ATENÇÃO: não consegui gravar o histórico do envio ({erro}).")
            if all(ok for ok, _ in resultados):
                enviadas.append(m)
                if c["modo_teste"]:
                    _anotar_teste(testes, chave)
                elif ao_enviar:
                    ao_enviar(m)
                aviso(f"WhatsApp: {'[teste] ' if c['modo_teste'] else ''}mensagem {_sobre(m)} enviada.")
            else:
                motivo = next(motivo for ok, motivo in resultados if not ok)
                falhas.append((m, motivo))
                aviso(f"ATENÇÃO: WhatsApp não enviou a mensagem {_sobre(m)} ({motivo}).")
            if i < len(mensagens) - 1:
                time.sleep(random.uniform(*c["intervalo_segundos"]))
    return enviadas, falhas
