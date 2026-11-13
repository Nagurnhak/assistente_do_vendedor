"""
Conferência de pedidos (tela "Conferência" do Assistente).

O vendedor escolhe o nome e vê os pedidos dele na Tray que estão em
"Mercadoria solicitada ao depósito central" ou "Pedido em separação", cada um com:
- os itens vendidos (nomes da Tray) e, quando dá para ligar pelo código, a OC de cada item;
- as OCs do pedido no Bling: atendida = já chegou; em aberto = prevista/atrasada, com botão para cobrar o fornecedor;
- a data do pedido, nesta ordem: observações do pedido na Tray (o que o vendedor/Assistente anotou),
  data do card no Trello (Logística), data de entrega da Tray.

De onde vêm as OCs de cada pedido (nada é criado aqui):
    observação da Tray (bloco do Assistente "parte:oc-<id>" e linhas "OC 1234"), nome do card no Trello
    ("(OC 5003)") e o acompanhamento_trello.json. Números sem id são procurados na lista de OCs do Bling.

Só leitura, menos duas ações que a tela pede com um clique:
    registrar_nova_previsao() -> uma linha nas observações do pedido na Tray (vira a data principal);
    mensagem_cobranca()       -> a mensagem que a janela manda pelo WhatsApp do Assistente.
"""

import re
import time
from datetime import date, datetime, timedelta
from html import unescape
from urllib.parse import quote

import TRAY
import ferramentas_internas as fi

STATUS_CONFERENCIA = ("MERCADORIA SOLICITADA AO DEPOSITO CENTRAL", "PEDIDO EM SEPARACAO")
ROTULO_STATUS = {"MERCADORIA SOLICITADA AO DEPOSITO CENTRAL": "Solicitada ao depósito",
                 "PEDIDO EM SEPARACAO": "Em separação"}
VALIDADE_CACHE = 5 * 60  # segundos: trocar de vendedor não lê a Tray de novo

_cache = {"quando": 0.0, "pedidos": None}
_cache_ocs = {}
_cache_fornecedores = {}


# ---------------------------------------------------------------------------
# DATAS
# ---------------------------------------------------------------------------

# "Nova previsão de entrega (vendedor, 29/10): 15/11/2026", "Nova previsão (Logística, WhatsApp 27/10): 15/11/2026",
# "Data prevista para entrega: 30/11/2026", "Previsão de entrega: 10/12/26"
_DATA_NA_OBS = re.compile(
    r"(nova\s+previs[aã]o[^:\n]*|data\s+prevista\s+para\s+entrega|previs[aã]o\s+de\s+entrega|entrega\s+prevista"
    r"|previs[aã]o)\s*:?\s*(\d{1,2})/(\d{1,2})/(\d{2,4})", re.IGNORECASE)


def vendedores():
    """[(id do parceiro na Tray, nome)]: config.json -> "vendedores" (os mesmos da tela Lançar pedido)."""
    return [(str(v["id"]), v["nome"].split()[0]) for v in fi.config().get("vendedores") or []]


def _padrao_pedido():
    """Como o número do pedido aparece no nome dos cards: config.json -> "padrao_numero_pedido"."""
    return fi.config().get("padrao_numero_pedido") or r"(?<!\d)(1\d{5})(?!\d)"


def texto_da_observacao(html):
    """Observação da Tray (HTML) em texto simples, uma linha por parágrafo/quebra."""
    texto = re.sub(r"(?i)<br\s*/?>|</p>", "\n", str(html or ""))
    texto = re.sub(r"<!--.*?-->|<[^>]+>", "", texto, flags=re.S)
    return "\n".join(" ".join(l.split()) for l in unescape(texto).splitlines() if l.strip())


def data_das_observacoes(html):
    """(data, rótulo) da previsão escrita nas observações, ou (None, ''). A última 'Nova previsão' manda;
    sem ela, a última 'Data prevista para entrega' / 'Previsão'."""
    achadas = []
    for m in _DATA_NA_OBS.finditer(texto_da_observacao(html)):
        ano = int(m[4]) + (2000 if len(m[4]) == 2 else 0)
        try:
            achadas.append((m[1].lower().startswith("nova"), m.start(), date(ano, int(m[3]), int(m[2])),
                            " ".join(m[1].split())))
        except ValueError:
            continue
    if not achadas:
        return None, ""
    _, _, data, rotulo = max(achadas)
    return data, rotulo


def _data_iso(texto):
    texto = str(texto or "")[:10]
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date() if not texto.startswith("0000") else None
    except ValueError:
        return None


def data_br(d):
    return d.strftime("%d/%m/%Y") if d else "—"


# ---------------------------------------------------------------------------
# TRAY, TRELLO E BLING
# ---------------------------------------------------------------------------

def _pedidos_tray(forcar=False):
    """Pedidos completos (cliente, itens, observação) nos status da conferência. Guardados por 5 minutos."""
    if not forcar and _cache["pedidos"] is not None and time.time() - _cache["quando"] < VALIDADE_CACHE:
        return _cache["pedidos"]
    pedidos = []
    for status in STATUS_CONFERENCIA:
        pagina = 1
        while True:
            dados = TRAY.chamar_tray("GET", "/orders", params={"status": status, "limit": 50, "page": pagina})
            for item in dados.get("Orders") or []:
                numero = str((item.get("Order") or item).get("id"))
                pedidos.append(TRAY.pedido_completo(numero))
            paginacao = dados.get("paging") or {}
            if pagina * int(paginacao.get("limit") or 50) >= int(paginacao.get("total") or 0):
                break
            pagina += 1
    _cache.update(quando=time.time(), pedidos=pedidos)
    return pedidos


def _cards_trello():
    """{número do pedido: card} do quadro da Logística (todas as listas). Sem Trello: {}."""
    try:
        lista = fi.config()["trello"]["lista_logistica_id"]
        quadro = fi._trello("GET", f"/lists/{lista}", params={"fields": "idBoard"})["idBoard"]
        nomes = {l["id"]: l["name"] for l in fi._trello("GET", f"/boards/{quadro}/lists", params={"fields": "name"})}
        cards = fi._trello("GET", f"/boards/{quadro}/cards", params={"fields": "name,due,dueComplete,idList,shortUrl"})
    except Exception as erro:
        print(f"Conferência: Trello não lido ({erro}).")
        return {}
    por_pedido = {}
    for card in cards:
        card["lista"] = nomes.get(card.get("idList"), "")
        for numero in re.findall(_padrao_pedido(), card.get("name") or ""):
            atual = por_pedido.get(numero)
            if atual is None or (card.get("due") and not atual.get("due")):
                por_pedido[numero] = card
    return por_pedido


# cards da fábrica: "OC 5003 (1002) - ...", "Ped. 5003 - ...", "Ped - 5003 L1002 - ..." (Ped. = número da OC)
_OC_NO_CARD = re.compile(r"\b(?:OC|Ped)\b[\s.:\-º°nN]*(\d{4,5})\b", re.IGNORECASE)


def _cards_fabrica():
    """Cards dos quadros da fábrica: ({número da OC: card}, {número do pedido: [cards]}). card['lista'] = etapa
    (a lista do Trello em que o card está, ex.: 'Marcenaria: Corte'). Sem Trello: ({}, {})."""
    por_oc, por_pedido = {}, {}
    try:
        quadros = {fi._trello("GET", f"/lists/{id_}", params={"fields": "idBoard"})["idBoard"]
                   for _, id_ in fi.listas_fabrica().values() if id_}
        for quadro in quadros:
            nomes = {l["id"]: l["name"] for l in fi._trello("GET", f"/boards/{quadro}/lists",
                                                            params={"fields": "name"})}
            for card in fi._trello("GET", f"/boards/{quadro}/cards",
                                   params={"fields": "name,due,dueComplete,idList,shortUrl"}):
                card["lista"] = " ".join(nomes.get(card.get("idList"), "").split())
                nome = card.get("name") or ""
                for numero in _OC_NO_CARD.findall(nome):
                    por_oc.setdefault(numero, card)
                for numero in re.findall(_padrao_pedido(), nome):
                    por_pedido.setdefault(numero, []).append(card)
    except Exception as erro:
        print(f"Conferência: quadro da fábrica não lido ({erro}).")
    return por_oc, por_pedido


_OC_ID = re.compile(r"parte:oc-(\d+)")
_OC_NUMERO = re.compile(r"\bOC\s*(?:N[ºo°]\s*)?(\d{4,})", re.IGNORECASE)


def _referencias_ocs(numero, observacao, card, registros):
    """(ids, números) das OCs ligadas ao pedido."""
    ids = set(_OC_ID.findall(observacao or ""))
    numeros = set(_OC_NUMERO.findall(texto_da_observacao(observacao)))
    numeros |= set(_OC_NUMERO.findall((card or {}).get("name") or ""))
    for registro in registros:
        if str(registro.get("pedido")) == numero:
            for item in registro.get("itens") or []:
                if item.get("oc_id"):
                    ids.add(str(item["oc_id"]))
    return ids, numeros


def _ids_pelos_numeros(numeros, desde):
    """{número da OC: id} pela lista de OCs do Bling (a partir da data 'desde'). Para quando achar todos."""
    faltam, achados, pagina = set(numeros), {}, 1
    while faltam and pagina <= 30:
        lista = fi.chamar_bling("GET", "/pedidos/compras", params={
            "dataInicial": desde.isoformat(), "dataFinal": date.today().isoformat(),
            "limite": 100, "pagina": pagina}).get("data", [])
        for oc in lista:
            if str(oc.get("numero")) in faltam:
                achados[str(oc["numero"])] = str(oc["id"])
                faltam.discard(str(oc["numero"]))
        if len(lista) < 100:
            break
        pagina += 1
    return achados


def _fornecedor(fornecedor_id):
    """(nome, whatsapp) do contato no Bling. WhatsApp: config.json (whatsapp_fornecedores / da fábrica) ou o
    celular/telefone do contato - a mesma regra da régua de mensagens."""
    chave = str(fornecedor_id or "")
    if chave not in _cache_fornecedores:
        try:
            contato = fi.chamar_bling("GET", f"/contatos/{chave}").get("data", {}) if chave else {}
        except Exception:
            contato = {}
        nome = contato.get("nome") or "Fornecedor"
        try:
            manual = (fi.config().get("whatsapp_fornecedores") or {}).get(chave)
        except Exception:
            manual = None
        numero = fi.normalizar_whatsapp(manual) if manual else ""
        if not numero and fi._oc_da_fabrica({"fornecedor_id": chave, "fornecedor_nome": nome}):
            numero = fi.whatsapp_da_fabrica()
        if not numero:
            numero = fi.normalizar_whatsapp(contato.get("celular")) or fi.normalizar_whatsapp(contato.get("telefone"))
        _cache_fornecedores[chave] = (nome, numero)
    return _cache_fornecedores[chave]


def _oc(oc_id, forcar=False):
    """A OC do Bling, resumida. None se não conseguir ler."""
    if forcar or oc_id not in _cache_ocs:
        try:
            oc = fi.chamar_bling("GET", f"/pedidos/compras/{oc_id}").get("data", {})
        except Exception as erro:
            print(f"Conferência: OC {oc_id} não lida no Bling ({erro}).")
            return None
        fornecedor_id = (oc.get("fornecedor") or {}).get("id")
        nome, whatsapp = _fornecedor(fornecedor_id)
        _cache_ocs[oc_id] = {
            "id": str(oc.get("id")), "numero": str(oc.get("numero")),
            "situacao": (oc.get("situacao") or {}).get("valor", 0),
            "prevista": _data_iso(oc.get("dataPrevista")), "fornecedor_id": fornecedor_id,
            "fornecedor_nome": nome, "fornecedor": fi.fornecedor_curto(nome), "whatsapp": whatsapp,
            "fabrica": fi._oc_da_fabrica({"fornecedor_id": fornecedor_id, "fornecedor_nome": nome}),
            "itens": [{"descricao": fi.nome_curto(i.get("descricao") or ""), "quantidade": i.get("quantidade") or 1,
                       "codigo": str((i.get("produto") or {}).get("codigo") or "").strip(),
                       "codigo_fornecedor": i.get("codigoFornecedor") or ""} for i in oc.get("itens") or []],
        }
    return _cache_ocs[oc_id]


def situacao_da_oc(oc, hoje=None):
    """('chegou' | 'cancelada' | 'atrasada' | 'aberta', texto)."""
    hoje = hoje or date.today()
    if oc.get("chegou_trello") or oc["situacao"] == 1:
        return "chegou", "Chegou" + (" (marcado no Trello)" if oc.get("chegou_trello") and oc["situacao"] != 1 else "")
    if oc["situacao"] == 2:
        return "cancelada", "Cancelada"
    if not oc["prevista"]:
        return "aberta", "Em aberto · sem data prevista"
    atraso = fi.dias_uteis_de_atraso(oc["prevista"], hoje)
    if atraso:
        return "atrasada", (f"Em aberto · prevista {oc['prevista']:%d/%m} · "
                            f"{atraso} {'dia útil' if atraso == 1 else 'dias úteis'} de atraso")
    return "aberta", f"Em aberto · prevista {oc['prevista']:%d/%m/%Y}"


# ---------------------------------------------------------------------------
# CONFERÊNCIA
# ---------------------------------------------------------------------------

def _cliente(pedido):
    c = pedido.get("Customer") or {}
    telefone = fi.normalizar_whatsapp(c.get("cellphone")) or fi.normalizar_whatsapp(c.get("phone"))
    return (c.get("name") or "").strip(), telefone


def conferir(parceiro_id, forcar=False, hoje=None):
    """Pedidos do vendedor nos status da conferência, do mais urgente para o mais folgado."""
    hoje = hoje or date.today()
    if forcar:
        _cache_ocs.clear()
    meus = [p for p in _pedidos_tray(forcar) if str(p.get("partner_id")) == str(parceiro_id)]
    if not meus:
        return []
    cards = _cards_trello()
    fabrica_oc, fabrica_pedido = _cards_fabrica()
    registros = fi.carregar_acompanhamento()
    chegou_trello = {str(i.get("oc_id")) for r in registros for i in r.get("itens") or []
                     if i.get("chegou_pelo_trello")}

    refs = {}
    for p in meus:
        numero = str(p.get("id"))
        refs[numero] = _referencias_ocs(numero, p.get(TRAY.campo_observacao()), cards.get(numero), registros)
    sem_id = {n for _, numeros in refs.values() for n in numeros}
    conhecidos = {o["numero"]: o["id"] for o in _cache_ocs.values() if o}
    if sem_id - set(conhecidos):
        desde = min(_data_iso(p.get("date")) or hoje for p in meus) - timedelta(days=7)
        try:
            conhecidos.update(_ids_pelos_numeros(sem_id - set(conhecidos), desde))
        except Exception as erro:
            print(f"Conferência: lista de OCs do Bling não lida ({erro}).")

    resultado = []
    for p in meus:
        numero = str(p.get("id"))
        ids, numeros = refs[numero]
        ids = set(ids) | {conhecidos[n] for n in numeros if n in conhecidos}
        ocs = []
        for oc_id in sorted(ids):
            oc = _oc(oc_id)
            if oc:
                oc = {**oc, "chegou_trello": oc["id"] in chegou_trello}
                oc["estado"], oc["texto"] = situacao_da_oc(oc, hoje)
                card_fab = fabrica_oc.get(oc["numero"])
                oc["etapa"] = card_fab["lista"] if card_fab else None
                oc["etapa_card"] = card_fab.get("shortUrl") if card_fab else None
                ocs.append(oc)
        lidos = {o["numero"] for o in ocs}
        # cards da fábrica com o número do pedido que não são de nenhuma OC listada (ex.: OC não anotada no pedido)
        com_oc = {o["etapa_card"] for o in ocs if o.get("etapa_card")}
        fabrica_extra = [{"nome": c.get("name") or "", "etapa": c["lista"], "card": c.get("shortUrl")}
                         for c in fabrica_pedido.get(numero, []) if c.get("shortUrl") not in com_oc]
        nao_achadas = sorted(n for n in numeros if n not in lidos)
        ocs.sort(key=lambda o: int(o["numero"]) if o["numero"].isdigit() else 0)

        itens = []
        for vendido in TRAY._itens_de(p):
            referencia = vendido["referencia"]
            oc_item = next((o for o in ocs for i in o["itens"] if referencia and i["codigo"] == referencia), None)
            itens.append({"texto": f"{fi.formatar_quantidade(vendido.get('quantidade') or 1)}x "
                                   f"{fi.limpar_nome_tray(vendido['nome'])}",
                          "oc": oc_item["numero"] if oc_item else None,
                          "estado": oc_item["estado"] if oc_item else None})

        card = cards.get(numero)
        pela_obs, rotulo_obs = data_das_observacoes(p.get(TRAY.campo_observacao()))
        pelo_trello = _data_iso((card or {}).get("due"))
        pela_tray = _data_iso(p.get("estimated_delivery_date"))
        if pela_tray and pela_tray == _data_iso(p.get("date")):  # a Tray repete a data da compra quando não calcula
            pela_tray = None
        fontes = [("Observações", pela_obs, rotulo_obs), ("Trello", pelo_trello, (card or {}).get("lista", "")),
                  ("Tray", pela_tray, "entrega prevista")]
        principal = next(((f, d, r) for f, d, r in fontes if d), (None, None, ""))
        cliente, telefone = _cliente(p)
        resultado.append({
            "numero": numero, "status": ROTULO_STATUS.get(fi.sem_acento(p.get("status") or "").upper(),
                                                          p.get("status") or ""),
            "data": _data_iso(p.get("date")), "cliente": cliente, "telefone": telefone,
            "itens": itens, "ocs": ocs, "ocs_nao_achadas": nao_achadas, "fabrica_extra": fabrica_extra,
            "previsao": principal[1], "fonte": principal[0], "fonte_detalhe": principal[2],
            "datas": [(f, d) for f, d, _ in fontes],
            "atrasado": bool(principal[1] and principal[1] < hoje),
            "card": card.get("shortUrl") if card else None,
        })
    resultado.sort(key=lambda r: (r["previsao"] is None, r["previsao"] or date.max, r["numero"]))
    return resultado


# ---------------------------------------------------------------------------
# AÇÕES (cada uma pedida por um clique na tela)
# ---------------------------------------------------------------------------

def registrar_nova_previsao(numero, nova, vendedor=""):
    """Anota a nova previsão nas observações do pedido na Tray (passa a ser a data principal)."""
    quem = f"vendedor {vendedor}".strip() if vendedor else "vendedor"
    texto = f"Nova previsão de entrega ({quem}, {date.today():%d/%m}): {nova:%d/%m/%Y}"
    TRAY.adicionar_observacao(str(numero), texto)
    for p in _cache["pedidos"] or []:  # a tela já mostra a data nova sem ler a Tray de novo
        if str(p.get("id")) == str(numero):
            campo = TRAY.campo_observacao()
            p[campo] = f"{p.get(campo) or ''}\n{texto}".strip()
    return texto


def mensagem_cobranca(pedido, oc, hoje=None):
    """Mensagem de cobrança da OC, no formato da régua (a janela envia com app.enviar_whatsapp)."""
    hoje = hoje or date.today()
    itens = "; ".join(f"{fi.formatar_quantidade(i['quantidade'])}x {i['descricao']}"
                      + (f" (cód. {i['codigo_fornecedor']})" if i.get("codigo_fornecedor") else "")
                      for i in oc["itens"]) or "itens da OC"
    if oc["prevista"]:
        atraso = fi.dias_uteis_de_atraso(oc["prevista"], hoje)
        prazo = (f"estava prevista para {oc['prevista']:%d/%m/%Y} e ainda não consta como recebida "
                 f"({atraso} {'dia útil' if atraso == 1 else 'dias úteis'} de atraso)" if atraso
                 else f"está prevista para {oc['prevista']:%d/%m/%Y}")
    else:
        prazo = "ainda não tem data prevista conosco"
    texto = (f"Olá, {oc['fornecedor']}! Tudo bem? Aqui é da {fi.nome_loja()}. A OC {oc['numero']} "
             f"(pedido {pedido['numero']}) {prazo}. Itens: {itens}. Pode nos passar a previsão de envio?")
    texto += fi.TEXTO_REFERENCIA.format(ref=f"#OC{oc['numero']}")
    return {"oc_id": oc["id"], "oc_numero": oc["numero"], "pedido": pedido["numero"],
            "fornecedor": oc["fornecedor"], "fornecedor_nome": oc["fornecedor_nome"], "whatsapp": oc["whatsapp"],
            "fabrica": oc["fabrica"], "etapa": "atraso", "rotulo": "Cobrança (Conferência)",
            "embarque": oc["prevista"].isoformat() if oc["prevista"] else None, "texto": texto,
            "chave": f"cobranca:{hoje.isoformat()}"}


def texto_aviso_cliente(pedido, vendedor, nova=None):
    """Mensagem ao cliente sobre o prazo (o vendedor revisa antes de mandar)."""
    nome = (pedido.get("cliente") or "").split()[0].title() if pedido.get("cliente") else ""
    data = nova or pedido.get("previsao")
    prazo = (f"a nova previsão de entrega é {data:%d/%m/%Y}" if data
             else "estamos confirmando a nova data com o fornecedor e te aviso assim que tiver")
    return (f"Olá{', ' + nome if nome else ''}! Tudo bem? Aqui é {vendedor}, da {fi.nome_loja()}. "
            f"Passando para atualizar sobre o seu pedido {pedido['numero']}: tivemos um ajuste no prazo do "
            f"fornecedor e {prazo}. Pedimos desculpas pelo transtorno; seguimos acompanhando de perto. "
            "Qualquer dúvida, estou à disposição!")


def link_whatsapp_cliente(telefone, texto):
    """Conversa com o cliente no WhatsApp do próprio vendedor (abre no navegador, com o texto pronto)."""
    return f"https://wa.me/{telefone}?text={quote(texto)}" if telefone else f"https://wa.me/?text={quote(texto)}"
