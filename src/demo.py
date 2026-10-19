"""
Modo demonstração: simula Bling, Trello e Tray com dados FICTÍCIOS, em memória.

Nada aqui acessa a internet nem lê credenciais: a loja, os fornecedores, os produtos
e os pedidos são inventados. Serve para qualquer pessoa testar o fluxo completo
(OCs, cards, status) sem precisar de contas nas plataformas.

Pedidos de exemplo (número da Tray):
    1001  2x Cadeira Lina                       -> bom para "tem em estoque"
    1002  Mesa Aurora (estruturada) + 4 cadeiras -> tampo da fábrica + base de fornecedor
    1003  Aparador Sol (fábrica) + Espelho       -> bom para testar personalização
"""

import copy
import re
import time
from datetime import date

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
    "loja": {"sufixo_nos_produtos": LOJA},
    "prazo_transporte_dias_uteis": 5,
}

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
        "fornecedor": {"contato": {"id": fornecedor_id, "nome": FORNECEDORES[fornecedor_id]},
                       "precoCusto": custo},
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

# O que a demonstração "criou" (fica só na memória enquanto o programa está aberto)
OCS, CARDS, OBSERVACOES_TRAY, STATUS_TRAY = {}, [], {}, {}
_proximo_numero_oc = [5001]


def _nome_situacao(id_):
    return next((s["nome"] for s in SITUACOES_VENDA if s["id"] == id_), str(id_))


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

    if metodo == "GET" and caminho == "/situacoes/modulos":
        return {"data": [{"id": 98, "nome": "Vendas"}, {"id": 99, "nome": "PedidosCompra"}]}
    if metodo == "GET" and caminho == "/situacoes/modulos/98":
        return {"data": copy.deepcopy(SITUACOES_VENDA)}

    if metodo == "GET" and caminho == "/contatos":
        return {"data": [{"id": ID_FABRICA, "nome": FABRICA}]}

    if metodo == "POST" and caminho == "/pedidos/compras":
        id_oc = 80000 + len(OCS) + 1
        numero = _proximo_numero_oc[0]
        _proximo_numero_oc[0] += 1
        OCS[id_oc] = {"numero": numero, **copy.deepcopy(json or {})}
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

def _nome_lista(lista_id):
    if lista_id == CONFIG["trello"]["lista_logistica_id"]:
        return "Logística"
    return next((l["nome"] for l in CONFIG["trello"]["listas_fabrica"] if l["id"] == lista_id), lista_id)


def criar_card(lista_id, nome_card, data_limite_iso=None, descricao=None):
    time.sleep(ATRASO)
    card_id = f"card-{len(CARDS) + 1}"
    CARDS.append({"id": card_id, "lista": _nome_lista(lista_id), "nome": nome_card,
                  "prazo": (data_limite_iso or "")[:10], "descricao": descricao, "anexos": []})
    prazo = f" | prazo {data_limite_iso[:10]}" if data_limite_iso else ""
    print(f"[demonstração] Trello: card '{nome_card}' na lista '{_nome_lista(lista_id)}'{prazo}.")
    return card_id, f"(card de demonstração {card_id})"


def anexar_imagem(card_id, conteudo_imagem, nome_arquivo):
    for card in CARDS:
        if card["id"] == card_id:
            card["anexos"].append(nome_arquivo)
    print(f"[demonstração] Trello: anexo '{nome_arquivo}' no {card_id}.")


def print_simulado():
    """No lugar do print real (área de transferência), uma imagem vazia."""
    return b"\x89PNG demonstracao"


# ---------------------------------------------------------------------------
# TRAY (simulada)
# ---------------------------------------------------------------------------

class _TrayFalsa:
    @staticmethod
    def tray_configurada():
        return True

    @staticmethod
    def adicionar_observacao(numero, texto):
        notas = OBSERVACOES_TRAY.setdefault(str(numero), [])
        if texto in notas:
            return False
        notas.append(texto)
        return True

    @staticmethod
    def mudar_status(numero, nome_status):
        STATUS_TRAY[str(numero)] = nome_status


TRAY_FALSA = _TrayFalsa()


def resumo():
    """Texto com tudo o que a demonstração 'criou' até agora."""
    linhas = [f"OCs: {len(OCS)} | Cards no Trello: {len(CARDS)} | Pedidos com observação na Tray: "
              f"{len(OBSERVACOES_TRAY)}"]
    for oc in OCS.values():
        linhas.append(f"  OC {oc['numero']} - {FORNECEDORES.get(oc['fornecedor']['id'], '?')}: "
                      f"{oc.get('observacoes', '')}")
    for card in CARDS:
        linhas.append(f"  Card [{card['lista']}] {card['nome']}")
    return "\n".join(linhas)
