"""
Envio das mensagens da régua pelo WhatsApp Web, num navegador próprio controlado pelo Assistente.

- A sessão (o QR code lido uma vez) fica na pasta whatsapp_sessao, ao lado do programa.
- Ritmo de uso normal: intervalo aleatório entre mensagens, limite por dia e só em horário comercial.
- Modo teste (config.json -> whatsapp_envio.modo_teste): tudo vai para os números de teste, com a
  indicação de para quem iria. Nada é anotado como enviado ao fornecedor.
  Exceção: as categorias em whatsapp_envio.envio_real ("logistica", "fabrica") vão de verdade mesmo
  com o modo teste ligado; as demais ("fornecedores") seguem em teste.
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
    "envio_real": [],  # categorias que já vão de verdade no modo teste: "logistica", "fabrica", "fornecedores"
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
        time.sleep(3)  # as mensagens antigas carregam depois da caixa: não podem parecer a mensagem nova
        ja_na_tela = self.pagina.evaluate(IDS_DA_CONVERSA_JS)
        caixa.press("Enter")
        # A caixa esvazia na hora, com a mensagem ainda no relógio: fechar o navegador aí a faz falhar ("Ocorreu um
        # erro", em 30/10). Só conta como enviada quando o próprio WhatsApp marcar Enviada/Entregue/Lida.
        limite = time.time() + ESPERA_CONFIRMACAO_SEGUNDOS
        while time.time() < limite:
            estado = self.pagina.evaluate(ESTADO_DA_NOVA_JS, {"antes": ja_na_tela, "trecho": _trecho(texto)})
            if estado == "confirmada":
                time.sleep(2)  # dá tempo de o WhatsApp gravar o estado antes de o navegador fechar
                return True, "enviada"
            if estado == "erro":
                return False, "o WhatsApp mostrou erro no envio"
            time.sleep(1)
        return False, "sem confirmação do WhatsApp em 2 minutos (mensagem no relógio)"


ESPERA_CONFIRMACAO_SEGUNDOS = 120
IDS_DA_CONVERSA_JS = "() => Array.from(document.querySelectorAll('#main [data-id]')).map(e => e.getAttribute('data-id'))"
# Estado da mensagem nova (id que não estava na tela antes do Enter, com o começo do nosso texto):
# 'erro', 'confirmada' (rótulo de enviada, os mesmos do LER_CONVERSA_JS) ou 'pendente'.
ESTADO_DA_NOVA_JS = """({antes, trecho}) => {
  const limpar = t => (t || '').replace(/\\s+/g, ' ').trim();
  const rotulos = e => Array.from(e.querySelectorAll('[aria-label]')).map(a => a.getAttribute('aria-label').trim().toLowerCase());
  const novas = Array.from(document.querySelectorAll('#main [data-id]'))
    .filter(e => !antes.includes(e.getAttribute('data-id')) && limpar(e.innerText).includes(trecho));
  if (novas.some(e => rotulos(e).some(r => r.startsWith('ocorreu um erro') || r.startsWith('an error occurred')))) return 'erro';
  return novas.some(e => rotulos(e).some(r => /^(enviada|entregue|lida|sent|delivered|read)$/.test(r))) ? 'confirmada' : 'pendente';
}"""


def _trecho(texto):
    """Começo da mensagem, com os espaços como o navegador mostra, para reconhecê-la na conversa."""
    return " ".join(str(texto).split())[:40]


LER_CONVERSA_JS = """() => Array.from(document.querySelectorAll('#main [data-id]'))
  .filter(e => {  // recebida = sem 'Você:' e sem status de entrega (Enviada / Entregue / Lida), que só as nossas têm
    const id = e.getAttribute('data-id') || '';
    if (id.startsWith('true_')) return false;
    if (id.startsWith('false_')) return true;
    if (!e.querySelector('[data-pre-plain-text]')) return false;  // ainda não carregada na tela
    const rotulos = Array.from(e.querySelectorAll('[aria-label]')).map(a => a.getAttribute('aria-label').trim().toLowerCase());
    return !rotulos.some(r => /^(você|you):?$/.test(r) || /^(enviada|entregue|lida|pendente|sent|delivered|read|pending)$/.test(r));
  })
  .map(e => {
    const c = e.querySelector('[data-pre-plain-text]');
    const partes = Array.from(e.querySelectorAll('span.selectable-text')).map(s => s.innerText);
    return {id: e.getAttribute('data-id'), pre: c ? c.getAttribute('data-pre-plain-text') : '',
            texto: partes.length ? partes[partes.length - 1] : '', completo: e.innerText};
  })"""


def _quando(pre):
    """'[14:05, 27/10/2026] Nome: ' -> '2026-10-27 14:05:00' (ou '' se não reconhecer)."""
    import re
    achado = re.search(r"\[(\d{1,2}):(\d{2}),\s*(\d{1,2})/(\d{1,2})/(\d{4})\]", pre or "")
    if not achado:
        return ""
    h, mi, d, me, a = (int(x) for x in achado.groups())
    return f"{a:04d}-{me:02d}-{d:02d} {h:02d}:{mi:02d}:00"


def ler_respostas(numeros, aviso=print):
    """Lê as mensagens recebidas nas conversas com esses números ({número: 'Logística'}). Só lê, não envia.
    Devolve [{id, numero, quem, quando, texto, completo}]."""
    lidas = []
    with SessaoWhatsApp() as sessao:
        if not sessao.esperar_login():
            raise RuntimeError("WhatsApp desconectado (use 'Conectar WhatsApp')")
        for numero, quem in numeros.items():
            sessao.pagina.goto(f"{URL}/send?phone={numero}")
            limite = time.time() + 60
            while time.time() < limite and not sessao.pagina.locator(SEL_CAIXA).count():
                time.sleep(1)
            if not sessao.pagina.locator(SEL_CAIXA).count():
                aviso(f"ATENÇÃO: a conversa com {quem} não abriu para ler as respostas.")
                continue
            time.sleep(4)  # as mensagens carregam depois da caixa de texto
            for m in sessao.pagina.evaluate(LER_CONVERSA_JS):
                lidas.append({"id": m["id"], "numero": numero, "quem": quem, "quando": _quando(m["pre"]),
                              "texto": (m["texto"] or "").strip(), "completo": m["completo"] or ""})
            time.sleep(random.uniform(2, 5))
    return lidas


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


def categoria(m):
    """'logistica', 'fabrica' ou 'fornecedores'."""
    if m.get("tipo") == "logistica":
        return "logistica"
    return "fabrica" if m.get("fabrica") else "fornecedores"


def e_teste(m, c=None):
    """True se esta mensagem vai para os números de teste (e não para o destino real)."""
    c = c or cfg()
    if not c["modo_teste"]:
        return False
    if categoria(m) not in (c.get("envio_real") or []):
        return True
    # envio_real_desde: antes dessa data, e para embarques anteriores a ela (pendências antigas), segue em teste
    desde = c.get("envio_real_desde") or ""
    return bool(desde) and (date.today().isoformat() < desde or (m.get("embarque") or "9999") < desde)


def enviar_lote(mensagens, ao_enviar=None, aviso=print, real=False):
    """Envia as mensagens do dia. ao_enviar(mensagem) é chamado a cada envio real (para anotar como enviada).
    Devolve (enviadas, falhas), falhas = [(mensagem, motivo)] para irem ao envio manual.
    real=True (envio pedido por um clique na tela): vai para o destino de verdade, sem modo teste."""
    c = cfg()
    if not em_horario_comercial():
        return [], [(m, "fora do horário comercial") for m in mensagens]
    enviadas, falhas = [], []
    testes = _testes_de_hoje() if c["modo_teste"] else None
    numeros_teste = [n for n in (c["numeros_teste"] or []) if n]
    if real:
        c = {**c, "modo_teste": False}
    if not numeros_teste:
        falhas = [(m, "modo teste sem número de teste no config.json") for m in mensagens if e_teste(m, c)]
        mensagens = [m for m in mensagens if not e_teste(m, c)]
        if not mensagens:
            return [], falhas
    with SessaoWhatsApp() as sessao:
        if not sessao.esperar_login():
            return [], [(m, "WhatsApp desconectado (use 'Conectar WhatsApp')") for m in mensagens]
        for i, m in enumerate(mensagens):
            if len(enviadas) >= c["limite_diario"]:
                falhas.append((m, "limite de mensagens do dia atingido"))
                continue
            teste = e_teste(m, c)
            if teste:
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
                                        "teste" if teste else "real", destino,
                                        "enviada" if ok else "falhou", "" if ok else motivo)
                except Exception as erro:
                    aviso(f"ATENÇÃO: não consegui gravar o histórico do envio ({erro}).")
            if all(ok for ok, _ in resultados):
                enviadas.append(m)
                if teste:
                    _anotar_teste(testes, chave)
                elif ao_enviar:
                    ao_enviar(m)
                aviso(f"WhatsApp: {'[teste] ' if teste else ''}mensagem {_sobre(m)} enviada.")
            else:
                motivo = next(motivo for ok, motivo in resultados if not ok)
                falhas.append((m, motivo))
                aviso(f"ATENÇÃO: WhatsApp não enviou a mensagem {_sobre(m)} ({motivo}).")
            if i < len(mensagens) - 1:
                time.sleep(random.uniform(*c["intervalo_segundos"]))
    return enviadas, falhas
