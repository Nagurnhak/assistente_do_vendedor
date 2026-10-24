"""
Modo demonstração: simula Bling, Trello, Tray e WhatsApp com dados FICTÍCIOS, em memória.

Nada aqui acessa a internet nem lê credenciais: a loja, os clientes, os fornecedores, os produtos
e os pedidos são inventados. Serve para qualquer pessoa testar o fluxo completo
(prazos de frete, OCs, fichas, cards, checklists, status e mensagens) sem contas nas plataformas.
Os arquivos de trabalho (acompanhamento, mensagens, histórico) vão para uma pasta temporária.

Pedidos de exemplo (número da Tray):
    1001  2x Cadeira Lina                        -> "tem em estoque"; cliente na região local (frete de 1 dia)
    1002  Mesa Aurora (estruturada) + 4 cadeiras -> tampo da fábrica + base de fornecedor; frete pela tabela
    1003  Aparador Sol (fábrica) + Espelho       -> bom para personalização; destino sem tabela (regra anterior)
Na lista A Separar já há dois cards de outros pedidos (um a 2 dias úteis do embarque e um atrasado),
para mostrar a medição da lista e os lembretes à Logística.
"""

import copy
import os
import re
import sys
import tempfile
import time
from datetime import date, timedelta

ATRASO = 0.25  # segundos por chamada, só para parecer uma API de verdade

LOJA = "Loja Exemplo"
FABRICA = "Fábrica Própria Exemplo Ltda"
ID_FABRICA = 900

CONFIG = {
    "trello": {
        "key": "demo",
        "token": "demo",
        "lista_logistica_id": "lista-logistica",
        "listas_fabrica": [
            {"nome": "Marcenaria: Corte", "id": "lista-corte"},
            {"nome": "Marcenaria: Montagem", "id": "lista-montagem"},
            {"nome": "Pintura e acabamento", "id": "lista-pintura"},
        ],
    },
    "fabrica": {"nome": FABRICA, "identificador": "Fábrica Própria", "contato_id": ID_FABRICA},
    "loja": {"nome": LOJA, "sufixo_nos_produtos": LOJA},
    "compras": {"status_tray": ["A Enviar", "Liberado"]},
    "prazo_transporte_dias_uteis": 5,
    "prazos_frete": {
        "regiao_local": {"nome": "Região local", "uf": "SP", "cep_inicio": "01000000", "cep_fim": "09999999", "dias": 1},
        "transportadoras": [{"chave": "rapida", "nome": "Transportadora Rápida", "tipo": "cidade"}],
    },
    "whatsapp_logistica": "11900000000",
}

# Tabela de frete fictícia (no uso real ela vem das planilhas das transportadoras: prazos_frete.py)
PRAZOS_FRETE = {"transportadoras": {"rapida": {"tipo": "cidade", "pj": {"SP|CAMPINAS": 3}, "pf": {"SP|CAMPINAS": 4}}}}

FORNECEDORES = {
    ID_FABRICA: FABRICA,
    701: "Estofados Horizonte",
    702: "Metalúrgica Aurora",
    703: "Vidraçaria Cristal",
}


def _produto(id_, codigo, nome, fornecedor_id, custo, componentes=None):
    produto = {
        "id": id_, "codigo": codigo, "nome": nome, "formato": "E" if componentes else "S",
        "precoCusto": custo,
        "fornecedor": {"id": 3000 + id_, "codigo": f"F-{codigo}",
                       "contato": {"id": fornecedor_id, "nome": FORNECEDORES[fornecedor_id]}, "precoCusto": custo},
    }
    if componentes:
        produto["estrutura"] = {"componentes": [{"produto": {"id": c}, "quantidade": q} for c, q in componentes]}
    return produto


PRODUTOS = {p["id"]: p for p in [
    _produto(501, "CAD-LINA", f"Cadeira Lina - {LOJA} Cor:Grafite", 701, 320.0),
    _produto(502, "MESA-AURORA", f"Mesa de Jantar Aurora 1,60m - {LOJA}", ID_FABRICA, 0.0,
             componentes=[(503, 1), (504, 1)]),
    _produto(503, "TAMPO-AURORA", "Tampo Aurora 1,60m", ID_FABRICA, 850.0),
    _produto(504, "BASE-AURORA", "Base Aurora Aço Preto", 702, 410.0),
    _produto(505, "APARADOR-SOL", f"Aparador Sol - {LOJA} Cor:Natural", ID_FABRICA, 690.0),
    _produto(506, "ESPELHO-80", "Espelho Redondo 80cm", 703, 180.0),
]}
# como cada fornecedor chama o produto (vínculo produto x fornecedor no Bling)
VINCULOS = {3000 + p["id"]: {"codigo": f"F-{p['codigo']}", "descricao": p["nome"].split(" - ")[0].upper()}
            for p in PRODUTOS.values()}


def _item(produto_id, quantidade):
    p = PRODUTOS[produto_id]
    return {"codigo": p["codigo"], "descricao": p["nome"], "quantidade": quantidade, "produto": {"id": produto_id}}


def _pedido(id_, numero_loja, itens, transportadora="", servico=""):
    return {
        "id": id_, "numero": id_ - 10000, "numeroLoja": numero_loja, "data": date.today().isoformat(),
        "situacao": {"id": 6}, "itens": itens,
        "transporte": {"contato": {"id": 1 if transportadora else 0, "nome": transportadora},
                       "volumes": [{"servico": servico}] if servico else []},
    }


PEDIDOS = {p["id"]: p for p in [
    _pedido(10001, "1001", [_item(501, 2)], "Transportadora Rápida Ltda"),
    _pedido(10002, "1002", [_item(502, 1), _item(501, 4)], servico="Rápida Standard"),
    _pedido(10003, "1003", [_item(505, 1), _item(506, 1)], "Retirada na loja"),
]}

SITUACOES_VENDA = [
    {"id": 6, "nome": "Em aberto"}, {"id": 9, "nome": "Atendido"}, {"id": 15, "nome": "Em andamento"},
    {"id": 101, "nome": "Em separação"}, {"id": 102, "nome": "OC enviada"},
]


# ---------------------------------------------------------------------------
# Pedidos na Tray (formato do /orders/{n}/complete), com clientes fictícios
# ---------------------------------------------------------------------------

def _vendido(produto_id, quantidade, variacao=""):
    p = PRODUTOS[produto_id]
    nome = p["nome"].split(" - ")[0] + (f"<br><strong>Cor</strong> {variacao}" if variacao else "")
    imagem = [{"https": f"demo://{p['codigo']}"}]  # foto desenhada pela própria demonstração (foto())
    return {"ProductsSold": {"name": nome, "quantity": quantidade, "reference": p["codigo"], "ProductSoldImage": imagem}}


def _pedido_tray(numero, cliente, endereco, vendidos, frete, pagamento, total, dias_entrega=30, nota=""):
    rua, numero_rua, bairro, cidade, uf, cep = endereco
    return {
        "id": numero, "date": date.today().isoformat(), "status": "A Enviar",
        "estimated_delivery_date": (date.today() + timedelta(days=dias_entrega)).isoformat(),
        "shipment": frete, "payment_method": pagamento, "customer_note": nota, "store_note": "", "total": total,
        "Customer": {"name": cliente, "cellphone": "(11) 90000-0000", "cnpj": "",
                     "CustomerAddresses": [{"CustomerAddress": {
                         "type_delivery": "1", "address": rua, "number": numero_rua, "neighborhood": bairro,
                         "city": cidade, "state": uf, "zip_code": cep, "recipient": cliente}}]},
        "ProductsSold": vendidos,
    }


PEDIDOS_TRAY = {p["id"]: p for p in [
    _pedido_tray("1001", "Cliente Exemplo Um", ("Rua das Flores", "100", "Centro", "São Paulo", "SP", "01001000"),
                 [_vendido(501, 2, "Grafite")], "Transportadora Rápida", "Pix", "1290.00"),
    _pedido_tray("1002", "Cliente Exemplo Dois", ("Avenida Brasil", "2000", "Jardim", "Campinas", "SP", "13000000"),
                 [_vendido(502, 1), _vendido(501, 4, "Grafite")], "Transportadora Rápida", "Cartão de crédito", "6480.00",
                 nota="Entregar em horário comercial."),
    _pedido_tray("1003", "Cliente Exemplo Três", ("Rua do Porto", "5", "Centro", "Recife", "PE", "50000000"),
                 [_vendido(505, 1, "Natural"), _vendido(506, 1)], "Retirada na loja", "Boleto", "2350.00"),
]}

# O que a demonstração "criou" (fica só na memória enquanto o programa está aberto)
OCS, CARDS, OBSERVACOES_TRAY, STATUS_TRAY = {}, [], {}, {}
_proximo_numero_oc = [5001]
_contador = [0]


def _novo_id(prefixo):
    _contador[0] += 1
    return f"{prefixo}-{_contador[0]}"


def _nome_situacao(id_):
    return next((s["nome"] for s in SITUACOES_VENDA if s["id"] == id_), str(id_))


# arquivos de trabalho (acompanhamento, mensagens, histórico) numa pasta temporária, não na do programa
PASTA_DEMO = tempfile.mkdtemp(prefix="assistente_demo_")
try:
    import configuracao

    configuracao.pasta_base = lambda: PASTA_DEMO
except ImportError:
    pass


# ---------------------------------------------------------------------------
# BLING (simulado)
# ---------------------------------------------------------------------------

def chamar_bling(metodo, caminho, params=None, json=None, **_):
    time.sleep(ATRASO)
    params = params or {}

    if metodo == "GET" and caminho == "/pedidos/vendas":
        lista = list(PEDIDOS.values())
        numero = params.get("numerosLojas[]")
        if numero:
            lista = [p for p in lista if p["numeroLoja"] == str(numero).strip()]
        resumo = [{k: p[k] for k in ("id", "numero", "numeroLoja", "data", "situacao")} for p in lista]
        return {"data": resumo[: int(params.get("limite", 100))]}

    achado = re.fullmatch(r"/pedidos/vendas/(\d+)", caminho)
    if metodo == "GET" and achado and int(achado.group(1)) in PEDIDOS:
        return {"data": copy.deepcopy(PEDIDOS[int(achado.group(1))])}

    achado = re.fullmatch(r"/pedidos/vendas/(\d+)/situacoes/(\d+)", caminho)
    if metodo == "PATCH" and achado:
        PEDIDOS[int(achado.group(1))]["situacao"] = {"id": int(achado.group(2))}
        print(f"[demonstração] Bling: pedido agora está em '{_nome_situacao(int(achado.group(2)))}'.")
        return {}

    achado = re.fullmatch(r"/produtos/(\d+)", caminho)
    if metodo == "GET" and achado and int(achado.group(1)) in PRODUTOS:
        return {"data": copy.deepcopy(PRODUTOS[int(achado.group(1))])}

    achado = re.fullmatch(r"/produtos/estruturas/(\d+)", caminho)
    if metodo == "GET" and achado and int(achado.group(1)) in PRODUTOS:
        return {"data": copy.deepcopy(PRODUTOS[int(achado.group(1))].get("estrutura", {}))}

    achado = re.fullmatch(r"/produtos/fornecedores/(\d+)", caminho)
    if metodo == "GET" and achado and int(achado.group(1)) in VINCULOS:
        return {"data": dict(VINCULOS[int(achado.group(1))])}

    if metodo == "GET" and caminho == "/situacoes/modulos":
        return {"data": [{"id": 98, "nome": "Vendas"}, {"id": 99, "nome": "PedidosCompra"}]}
    if metodo == "GET" and caminho == "/situacoes/modulos/98":
        return {"data": copy.deepcopy(SITUACOES_VENDA)}

    if metodo == "GET" and caminho == "/contatos":
        return {"data": [{"id": ID_FABRICA, "nome": FABRICA}]}

    achado = re.fullmatch(r"/contatos/(\d+)", caminho)
    if metodo == "GET" and achado and int(achado.group(1)) in FORNECEDORES:
        id_ = int(achado.group(1))
        return {"data": {"id": id_, "nome": FORNECEDORES[id_], "situacao": "A", "email": f"contato{id_}@exemplo.com",
                         "celular": f"(11) 90000-{id_:04d}"}}

    if metodo == "POST" and caminho == "/pedidos/compras":
        id_oc = 80000 + len(OCS) + 1
        numero = _proximo_numero_oc[0]
        _proximo_numero_oc[0] += 1
        OCS[id_oc] = {"id": id_oc, "numero": numero, "situacao": {"valor": 0}, **copy.deepcopy(json or {})}
        fornecedor = FORNECEDORES.get((json or {}).get("fornecedor", {}).get("id"), "?")
        print(f"[demonstração] Bling: OC Nº {numero} registrada para {fornecedor} (só na memória).")
        return {"data": {"id": id_oc}}

    achado = re.fullmatch(r"/pedidos/compras/(\d+)", caminho)
    if metodo == "GET" and achado and int(achado.group(1)) in OCS:
        return {"data": copy.deepcopy(OCS[int(achado.group(1))])}

    raise RuntimeError(f"[demonstração] Esta chamada não existe na simulação: {metodo} {caminho}")


# ---------------------------------------------------------------------------
# TRELLO (simulado)
# ---------------------------------------------------------------------------

QUADRO = "quadro-demo"
ETIQUETAS = []


def _nome_lista(lista_id):
    if lista_id == CONFIG["trello"]["lista_logistica_id"]:
        return "Logística"
    return next((l["nome"] for l in CONFIG["trello"]["listas_fabrica"] if l["id"] == lista_id), lista_id)


def _dia_util(dia, passos):
    """Anda `passos` dias úteis (negativo = para trás), pulando fim de semana."""
    passo = 1 if passos >= 0 else -1
    for _ in range(abs(passos)):
        dia += timedelta(days=passo)
        while dia.weekday() >= 5:
            dia += timedelta(days=passo)
    return dia


def _card(lista_id, nome, prazo=None, descricao=None, dias_atras=0):
    _contador[0] += 1  # como no Trello, o id começa com a data de criação (em hexadecimal)
    criado = int(time.time()) - dias_atras * 86400
    card = {"id": f"{criado:08x}{_contador[0]:016x}", "idList": lista_id, "lista": _nome_lista(lista_id), "nome": nome, "name": nome,
            "prazo": (prazo or "")[:10], "due": prazo, "dueComplete": False, "closed": False, "pos": len(CARDS),
            "descricao": descricao, "anexos": [], "checklists": [], "idLabels": [], "idBoard": QUADRO}
    card["shortUrl"] = f"(card de demonstração {len(CARDS) + 1})"
    CARDS.append(card)
    return card


def _cards_iniciais():
    """Dois cards de pedidos anteriores já em A Separar: um a 2 dias úteis do embarque e um atrasado."""
    lista = CONFIG["trello"]["lista_logistica_id"]
    hoje = date.today()
    _card(lista, "Pedido 0998 - 1x Sofá Brisa 3 lugares (Estoque) - Transportadora Rápida",
          f"{_dia_util(hoje, 2).isoformat()}T12:00:00.000Z")
    _card(lista, "Pedido 0995 - 2x Poltrona Duna (OC 4990) - Transportadora Rápida",
          f"{_dia_util(hoje, -3).isoformat()}T12:00:00.000Z", dias_atras=8)


_cards_iniciais()
_INICIAIS = len(CARDS)


def _achar_card(card_id):
    card = next((c for c in CARDS if c["id"] == card_id), None)
    if card is None:
        raise RuntimeError(f"O Trello recusou: erro 404 - card {card_id} não existe na demonstração")
    return card


def criar_card(lista_id, nome_card, data_limite_iso=None, descricao=None):
    time.sleep(ATRASO)
    card = _card(lista_id, nome_card, data_limite_iso, descricao)
    prazo = f" | prazo {data_limite_iso[:10]}" if data_limite_iso else ""
    print(f"[demonstração] Trello: card '{nome_card}' na lista '{_nome_lista(lista_id)}'{prazo}.")
    return card["id"], card["shortUrl"]


def anexar_imagem(card_id, conteudo_imagem, nome_arquivo):
    """Guarda a ficha no card e salva uma cópia em PASTA_DEMO/fichas, para abrir e ver como ficou."""
    card = _achar_card(card_id)
    card["anexos"].append(nome_arquivo)
    card.setdefault("imagens", {})[nome_arquivo] = conteudo_imagem
    pasta = os.path.join(PASTA_DEMO, "fichas")
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome_arquivo)
    with open(caminho, "wb") as f:
        f.write(conteudo_imagem)
    print(f"[demonstração] Trello: anexo '{nome_arquivo}' no card (cópia para ver: {caminho}).")


def trello(metodo, caminho, params=None, data=None, **_):
    """As chamadas do Trello que o Assistente usa (checklists, etiquetas, lista A Separar)."""
    data = data or {}
    partes = caminho.strip("/").split("/")
    if metodo == "POST" and len(partes) == 3 and partes[0] == "cards" and partes[2] == "checklists":
        checklist = {"id": _novo_id("checklist"), "name": data.get("name", ""), "checkItems": []}
        _achar_card(partes[1])["checklists"].append(checklist)
        return dict(checklist)
    if metodo == "POST" and len(partes) == 3 and partes[0] == "checklists":
        for card in CARDS:
            for checklist in card["checklists"]:
                if checklist["id"] == partes[1]:
                    item = {"id": _novo_id("item"), "name": data.get("name", ""), "state": "incomplete"}
                    checklist["checkItems"].append(item)
                    return dict(item)
    if metodo == "PUT" and len(partes) == 4 and partes[2] == "checkItem":
        for checklist in _achar_card(partes[1])["checklists"]:
            for item in checklist["checkItems"]:
                if item["id"] == partes[3]:
                    item["name"] = data.get("name", item["name"])
        return {}
    if metodo == "GET" and len(partes) == 2 and partes[0] == "cards":
        return copy.deepcopy(_achar_card(partes[1]))
    if metodo == "GET" and len(partes) == 3 and partes[0] == "cards" and partes[2] == "actions":
        return []  # sem histórico: vale a data de criação (no id dos cards de verdade)
    if metodo == "PUT" and len(partes) == 2 and partes[0] == "cards":
        card = _achar_card(partes[1])
        if data.get("pos") == "top":
            card["pos"] = min(c["pos"] for c in CARDS) - 1
        return {}
    if metodo == "GET" and len(partes) == 2 and partes[0] == "lists":
        return {"id": partes[1], "idBoard": QUADRO}
    if metodo == "GET" and len(partes) == 3 and partes[0] == "lists" and partes[2] == "cards":
        cards = sorted((c for c in CARDS if c["idList"] == partes[1] and not c["closed"]), key=lambda c: c["pos"])
        return copy.deepcopy(cards)
    if metodo == "GET" and len(partes) == 3 and partes[0] == "boards" and partes[2] == "labels":
        return copy.deepcopy(ETIQUETAS)
    if metodo == "GET" and len(partes) == 3 and partes[0] == "boards" and partes[2] == "cards":
        return [{"id": c["id"], "idList": c["idList"], "idLabels": list(c["idLabels"])} for c in CARDS]
    if metodo == "POST" and partes == ["labels"]:
        etiqueta = {"id": _novo_id("etiqueta"), "name": data.get("name"), "color": data.get("color")}
        ETIQUETAS.append(etiqueta)
        return dict(etiqueta)
    if metodo == "POST" and len(partes) == 3 and partes[2] == "idLabels":
        etiquetas = _achar_card(partes[1])["idLabels"]
        if data.get("value") not in etiquetas:
            etiquetas.append(data.get("value"))
        return []
    if metodo == "DELETE" and len(partes) == 4 and partes[2] == "idLabels":
        card = _achar_card(partes[1])
        card["idLabels"] = [e for e in card["idLabels"] if e != partes[3]]
        return []
    raise RuntimeError(f"[demonstração] Esta chamada do Trello não existe na simulação: {metodo} {caminho}")


def print_simulado():
    """No lugar do print real (área de transferência), uma imagem vazia."""
    return b"\x89PNG demonstracao"


# Fotos fictícias: desenhadas aqui mesmo (Pillow), nada é baixado. Cada produto tem o seu desenho.
_FOTOS = {"CAD-LINA": "cadeira", "MESA-AURORA": "mesa", "TAMPO-AURORA": "mesa", "BASE-AURORA": "mesa",
          "APARADOR-SOL": "aparador", "ESPELHO-80": "espelho"}
_cache_fotos = {}


def _desenho(tipo, lado=480):
    from io import BytesIO
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (lado, lado), "#F4EFEA")
    d = ImageDraw.Draw(img)
    u = lado / 100  # desenho em uma grade de 100 x 100
    r = lambda *c: [v * u for v in c]
    d.ellipse(r(14, 84, 86, 92), fill="#E3D9CF")  # sombra no chão
    madeira, escura, metal = "#B07A4A", "#8A5A33", "#2F2F33"
    if tipo == "mesa":
        d.rounded_rectangle(r(10, 34, 90, 42), radius=2 * u, fill=madeira)
        d.rectangle(r(10, 40, 90, 42), fill=escura)
        d.polygon([(46 * u, 42 * u), (54 * u, 42 * u), (52 * u, 80 * u), (48 * u, 80 * u)], fill=metal)
        d.rounded_rectangle(r(32, 79, 68, 84), radius=2 * u, fill=metal)
    elif tipo == "cadeira":
        d.rounded_rectangle(r(30, 14, 70, 50), radius=8 * u, fill="#5B5E66")
        d.rounded_rectangle(r(26, 48, 74, 58), radius=4 * u, fill="#4A4D55")
        for x1, x2 in ((30, 26), (70, 74)):
            d.line([(x1 * u, 57 * u), (x2 * u, 86 * u)], fill=metal, width=int(2.4 * u))
        for x1, x2 in ((40, 38), (60, 62)):
            d.line([(x1 * u, 57 * u), (x2 * u, 83 * u)], fill=metal, width=int(2 * u))
    elif tipo == "aparador":
        d.rounded_rectangle(r(8, 34, 92, 72), radius=2 * u, fill="#C9A57A")
        for x in (8, 36, 64):
            d.rectangle(r(x + 2, 38, x + 26, 68), outline="#A9845B", width=int(u))
            d.ellipse(r(x + 13, 52, x + 15, 54), fill=escura)
        for x in (14, 84):
            d.rectangle(r(x, 72, x + 2, 86), fill=escura)
    else:  # espelho redondo
        d.ellipse(r(18, 10, 82, 74), fill="#C8A24A")
        d.ellipse(r(22, 14, 78, 70), fill="#CFE3EA")
        d.line([(34 * u, 30 * u), (46 * u, 22 * u)], fill="white", width=int(2 * u))
        d.line([(36 * u, 38 * u), (54 * u, 25 * u)], fill="white", width=int(1.2 * u))
    saida = BytesIO()
    img.save(saida, format="PNG")
    return saida.getvalue()


def foto(url):
    """Foto do produto: na demonstração, um desenho fictício (None se o Pillow não estiver instalado)."""
    codigo = str(url or "").replace("demo://", "")
    if codigo not in _cache_fotos:
        try:
            _cache_fotos[codigo] = _desenho(_FOTOS.get(codigo, "mesa"))
        except Exception:
            _cache_fotos[codigo] = None
    return _cache_fotos[codigo]


# ---------------------------------------------------------------------------
# TRAY (simulada)
# ---------------------------------------------------------------------------

class _TrayFalsa:
    @staticmethod
    def tray_configurada():
        return True

    @staticmethod
    def campo_observacao():
        return "store_note"

    @staticmethod
    def obter_pedido(numero):
        return copy.deepcopy(PEDIDOS_TRAY.get(str(numero), {}))

    @staticmethod
    def pedido_completo(numero):
        return copy.deepcopy(PEDIDOS_TRAY.get(str(numero), {}))

    @staticmethod
    def _itens(numero):
        itens = []
        for vendido in PEDIDOS_TRAY.get(str(numero), {}).get("ProductsSold") or []:
            v = vendido["ProductsSold"]
            itens.append({"nome": v["name"], "quantidade": v["quantity"], "referencia": v["reference"]})
        return itens

    @classmethod
    def itens_vendidos(cls, numero):
        return cls._itens(numero)

    @classmethod
    def detalhes_pedido(cls, numero):
        return {"itens": cls._itens(numero), "observacao": PEDIDOS_TRAY.get(str(numero), {}).get("store_note", "")}

    @staticmethod
    def entrega_prevista(numero):
        return PEDIDOS_TRAY.get(str(numero), {}).get("estimated_delivery_date")

    @staticmethod
    def pedidos_por_status(nomes_status):
        alvo = {n.lower() for n in nomes_status}
        return [{"numero": p["id"], "data": p["date"], "status": STATUS_TRAY.get(p["id"], p["status"]),
                 "total": p.get("total", "0.00"), "entrega": p["estimated_delivery_date"]}
                for p in PEDIDOS_TRAY.values() if STATUS_TRAY.get(p["id"], p["status"]).lower() in alvo]

    @staticmethod
    def adicionar_observacao(numero, texto):
        notas = OBSERVACOES_TRAY.setdefault(str(numero), [])
        if texto in notas:
            return False
        notas.append(texto)
        return True

    @staticmethod
    def atualizar_observacao_gerenciada(numero, partes):
        from notas_compras import atualizar_html
        pedido = PEDIDOS_TRAY.get(str(numero))
        if pedido is None:
            return False
        novo = atualizar_html(pedido.get("store_note") or "", partes)
        if novo == pedido.get("store_note"):
            return False
        pedido["store_note"] = novo
        OBSERVACOES_TRAY.setdefault(str(numero), []).append(novo)
        print(f"[demonstração] Tray: observação do pedido {numero} atualizada.")
        return True

    @staticmethod
    def mudar_status(numero, nome_status):
        STATUS_TRAY[str(numero)] = nome_status


TRAY_FALSA = _TrayFalsa()


# ---------------------------------------------------------------------------
# WHATSAPP (simulado): as mensagens do dia são "enviadas" só no histórico, nada sai do computador
# ---------------------------------------------------------------------------

class _WhatsappFalso:
    @staticmethod
    def cfg():
        return {"modo_teste": True, "numeros_teste": ["demonstração"], "envio_automatico": False,
                "horario": "09:00", "horario_limite": "18:00", "limite_diario": 40}

    @staticmethod
    def em_horario_comercial(agora=None):
        return True

    @staticmethod
    def conectar(_tempo=None):
        print("[demonstração] WhatsApp: conexão simulada.")
        return True

    @staticmethod
    def enviar_lote(mensagens, ao_enviar=None, aviso=print):
        from ferramentas_internas import registrar_historico
        for m in mensagens:
            registrar_historico(m, "WhatsApp (demonstração)", "teste", m.get("whatsapp"), "enviada",
                                "simulado: nada foi enviado")
        aviso(f"[demonstração] WhatsApp: {len(mensagens)} mensagem(ns) simulada(s).")
        return list(mensagens), []


sys.modules["WHATSAPP"] = _WhatsappFalso()


def resumo():
    """Texto com tudo o que a demonstração 'criou' até agora."""
    novos = CARDS[_INICIAIS:]
    linhas = [f"OCs: {len(OCS)} | Cards novos no Trello: {len(novos)} | Pedidos com observação na Tray: "
              f"{len(OBSERVACOES_TRAY)}"]
    for oc in OCS.values():
        linhas.append(f"  OC {oc['numero']} - {FORNECEDORES.get(oc['fornecedor']['id'], '?')} "
                      f"(prevista {oc.get('dataPrevista', '-')}): {oc.get('observacoes', '')}")
    for card in novos:
        anexos = f" | anexos: {', '.join(card['anexos'])}" if card["anexos"] else ""
        linhas.append(f"  Card [{card['lista']}] {card['nome']} | prazo {card['prazo'] or '-'}{anexos}")
    for numero, status in STATUS_TRAY.items():
        linhas.append(f"  Tray: pedido {numero} -> {status}")
    if any(card.get("imagens") for card in novos):
        linhas.append(f"  Fichas anexadas aos cards (abra para ver): {os.path.join(PASTA_DEMO, 'fichas')}")
    return "\n".join(linhas)
