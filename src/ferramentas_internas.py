"""
Assistente do Vendedor - menu único.

[1] Calcular desconto de 5%
[2] Realizar compras (Tray -> Bling -> Trello)
[3] Gerar descrição detalhada em HTML (padrão Tray)

Produtos ESTRUTURADOS no Bling (ex.: mesa = tampo + base) são desmembrados
e comprados por componente, cada um com seu próprio fornecedor.

Status no Bling (e na Tray):
    Tudo em estoque, sem personalização -> Em separação (Tray: Pedido em separação)
    Qualquer OC (compra ou personalização) -> OC enviada (Tray: status configurado em tray.status_oc_enviada)

Tray (TRAY.py, opcional: só funciona com a seção "tray" preenchida no config.json):
    Cada OC criada -> observação no pedido: "OC xxxx Fornecedor - Produtos"
    HTML da opção 3 -> gravado nas observações do pedido

Prints no Trello:
    Logística -> print do pedido da Tray (obrigatório)
    Fábrica   -> print da OC do Bling; o pedido da Tray vai na descrição do card

Requisitos:
    python -m pip install requests pillow

Arquivos na mesma pasta:
    configuracao.py, BLING.py, config.json   (necessários para a opção 2)
    TRAY.py                                   (opcional)
A opção 1 funciona sem eles; a 3 também, preenchendo tudo à mão.

Modo demonstração (MODO_DEMO = True, ligado pelo app_demo.py): Bling, Trello e Tray
são trocados por dados fictícios do demo.py. Nada sai do computador.

Rode:  py ferramentas_internas.py
"""

import os
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from html import escape, unescape
from io import BytesIO

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO (carregada só quando a opção 2 precisa)
# ---------------------------------------------------------------------------

TRELLO_BASE_URL = "https://api.trello.com/1"
VERMELHO = "#ff0000"
AZUL = "#0000ff"
NOME_FABRICA_PADRAO = "Fábrica Própria"

# Demonstração: Bling, Trello e Tray viram dados fictícios em memória (demo.py).
MODO_DEMO = False


def config():
    if MODO_DEMO:
        import demo
        return demo.CONFIG
    from configuracao import carregar_config
    return carregar_config()


def chamar_bling(*args, **kwargs):
    """Carrega o BLING.py só quando precisa."""
    if MODO_DEMO:
        import demo
        return demo.chamar_bling(*args, **kwargs)
    try:
        from BLING import chamar_bling as _chamar
    except ImportError as erro:
        raise RuntimeError(f"Não consegui carregar o BLING.py ({erro}). Ele é necessário para a opção 2.")
    return _chamar(*args, **kwargs)


STATUS_TRAY_PADRAO = {
    "OC enviada": ("status_oc_enviada", "Aguardando fornecedor"),
    "Em separação": ("status_separacao", "Pedido em separação"),
}
_aviso_tray_dado = False


def tray():
    """O módulo TRAY.py, ou None se ele não existir ou a Tray não estiver configurada
    (aí a parte da Tray é pulada e o resto do fluxo segue normal)."""
    global _aviso_tray_dado
    if MODO_DEMO:
        import demo
        return demo.TRAY_FALSA
    try:
        import TRAY
        if TRAY.tray_configurada():
            return TRAY
    except Exception:
        pass
    if not _aviso_tray_dado:
        print("(Tray ainda não configurada no config.json: a parte da Tray foi pulada.)")
        _aviso_tray_dado = True
    return None


def na_tray(acao, funcao, *args):
    """Executa uma ação na Tray sem travar o fluxo: em caso de erro, só avisa."""
    modulo = tray()
    if modulo is None:
        return False
    try:
        resultado = getattr(modulo, funcao)(*args)
    except Exception as erro:
        print(f"ATENÇÃO: não consegui {acao} na Tray ({erro}). Faça isso manualmente na loja.")
        return False
    print(f"Tray: {acao} - OK." if resultado is not False else f"Tray: {acao} - já estava lá, nada mudou.")
    return True


def status_tray_equivalente(status_bling):
    """Nome do status da Tray que corresponde ao status do Bling (config.json pode trocar)."""
    chave, padrao = STATUS_TRAY_PADRAO[status_bling]
    try:
        return (config().get("tray") or {}).get(chave) or padrao
    except Exception:
        return padrao


def trello_auth():
    """Cabeçalho de autenticação do Trello. Fica fora da URL para a chave e o token
    não aparecerem em mensagens de erro (ex.: falha de conexão)."""
    t = config()["trello"]
    return {"Authorization": f'OAuth oauth_consumer_key="{t["key"]}", oauth_token="{t["token"]}"'}


def listas_fabrica():
    """{'1': (nome, id), '2': ...} a partir do config.json."""
    listas = config()["trello"].get("listas_fabrica", [])
    return {str(i): (l["nome"], l["id"]) for i, l in enumerate(listas, 1)}


def nome_fabrica():
    try:
        return config().get("fabrica", {}).get("nome") or NOME_FABRICA_PADRAO
    except Exception:
        return NOME_FABRICA_PADRAO


def prazo_transporte():
    """Dias úteis descontados do prazo para achar a data de embarque."""
    try:
        return int(config().get("prazo_transporte_dias_uteis", 5))
    except Exception:
        return 5


def validar_config_trello():
    """Confere se há ids vazios ou repetidos nas listas do Trello. Devolve lista de problemas."""
    problemas = []
    t = config().get("trello", {})
    if not t.get("lista_logistica_id"):
        problemas.append("lista_logistica_id está vazio")
    vistos = {}
    for nome, id_ in listas_fabrica().values():
        if not id_ or "ID_DA_LISTA" in id_:
            problemas.append(f"a aba '{nome}' está sem id")
        elif id_ in vistos:
            problemas.append(f"as abas '{vistos[id_]}' e '{nome}' estão com o MESMO id")
        else:
            vistos[id_] = nome
    return problemas


# ---------------------------------------------------------------------------
# UTILITÁRIOS
# ---------------------------------------------------------------------------

def sem_acento(texto):
    base = unicodedata.normalize("NFD", str(texto))
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower().strip()


def identificador_fabrica():
    """Trecho que identifica a fábrica no nome do fornecedor (config: fabrica.identificador).
    Sem ele, usa as duas primeiras palavras do nome da fábrica."""
    try:
        ident = (config().get("fabrica") or {}).get("identificador")
    except Exception:
        ident = None
    return sem_acento(ident or " ".join(nome_fabrica().split()[:2]))


def e_fabrica(nome_fornecedor):
    """True se o fornecedor é a nossa fábrica."""
    return bool(nome_fornecedor) and identificador_fabrica() in sem_acento(nome_fornecedor)


def nome_loja():
    """Nome da loja nas mensagens aos fornecedores (config: loja.nome)."""
    try:
        return (config().get("loja") or {}).get("nome") or "nossa loja"
    except Exception:
        return "nossa loja"


def converter_numero(texto):
    """Aceita o formato brasileiro: '1.500,50', '150,50', '1.500', 'R$ 150,50' e também '150.50'.
    Levanta ValueError se não for número."""
    texto = re.sub(r"^\s*R\$\s*", "", str(texto)).replace(" ", "")
    if "," in texto:                                  # vírgula = decimal; pontos = milhar
        texto = texto.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", texto):  # '1.500' ou '1.500.000' = milhar
        texto = texto.replace(".", "")
    return float(texto)


def ler_numero(pergunta, padrao):
    """Pergunta um número; Enter mantém o valor padrão."""
    while True:
        texto = input(f"{pergunta} [Enter = {formatar_quantidade(padrao)}]: ").strip()
        if not texto:
            return padrao
        try:
            return converter_numero(texto)
        except ValueError:
            print("Digite apenas números, por exemplo: 12,5")


# A janela (app.py) troca isto por uma função que mostra um botão por opção.
_escolha_externa = None


def escolher(pergunta, opcoes):
    """Pergunta com opções fixas. opcoes: [(chave, rótulo), ...]; devolve a chave escolhida.
    Na janela: um botão por opção. No terminal: lista e aceita a chave, o rótulo
    ou uma palavra só dele (ex.: 'física')."""
    if _escolha_externa:
        return _escolha_externa(pergunta, opcoes)
    print(f"\n{pergunta}")
    for chave, rotulo in opcoes:
        print(f"  [{chave or 'Enter'}] {rotulo}")
    while True:
        texto = sem_acento(input("Escolha: "))
        exatas = [c for c, r in opcoes if texto in (sem_acento(c), sem_acento(r))]
        por_palavra = [c for c, r in opcoes if texto and texto in sem_acento(r).split()]
        achadas = exatas or (por_palavra if len(por_palavra) == 1 else [])
        if achadas:
            return achadas[0]
        print("Opção inválida, tente novamente.")


def sim(pergunta):
    if _escolha_externa:
        return escolher(pergunta, [("s", "Sim"), ("n", "Não")]) == "s"
    return input(f"{pergunta} [s/N] ").strip().lower() in ("s", "sim")


def nome_arquivo_seguro(texto, sufixo=".png"):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", texto)[:80] + sufixo


def formatar_quantidade(qtd):
    """10.0 -> '10'; 2.5 -> '2,5'."""
    try:
        numero = float(qtd)
    except (TypeError, ValueError):
        return str(qtd)
    return str(int(numero)) if numero == int(numero) else str(numero).replace(".", ",")


def nome_curto(descricao):
    """Tira o nome da loja que vem no fim dos produtos (config: loja.sufixo_nos_produtos).
    Ex. com 'Loja Exemplo': 'Cadeira Aurora - Loja Exemplo Cor:Preta' -> 'Cadeira Aurora Cor:Preta'."""
    try:
        sufixo = ((config().get("loja") or {}).get("sufixo_nos_produtos") or "").strip()
    except Exception:
        sufixo = ""
    if not sufixo:
        return str(descricao).strip()
    return re.sub(rf"\s*-\s*{re.escape(sufixo)}\b", "", str(descricao), flags=re.IGNORECASE).strip()


def rotulo_item(item):
    return f"{formatar_quantidade(item.get('quantidade', 1))}x {nome_curto(item.get('descricao', ''))}"


def nome_da_loja(item):
    """Nome como o cliente comprou na Tray (quando foi buscado); senão, o do Bling sem o sufixo da loja."""
    return item.get("nome_tray") or nome_curto(item.get("descricao", ""))


def rotulo_loja(item):
    """Para Trello e observações: '1x Nome da Tray'. Componente de produto estruturado: '1x Nome da Tray (peça: Tampo)'."""
    texto = f"{formatar_quantidade(item.get('quantidade', 1))}x {nome_da_loja(item)}"
    if item.get("nome_tray") and item.get("kit"):
        texto += f" (peça: {nome_curto(item.get('descricao', ''))})"
    return texto


def texto_itens(itens, separador=", "):
    """'10x Base Aurora, 2x Tampo Redondo' (com os nomes da Tray, quando houver). Personalização fica de fora."""
    return separador.join(rotulo_loja(i) for i in itens if not i.get("personalizacao_linha"))


def texto_personalizacoes(itens, separador="; "):
    """'2x Cadeira X: bordado azul; 1x Mesa Y: logo gravado'."""
    return separador.join(
        f"{formatar_quantidade(i['quantidade'])}x {i.get('nome_tray') or nome_curto(i['produto_ref'])}: "
        f"{i['personalizacao_texto']}"
        for i in itens
        if i.get("personalizacao_linha")
    )


def limpar_nome_tray(nome):
    """'Almofada X (Ref. 1990_23818)<br><strong>Cor Assento</strong> Facto Metal Cobre'
    -> 'Almofada X (Ref. 1990_23818) - Cor Assento: Facto Metal Cobre'."""
    texto = re.sub(r"(?i)<br\s*/?>", " | ", str(nome or ""))
    texto = re.sub(r"(?is)<(strong|b)>(.*?)</\1>\s*", r"\2: ", texto)
    texto = unescape(re.sub(r"<[^>]+>", "", texto))
    partes = [" ".join(p.split()).strip(" -:") for p in texto.split("|")]
    return nome_curto(" - ".join(p for p in partes if p))  # sem o sufixo da loja, como no Bling


def casar_itens_tray(itens_bling, vendidos):
    """{posição no pedido do Bling: nome da Tray}. Primeiro pelo código (SKU do Bling = referência da Tray);
    o que sobrar, pela ordem, só se sobrar a mesma quantidade dos dois lados."""
    return {i: limpar_nome_tray(vendidos[v]["nome"]) for i, v in posicoes_na_tray(itens_bling, vendidos).items()
            if limpar_nome_tray(vendidos[v]["nome"])}


def posicoes_na_tray(itens_bling, vendidos):
    """{posição no pedido do Bling: posição do item vendido na Tray} (mesma regra do casar_itens_tray)."""
    livres = list(range(len(vendidos)))
    pares = {}
    for i, item in enumerate(itens_bling):
        codigo = sem_acento(item.get("codigo") or "")
        achado = next((v for v in livres if codigo and sem_acento(vendidos[v]["referencia"]) == codigo), None)
        if achado is not None:
            pares[i] = achado
            livres.remove(achado)
    restantes = [i for i in range(len(itens_bling)) if i not in pares]
    if restantes and len(restantes) == len(livres):
        pares.update(zip(restantes, livres))
    return pares


def buscar_nomes_na_tray(numero_tray, pedido):
    """Põe em cada item do pedido o nome como está na Tray (campo nome_tray), usado nos cards do Trello e nas
    observações da OC. Sem a Tray ou se ela falhar, tudo segue com os nomes do Bling."""
    modulo = tray()
    if modulo is None:
        return False
    try:
        vendidos = modulo.itens_vendidos(numero_tray)
    except Exception as erro:
        print(f"ATENÇÃO: não consegui ler os nomes na Tray ({erro}). Os cards e as observações usarão os nomes do Bling.")
        return False
    itens = pedido.get("itens", [])
    nomes = casar_itens_tray(itens, vendidos)
    for i, v in posicoes_na_tray(itens, vendidos).items():
        itens[i]["indice_tray"] = v  # para a ficha do pedido achar a foto e a OC de cada produto
    for i, nome in nomes.items():
        itens[i]["nome_tray"] = nome
    if len(nomes) < len(itens):
        print(f"ATENÇÃO: {len(itens) - len(nomes)} item(ns) sem nome correspondente na Tray: ficam com o nome do Bling.")
    print(f"Nomes da Tray: {len(nomes)} de {len(itens)} item(ns).")
    return True


# ---------------------------------------------------------------------------
# BLING: PEDIDO DE VENDA E SITUAÇÕES
# ---------------------------------------------------------------------------

def buscar_id_pedido_tray(numero_tray):
    """Acha o ID interno do pedido de venda no Bling a partir do número da Tray."""
    def mesmo_numero(pedidos):
        # Confere sempre: se o Bling ignorar o filtro, ele devolve os pedidos mais recentes.
        return [p for p in pedidos if str(p.get("numeroLoja", "")).strip() == numero_tray]

    dados = mesmo_numero(
        chamar_bling("GET", "/pedidos/vendas", params={"numerosLojas[]": numero_tray}).get("data", []))
    if not dados:
        recentes = chamar_bling("GET", "/pedidos/vendas", params={"limite": 100}).get("data", [])
        dados = mesmo_numero(recentes)
    if not dados:
        return None
    if len(dados) > 1:
        print(f"Atenção: {len(dados)} pedidos com esse número da Tray, usando o primeiro.")
    return dados[0]["id"]


def mostrar_pedido(id_pedido):
    pedido = chamar_bling("GET", f"/pedidos/vendas/{id_pedido}").get("data", {})
    print(f"\nPedido encontrado no Bling: Nº {pedido.get('numero')} (ID {id_pedido})")
    for item in pedido.get("itens", []):
        print(f"  • {item.get('codigo', '?')} - {nome_curto(item.get('descricao', ''))} "
              f"(qtd {formatar_quantidade(item.get('quantidade', '?'))})")
    return pedido


def achar_id_situacao_venda(rotulo, nomes_exatos, palavra_chave):
    """Procura no módulo de Vendas a situação desejada. Devolve o id ou None."""
    modulos = chamar_bling("GET", "/situacoes/modulos").get("data", [])
    modulo = next((m for m in modulos if "venda" in sem_acento(m.get("nome", ""))), None)
    if modulo is None:
        print("Não achei o módulo de vendas no Bling.")
        return None

    situacoes = chamar_bling("GET", f"/situacoes/modulos/{modulo['id']}").get("data", [])
    for s in situacoes:
        if sem_acento(s.get("nome", "")) in nomes_exatos:
            return s["id"]
    parecidas = [s for s in situacoes if palavra_chave in sem_acento(s.get("nome", ""))]
    if len(parecidas) == 1:
        return parecidas[0]["id"]

    escolhido = escolher(f"Não consegui identificar sozinho a situação '{rotulo}' no Bling. Qual é ela?",
                         [(str(s.get("id")), s.get("nome", "")) for s in situacoes] + [("", "Cancelar")])
    return int(escolhido) if escolhido.isdigit() else None


def id_situacao_separacao():
    return achar_id_situacao_venda("Em separação", ["em separacao", "pedido em separacao"], "separacao")


def id_situacao_oc_enviada():
    return achar_id_situacao_venda("OC enviada", ["oc enviada", "oc enviado"], "oc env")


def mudar_situacao_venda(id_pedido, id_situacao):
    chamar_bling("PATCH", f"/pedidos/vendas/{id_pedido}/situacoes/{id_situacao}")


# ---------------------------------------------------------------------------
# COMPRA - FASE 1: LEVANTAR ITENS
# ---------------------------------------------------------------------------

MAX_NIVEIS_ESTRUTURA = 3  # proteção contra estrutura dentro de estrutura em loop


def item_base(produto_id, codigo, descricao, quantidade, kit=None, origem_pedido=None, comprar=True):
    return {
        "produto_id": produto_id,
        "codigo": codigo or "?",
        "descricao": descricao or "",
        "quantidade": float(quantidade or 1),
        "kit": kit,                    # nome do produto estruturado de origem (se for componente)
        "origem_pedido": origem_pedido,  # posição do item no pedido de venda (liga OC <-> item do pedido)
        "comprar": comprar,            # False = sai do estoque (não entra em OC de compra)
        "fornecedor_codigo": "",       # código do produto NO FORNECEDOR (cadastro do Bling)
        "fornecedor_descricao": "",    # nome/descrição do produto NO FORNECEDOR
        "fornecedor_id": None,
        "fornecedor_nome": None,
        "valor": 0.0,
        "personalizacao": "",
        "valor_personalizacao": 0.0,
    }


def dados_produto(produto_id):
    return chamar_bling("GET", f"/produtos/{produto_id}").get("data", {}) or {}


def e_estruturado(produto):
    """Produto com composição no Bling: formato 'E' ou com componentes na estrutura."""
    return produto.get("formato") == "E" or bool((produto.get("estrutura") or {}).get("componentes"))


def componentes_da_estrutura(produto):
    """Lista de componentes [{'produto': {'id'}, 'quantidade'}] de um produto estruturado."""
    comps = (produto.get("estrutura") or {}).get("componentes") or []
    if not comps and produto.get("formato") == "E" and produto.get("id"):
        try:  # alguns retornos não trazem os componentes no GET do produto
            dados = chamar_bling("GET", f"/produtos/estruturas/{produto['id']}").get("data", {}) or {}
            comps = dados.get("componentes") or (dados.get("estrutura") or {}).get("componentes") or []
        except Exception as erro:
            print(f"    (não consegui ler a estrutura do produto {produto.get('id')}: {erro})")
    return comps


def preencher_fornecedor(info, produto):
    fornecedor = produto.get("fornecedor", {}) or {}
    contato = fornecedor.get("contato", {}) or {}
    info["fornecedor_id"] = contato.get("id")
    info["fornecedor_nome"] = contato.get("nome") or fornecedor.get("nome")
    info["fornecedor_codigo"] = str(fornecedor.get("codigo") or "").strip()
    vinculo = fornecedor.get("id")  # vínculo produto x fornecedor: tem a descrição do produto no fornecedor
    if vinculo:
        try:
            dados = chamar_bling("GET", f"/produtos/fornecedores/{vinculo}").get("data", {}) or {}
            info["fornecedor_descricao"] = str(dados.get("descricao") or "").strip()
            info["fornecedor_codigo"] = str(dados.get("codigo") or "").strip() or info["fornecedor_codigo"]
        except Exception:
            pass  # sem a descrição do fornecedor, a mensagem usa o nome da loja
    info["valor"] = float(
        fornecedor.get("precoCompra") or fornecedor.get("precoCusto") or produto.get("precoCusto") or 0
    )


def expandir_produto(produto_id, quantidade, descricao=None, codigo=None, kit=None, nivel=0, origem_pedido=None):
    """
    Devolve a lista de itens COMPRÁVEIS de um produto:
      - simples      -> ele mesmo;
      - estruturado  -> cada componente (quantidade do pedido x quantidade na estrutura).
    """
    produto = dados_produto(produto_id)
    descricao = descricao or produto.get("nome", "")
    codigo = codigo or produto.get("codigo", "?")
    recuo = "    " * (nivel + 1)

    if e_estruturado(produto) and nivel < MAX_NIVEIS_ESTRUTURA:
        comps = componentes_da_estrutura(produto)
        if comps:
            print(f"{recuo}↳ {descricao} é ESTRUTURADO: comprando por componente ({len(comps)})")
            itens = []
            for c in comps:
                cid = (c.get("produto") or {}).get("id")
                if not cid:
                    continue
                qtd_comp = float(c.get("quantidade") or 1)
                itens += expandir_produto(cid, quantidade * qtd_comp, kit=kit or descricao, nivel=nivel + 1,
                                          origem_pedido=origem_pedido)
            return itens
        print(f"{recuo}ATENÇÃO: {descricao} está como estruturado, mas não achei os componentes. "
              "Vai ser comprado como produto único.")

    info = item_base(produto_id, codigo, descricao, quantidade, kit, origem_pedido)
    preencher_fornecedor(info, produto)
    if nivel > 0:
        print(f"{recuo}• {rotulo_item(info)} [{info['fornecedor_nome'] or 'SEM fornecedor'}]")
    return [info]


def levantar_itens(pedido, buscar_fornecedor=True, comprar=None):
    """
    Monta a lista de itens.
    - buscar_fornecedor=True (compra): consulta no Bling os itens que VÃO ser comprados; produtos
      ESTRUTURADOS são desmembrados nos componentes, com fornecedor e preço de cada um.
      comprar = [True/False por item do pedido]; os False saem do estoque (sem consultar o Bling).
    - buscar_fornecedor=False (estoque): só a lista do pedido, tudo do estoque.
    """
    itens = []
    for i, item in enumerate(pedido.get("itens", [])):
        produto_id = (item.get("produto", {}) or {}).get("id")
        codigo, descricao = item.get("codigo", "?"), item.get("descricao", "")
        quantidade = float(item.get("quantidade", 1) or 1)
        vai_comprar = buscar_fornecedor and (comprar[i] if comprar is not None else True)
        if produto_id and vai_comprar:
            itens += expandir_produto(produto_id, quantidade, descricao, codigo, origem_pedido=i)
        else:
            itens.append(item_base(produto_id, codigo, descricao, quantidade, origem_pedido=i, comprar=vai_comprar))
    # Nome da Tray (buscar_nomes_na_tray): cada peça, inclusive componente, herda o do item do pedido
    nomes = [item.get("nome_tray") for item in pedido.get("itens", [])]
    for it in itens:
        origem = it.get("origem_pedido")
        if origem is not None and origem < len(nomes) and nomes[origem]:
            it["nome_tray"] = nomes[origem]
    return itens


def perguntar_o_que_comprar(pedido):
    """Pergunta, item a item do pedido, se precisa comprar. Devolve [True/False, ...]."""
    itens = pedido.get("itens", [])
    if len(itens) <= 1:  # um item só: já respondeu "precisa comprar" no menu
        return [True] * len(itens)
    print("\n--- O que precisa comprar? ---")
    respostas = []
    for item in itens:
        respostas.append(escolher(f"{rotulo_item(item)}: precisa comprar?",
                                  [("s", "Sim, comprar"), ("n", "Não, tem em estoque")]) == "s")
    return respostas


# ---------------------------------------------------------------------------
# COMPRA - FASE 2: PERSONALIZAÇÃO PRODUTO A PRODUTO
# ---------------------------------------------------------------------------

def perguntar_personalizacoes(itens, mostrar_origem=True):
    """Pergunta, para cada produto, se ele tem personalização (texto + valor por unidade).
    Devolve True se algum produto tiver personalização."""
    print("\n--- Personalização (produto a produto) ---")
    for it in itens:
        if mostrar_origem and it.get("comprar", True):
            origem = it["fornecedor_nome"] or "SEM fornecedor cadastrado"
            if e_fabrica(it["fornecedor_nome"]):
                origem += " (fábrica)"
            if it.get("kit"):
                origem += f" | parte de: {it['kit']}"
            print(f"\n  • {rotulo_item(it)}  [{origem}]")
        else:
            print(f"\n  • {rotulo_item(it)}  [em estoque]")
        if not sim("    Esse produto tem personalização?"):
            continue
        texto = input("    Qual a personalização? ").strip()
        if not texto:
            print("    Personalização vazia, ignorada.")
            continue
        it["personalizacao"] = texto
        it["valor_personalizacao"] = ler_numero("    Valor da personalização POR UNIDADE (OC da fábrica)", 0.0)
    return any(it["personalizacao"] for it in itens)


# ---------------------------------------------------------------------------
# COMPRA - FASE 3: MONTAR O PLANO DE OCs
# ---------------------------------------------------------------------------

def localizar_fabrica():
    """Acha o contato da fábrica no Bling. Devolve (id, nome) ou None."""
    fab_cfg = {}
    try:
        fab_cfg = config().get("fabrica", {}) or {}
    except Exception:
        pass
    if fab_cfg.get("contato_id"):
        return int(fab_cfg["contato_id"]), fab_cfg.get("nome") or NOME_FABRICA_PADRAO

    achados = []
    try:
        pesquisa = ((config().get("fabrica") or {}).get("identificador") or nome_fabrica())
        contatos = chamar_bling("GET", "/contatos", params={"pesquisa": pesquisa}).get("data", [])
        achados = [c for c in contatos if e_fabrica(c.get("nome"))]
    except Exception as erro:
        print(f"Não consegui pesquisar o contato da fábrica automaticamente ({erro}).")

    escolhido = None
    if len(achados) == 1:
        escolhido = achados[0]
    elif len(achados) > 1:
        escolha = escolher("Vários contatos parecidos com a fábrica. Qual é ela?",
                           [(str(i), f"{c.get('nome')} (id {c.get('id')})") for i, c in enumerate(achados, 1)]
                           + [("0", "Nenhum destes")])
        if escolha != "0":
            escolhido = achados[int(escolha) - 1]

    if escolhido:
        print(f"Fábrica: {escolhido.get('nome')} (id {escolhido['id']}). "
              "Dica: coloque esse id em fabrica.contato_id no config.json para pular essa busca.")
        return escolhido["id"], escolhido.get("nome", nome_fabrica())

    manual = input(f"Não achei '{nome_fabrica()}'. Digite o ID do contato no Bling (Enter cancela): ").strip()
    return (int(manual), nome_fabrica()) if manual.isdigit() else None


def linha_personalizacao(item, fab_id, fab_nome):
    """Linha destacada da OC da fábrica com a personalização de um produto."""
    return {
        "produto_id": None,
        "codigo": "",
        "descricao": f"*** PERSONALIZAÇÃO - {item['descricao']}: {item['personalizacao']} ***",
        "quantidade": item["quantidade"],
        "valor": item["valor_personalizacao"],
        "fornecedor_id": fab_id,
        "fornecedor_nome": fab_nome,
        "personalizacao_linha": True,
        "personalizacao_texto": item["personalizacao"],
        "produto_ref": item["descricao"],
        "nome_tray": item.get("nome_tray"),
        "origem": item,  # para acompanhar a quantidade revisada do produto
        "origem_pedido": item.get("origem_pedido"),
    }


def montar_plano(itens, comprar_produtos=True):
    """
    Agrupa tudo em OCs, uma por fornecedor.
    Com comprar_produtos=False (ramo estoque) os produtos NÃO são comprados:
    sai apenas a OC da fábrica com as linhas de personalização.
    A OC da FÁBRICA recebe:
      - os itens que a própria fábrica fornece (com a personalização logo abaixo de cada um);
      - a personalização dos itens que vêm de outros fornecedores.
    Devolve lista de grupos: {"fornecedor_id", "fornecedor_nome", "itens", "fabrica"}.
    """
    grupos = {}
    if not comprar_produtos:
        pers = [it for it in itens if it["personalizacao"]]
        if not pers:
            return []
        fabrica = localizar_fabrica()
        if fabrica is None:
            print("Sem o contato da fábrica, a OC de personalização não será criada.")
            return []
        return [{"fornecedor_id": fabrica[0], "fornecedor_nome": fabrica[1], "fabrica": True,
                 "itens": [linha_personalizacao(it, *fabrica) for it in pers]}]

    a_comprar = [it for it in itens if it.get("comprar", True)]
    sem_fornecedor = [it for it in a_comprar if not it["fornecedor_id"]]
    # Personalização que vai para a OC da fábrica sem o produto: itens de outros fornecedores,
    # sem fornecedor, ou que saem do estoque
    pers_externas = [it for it in itens if it["personalizacao"]
                     and (not it.get("comprar", True) or not e_fabrica(it["fornecedor_nome"]))]

    if sem_fornecedor:
        print("\nATENÇÃO: estes itens estão SEM fornecedor no cadastro e não entram em nenhuma OC de compra:")
        for it in sem_fornecedor:
            print(f"  - {it['codigo']} - {it['descricao']}")

    # Identifica a fábrica: pelos próprios itens ou, se precisar, pelo cadastro.
    fabrica = next(((it["fornecedor_id"], it["fornecedor_nome"]) for it in a_comprar
                    if it["fornecedor_id"] and e_fabrica(it["fornecedor_nome"])), None)
    if fabrica is None and pers_externas:
        fabrica = localizar_fabrica()
        if fabrica is None:
            print("Sem o contato da fábrica, as personalizações NÃO entrarão em nenhuma OC.")

    def grupo(fid, fnome):
        if fid not in grupos:
            grupos[fid] = {"fornecedor_id": fid, "fornecedor_nome": fnome, "itens": [],
                           "fabrica": e_fabrica(fnome)}
        return grupos[fid]

    # Itens a comprar com fornecedor (fábrica: produto + personalização em sequência)
    for it in a_comprar:
        if not it["fornecedor_id"]:
            continue
        g = grupo(it["fornecedor_id"], it["fornecedor_nome"])
        g["itens"].append(it)
        if g["fabrica"] and it["personalizacao"]:
            g["itens"].append(linha_personalizacao(it, *fabrica))

    # Personalizações de itens de outros fornecedores (ou sem fornecedor) -> OC da fábrica
    if fabrica and pers_externas:
        g = grupo(*fabrica)
        g["fabrica"] = True
        for it in pers_externas:
            g["itens"].append(linha_personalizacao(it, *fabrica))

    # Fábrica por último, para as OCs dos outros fornecedores saírem antes
    return sorted(grupos.values(), key=lambda g: g["fabrica"])


# ---------------------------------------------------------------------------
# COMPRA - FASE 4: REVISAR, CONFIRMAR E CRIAR AS OCs
# ---------------------------------------------------------------------------

def revisar_itens(grupo):
    """Deixa ajustar quantidade/valor dos produtos. Na linha de personalização, a quantidade
    sugerida é a que ficou no produto (a OC da fábrica é revisada por último)."""
    print(f"\n=== OC para: {grupo['fornecedor_nome']} (contato id {grupo['fornecedor_id']}) ===")
    finais = []
    for it in grupo["itens"]:
        if it.get("personalizacao_linha"):
            origem = it.get("origem") or {}
            sugerida = origem.get("quantidade_revisada", it["quantidade"])
            print(f"\n  ★ {it['descricao']} - R$ {it['valor']:.2f}/un")
            qtd = ler_numero("    Quantidade a personalizar (0 = tirar da OC)", sugerida)
            if qtd <= 0:
                print("    Personalização retirada desta OC.")
                continue
            finais.append({**it, "quantidade": qtd})
            continue
        print(f"\n  • {it['codigo']} - {it['descricao']}")
        qtd = ler_numero("    Quantidade a comprar (0 = não comprar este item)", it["quantidade"])
        it["quantidade_revisada"] = qtd
        if qtd <= 0:
            print("    Item ignorado nesta OC.")
            continue
        valor = ler_numero("    Valor unitário de compra", it["valor"])
        finais.append({**it, "quantidade": qtd, "valor": valor})
    return finais


def pedir_data_prevista(sugerida=None):
    """Data prevista de entrega do fornecedor (obrigatória no Bling). Devolve 'aaaa-mm-dd'.
    sugerida: o prazo dos fornecedores calculado pela tabela da transportadora (Enter aceita)."""
    padrao = ""
    if sugerida:
        if sugerida < date.today():
            print(f"ATENÇÃO: pedido ATRASADO: o prazo dos fornecedores era {sugerida.strftime('%d/%m/%Y')}. "
                  "Sugerindo o próximo dia útil.")
            sugerida = somar_dias_uteis(date.today(), 1)
        padrao = sugerida.strftime("%d/%m/%Y")
    while True:
        texto = input("Data prevista de entrega do fornecedor (dd/mm/aaaa)"
                      + (f" [Enter = {padrao}]" if padrao else "") + ": ").strip() or padrao
        try:
            return datetime.strptime(texto, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            print("Data inválida, use o formato dd/mm/aaaa (ex: 20/10/2026).")


def pedir_observacoes_internas(texto_padrao):
    print(f"Observação interna padrão: {texto_padrao}")
    extra = input("Complemento das observações internas (Enter para usar só o padrão): ").strip()
    return f"{texto_padrao} | {extra}" if extra else texto_padrao


class OCReconciliacaoNecessaria(RuntimeError):
    """A OC pode já existir; uma falha de conferência nunca autoriza repetir o POST."""

    def __init__(self, id_oc):
        self.id_oc = id_oc
        super().__init__(f"OC ID {id_oc} criada; releitura/vínculo pendente. Não repetir a criação.")


def conferir_fornecedor(fornecedor_id):
    """Confirma o mesmo contato ativo; homônimo ativo é apenas candidato, nunca substituição automática."""
    contato = chamar_bling("GET", f"/contatos/{fornecedor_id}").get("data", {}) or {}
    if str(contato.get("id")) != str(fornecedor_id):
        raise RuntimeError("Identidade do fornecedor não confirmada; compra bloqueada.")
    if contato.get("situacao") == "A":
        return contato

    candidatos = []
    nome = str(contato.get("nome") or "").strip()
    if nome:
        try:
            encontrados = chamar_bling(
                "GET", "/contatos",
                params={"pesquisa": nome, "pagina": 1, "limite": 100},
            ).get("data", [])
            candidatos = [
                str(c["id"])
                for c in encontrados
                if c.get("situacao") == "A"
                and c.get("id")
                and sem_acento(str(c.get("nome") or "")).strip().casefold()
                == sem_acento(nome).strip().casefold()
            ]
        except Exception:
            pass
    sugestao = ", ".join(sorted(set(candidatos))) or "nenhum candidato confirmado nesta consulta"
    raise RuntimeError(
        f"Fornecedor {fornecedor_id} não está ativo. Candidatos homônimos: {sugestao}. "
        "Reconciliar identidade e vínculo do produto; nenhuma troca automática foi feita."
    )


def criar_oc(fornecedor_id, itens, data_prevista, observacoes="", observacoes_internas="",
             ordem_compra=""):
    """Cria o pedido de compra no Bling e devolve (id, numero)."""
    conferir_fornecedor(fornecedor_id)
    itens_payload = []
    for it in itens:
        item = {"descricao": it["descricao"], "quantidade": it["quantidade"], "valor": it["valor"]}
        if it.get("produto_id"):
            item["produto"] = {"id": it["produto_id"]}
        itens_payload.append(item)

    payload = {
        "data": date.today().strftime("%Y-%m-%d"),
        "dataPrevista": data_prevista,
        "fornecedor": {"id": fornecedor_id},
        "itens": itens_payload,
    }
    # Liga a OC ao pedido de origem da Tray no campo próprio do Bling.
    # Fazer isso na criação evita que uma OC recebida/bloqueada fique sem vínculo depois.
    if str(ordem_compra or "").strip():
        payload["ordemCompra"] = str(ordem_compra).strip()
    if observacoes:
        payload["observacoes"] = observacoes
    if observacoes_internas:
        payload["observacoesInternas"] = observacoes_internas

    id_oc = chamar_bling("POST", "/pedidos/compras", json=payload).get("data", {}).get("id")
    if not id_oc:
        raise OCReconciliacaoNecessaria("não retornado; reconciliar antes de tentar novamente")
    try:
        relida = chamar_bling("GET", f"/pedidos/compras/{id_oc}").get("data", {})
        if (
            str(relida.get("id")) != str(id_oc)
            or not relida.get("numero")
            or str((relida.get("fornecedor") or {}).get("id")) != str(fornecedor_id)
            or (
                payload.get("ordemCompra")
                and str(relida.get("ordemCompra") or "").strip() != payload["ordemCompra"]
            )
        ):
            raise ValueError("OC divergente")
    except Exception:
        raise OCReconciliacaoNecessaria(id_oc) from None
    return id_oc, relida["numero"]


def processar_grupo(grupo, texto_obs_padrao, numero_tray="", data_sugerida=None):
    """Revisa, confirma e cria a OC de um fornecedor. Devolve o dict da OC ou None."""
    finais = revisar_itens(grupo)
    if not finais:
        print("Nenhum item para este fornecedor, pulando.")
        return None

    # Observações da OC: só o que ESTA OC compra (+ personalização, na OC da fábrica)
    obs_padrao = texto_obs_padrao
    produtos = texto_itens(finais)
    pers = texto_personalizacoes(finais)
    if produtos:
        obs_padrao += f" | {produtos}"
    if pers:
        obs_padrao += f" | PERSONALIZAÇÃO: {pers}"

    data_prevista = pedir_data_prevista(data_sugerida)
    obs = pedir_observacoes_internas(obs_padrao)

    total = sum(i["quantidade"] * i["valor"] for i in finais)
    print(f"\nResumo da OC para {grupo['fornecedor_nome']}:")
    for i in finais:
        marca = "★" if i.get("personalizacao_linha") else "•"
        print(f"  {marca} {rotulo_item(i)} - R$ {i['valor']:.2f}/un")
    print(f"  Total R$ {total:.2f} | entrega prevista {data_prevista}")
    if not sim(f"Criar a OC para {grupo['fornecedor_nome']}?"):
        print("Cancelado, nada foi criado para este fornecedor.")
        return None

    # Observações: só o padrão. Observações internas: padrão + complemento digitado.
    id_oc, numero = criar_oc(
        grupo["fornecedor_id"], finais, data_prevista, obs_padrao, obs,
        ordem_compra=numero_tray,
    )
    print(f"OC criada! Nº {numero} (ID {id_oc})")
    return {
        "id": id_oc,
        "numero": numero,
        "fornecedor_id": grupo["fornecedor_id"],
        "fornecedor_nome": grupo["fornecedor_nome"],
        "fabrica": grupo["fabrica"],
        "itens": finais,
        "data_prevista": data_prevista,
        # só o complemento digitado (o padrão repete os itens): vai para a ficha da OC no card da Fábrica
        "observacoes_ficha": obs[len(obs_padrao) + 3:].strip() if obs.startswith(obs_padrao + " | ") else "",
    }


# ---------------------------------------------------------------------------
# TRELLO
# ---------------------------------------------------------------------------

def pegar_imagem_do_clipboard():
    try:
        from PIL import ImageGrab
        imagem = ImageGrab.grabclipboard()
    except Exception as erro:
        print(f"Não foi possível acessar a área de transferência aqui ({erro}).")
        return None
    if imagem is None:
        return None
    if isinstance(imagem, list):  # copiou o ARQUIVO no Explorer em vez da imagem
        arquivos = [c for c in imagem if os.path.isfile(c)]
        if not arquivos:
            return None
        with open(arquivos[0], "rb") as f:
            return BytesIO(f.read())
    buffer = BytesIO()
    imagem.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def escolher_arquivo_manualmente():
    caminho = input("Cole o caminho do arquivo de imagem (ou Enter para cancelar): ").strip().strip('"')
    if not caminho:
        return None
    if not os.path.isfile(caminho):
        print(f"Arquivo não encontrado: {caminho}")
        return None
    with open(caminho, "rb") as f:
        return BytesIO(f.read())


def capturar_print(instrucao):
    print(instrucao)
    if MODO_DEMO:
        import demo
        escolher("Quando o print estiver copiado:", [("", "Pronto, já copiei o print (simulado)")])
        return demo.print_simulado()
    escolher("Quando o print estiver copiado:", [("", "Pronto, já copiei o print")])
    imagem = pegar_imagem_do_clipboard()
    if imagem is None:
        print("Não encontrei imagem na área de transferência, vamos pelo caminho do arquivo.")
        imagem = escolher_arquivo_manualmente()
    return imagem.read() if imagem else None


def checar_trello(resposta, acao):
    """Mostra o motivo da recusa de forma curta, sem o traceback do requests."""
    if not resposta.ok:
        raise RuntimeError(f"O Trello recusou ao {acao}: erro {resposta.status_code} - {resposta.text[:200]}")


def criar_card(lista_id, nome_card, data_limite_iso=None, descricao=None):
    if MODO_DEMO:
        import demo
        return demo.criar_card(lista_id, nome_card, data_limite_iso, descricao)
    import requests
    dados = {"idList": lista_id, "name": nome_card}
    if data_limite_iso:
        dados["due"] = data_limite_iso
    if descricao:
        dados["desc"] = descricao
    resposta = requests.post(f"{TRELLO_BASE_URL}/cards", headers=trello_auth(), data=dados, timeout=30)
    checar_trello(resposta, f"criar o card na lista {lista_id}")
    card = resposta.json()
    return card["id"], card.get("shortUrl", "")


def anexar_imagem(card_id, conteudo_imagem, nome_arquivo):
    if MODO_DEMO:
        import demo
        return demo.anexar_imagem(card_id, conteudo_imagem, nome_arquivo)
    import requests
    resposta = requests.post(
        f"{TRELLO_BASE_URL}/cards/{card_id}/attachments",
        headers=trello_auth(),
        files={"file": (nome_arquivo, BytesIO(conteudo_imagem))},
        timeout=60,
    )
    checar_trello(resposta, f"anexar o print '{nome_arquivo}'")


FOLGA_TRELLO_DIAS_UTEIS = 10


def dias_uteis_trello(dias_combinados):
    """Prazo que vai para o card: 10 dias úteis a menos que o combinado.
    Até 10 dias úteis, fica igual ao combinado. Ex.: 20 -> 10; 8 -> 8."""
    if dias_combinados > FOLGA_TRELLO_DIAS_UTEIS:
        return dias_combinados - FOLGA_TRELLO_DIAS_UTEIS
    return dias_combinados


def dias_ate_entrega_tray(numero_tray, hoje=None):
    """(data, dias úteis de 'hoje' até ela) da entrega prevista pela Tray, ou (None, None).
    No fluxo de compras, 'hoje' é a data da compra (o prazo combinado conta da compra)."""
    modulo = tray() if numero_tray else None
    if modulo is None:
        return None, None
    try:
        texto = modulo.entrega_prevista(numero_tray)
    except Exception as erro:
        print(f"(não consegui ler a entrega prevista na Tray: {erro})")
        return None, None
    if not texto:
        return None, None
    data = datetime.strptime(texto[:10], "%Y-%m-%d").date()
    return data, dias_uteis_ate(hoje or date.today(), data)


def pedir_prazo_combinado(ctx=None, obrigatorio=False):
    """Pergunta o prazo combinado em dias úteis (UMA vez por pedido: fica em ctx['dias_combinados'] e é usado no
    HTML e no card da Logística). Enter = a entrega prevista que a Tray calculou para o pedido."""
    if ctx is not None and ctx.get("dias_combinados") is not None:
        return ctx["dias_combinados"]
    base = (ctx or {}).get("data_compra")  # com a data da compra, o prazo conta dela (como na Tray)
    data_tray, dias_tray = dias_ate_entrega_tray((ctx or {}).get("numero_tray"), hoje=base)
    usar_tray = data_tray is not None and dias_tray > 0
    if data_tray is not None and not usar_tray:
        print(f"A Tray não informou um prazo de entrega útil ({data_tray.strftime('%d/%m/%Y')}): informe o prazo.")
    sugestao = (f"Enter = data da Tray, {data_tray.strftime('%d/%m/%Y')} = {dias_tray} dias úteis" if usar_tray
                else ("" if obrigatorio else "Enter para pular"))
    while True:
        texto = input(f"Prazo de entrega combinado (quantos dias úteis?{' ' + sugestao if sugestao else ''}): ").strip()
        if not texto and usar_tray:
            texto = str(dias_tray)
            print(f"Usando a entrega prevista na Tray: {dias_tray} dias úteis.")
        if not texto and not obrigatorio:
            return None
        if not texto.isdigit():
            print("Digite só o número de dias úteis, por exemplo: 20")
            continue
        if ctx is not None:
            ctx["dias_combinados"] = int(texto)
        return int(texto)


def pedir_data_limite(ctx=None):
    """Data do card da Logística (ISO). Com o prazo da transportadora: a data máxima de EMBARQUE.
    Sem tabela (regra anterior): prazo combinado - 10 dias úteis de folga, contado de hoje."""
    embarque = ((ctx or {}).get("prazos") or {}).get("embarque")
    if embarque:
        print(f"Data no Trello: {embarque.strftime('%d/%m/%Y')} = embarque máximo (prazo combinado - frete).")
        return embarque.strftime("%Y-%m-%dT12:00:00.000Z")
    combinados = pedir_prazo_combinado(ctx)
    if combinados is None:
        return None
    no_trello = dias_uteis_trello(combinados)
    data = somar_dias_uteis(date.today(), no_trello)
    folga = f" ({combinados} combinados - {FOLGA_TRELLO_DIAS_UTEIS} de folga)" if no_trello != combinados else ""
    print(f"Data no Trello: {data.strftime('%d/%m/%Y')} = {no_trello} dias úteis a partir de hoje{folga}.")
    return data.strftime("%Y-%m-%dT12:00:00.000Z")


def iso_da_data_bling(data_aaaa_mm_dd):
    return f"{data_aaaa_mm_dd}T12:00:00.000Z"


def escolher_lista_fabrica():
    listas = listas_fabrica()
    if not listas:
        raise RuntimeError("Nenhuma aba da fábrica em trello.listas_fabrica no config.json.")
    chave = escolher("Em qual aba do Trello da Fábrica incluir?",
                     [(chave, nome) for chave, (nome, _id) in listas.items()])
    return listas[chave]


def titulo_fabrica(f, numero_tray):
    prefixo = ("ATRASADO - " if f.get("atrasado") else "") + ("URGENTE: " if f["urgente"] else "")
    titulo = f"{prefixo}OC {f['oc']['numero']} ({numero_tray})"
    if f["itens"]:
        titulo += f" - {f['itens']}"
    if f["personalizacao"]:
        titulo += f" - Personalização: {f['personalizacao']}"
    return titulo


def transportadora_do_pedido(pedido):
    """Nome da transportadora no pedido de venda do Bling ('' se não estiver definida)."""
    transporte = pedido.get("transporte") or {}
    nome = ((transporte.get("contato") or {}).get("nome") or "").strip()
    if not nome:  # sem contato: tenta o serviço do volume (ex.: 'Rápida Standard')
        volumes = transporte.get("volumes") or []
        nome = ((volumes[0] or {}).get("servico") or "").strip() if volumes else ""
    return nome


def pedir_transportadora(pedido):
    sugerida = transportadora_do_pedido(pedido)
    if not sugerida:
        print("O pedido não tem transportadora definida no Bling.")
        try:
            import prazos_frete
            com_tabela = ", ".join(prazos_frete.nomes().values())
        except Exception:
            com_tabela = ""
        if com_tabela:
            print(f"Com tabela de prazos: {com_tabela} (outra: vale a regra anterior de datas).")
        return input("Transportadora utilizada: ").strip()
    digitada = input(f"Transportadora utilizada [Enter = {sugerida}]: ").strip()
    return digitada or sugerida


# ---------------------------------------------------------------------------
# PRAZOS DO PEDIDO (tabela de frete da transportadora)
# ---------------------------------------------------------------------------
# Contado da DATA DA COMPRA, em dias úteis (sem fim de semana nem feriado):
#   entrega ao cliente   = compra + prazo combinado
#   embarque máximo      = entrega - frete da transportadora até o destino  (data do card da Logística)
#   prazo dos fornecedores = embarque - 3 dias úteis de logística          (data das OCs e do card da Fábrica)
# Grande São Paulo: frete de 1 dia útil. Sem tabela para a transportadora/destino: regra anterior.

LOGISTICA_DIAS_UTEIS = 3


def data_da_compra(ctx):
    texto = str((ctx.get("pedido") or {}).get("data") or "")[:10]
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        o = _pedido_tray_completo(ctx) if tray() else None
        try:
            return datetime.strptime(str((o or {}).get("date") or "")[:10], "%Y-%m-%d").date()
        except ValueError:
            return date.today()


def destino_do_pedido(ctx):
    """CEP, cidade, UF e se o cliente é pessoa jurídica (só para escolher a coluna da tabela)."""
    try:
        o = _pedido_tray_completo(ctx)
    except Exception as erro:
        print(f"(não consegui ler o destino na Tray: {erro})")
        return {}
    cliente = (o or {}).get("Customer") or {}
    enderecos = [(e.get("CustomerAddress") or e) for e in cliente.get("CustomerAddresses") or []]
    entrega = (next((e for e in enderecos if str(e.get("type_delivery")) == "1"), None)
               or next((e for e in enderecos if str(e.get("active")) == "1"), None) or (enderecos[0] if enderecos else {}))
    return {"cep": entrega.get("zip_code"), "cidade": entrega.get("city"), "uf": entrega.get("state"),
            "pessoa_juridica": bool(str(cliente.get("cnpj") or "").strip())}


def calcular_prazos(compra, combinados, frete, hoje=None):
    hoje = hoje or date.today()
    p = {"compra": compra, "combinados": combinados, "frete": frete, "logistica": LOGISTICA_DIAS_UTEIS,
         "entrega": somar_dias_uteis(compra, combinados)}
    if frete is not None:
        p["embarque"] = somar_dias_uteis(compra, max(combinados - frete, 0))
        p["fornecedores"] = somar_dias_uteis(compra, max(combinados - frete - LOGISTICA_DIAS_UTEIS, 0))
        p["sem_folga"] = combinados - frete - LOGISTICA_DIAS_UTEIS <= 0
        p["embarque_atrasado"] = p["embarque"] < hoje
        p["fornecedores_atrasado"] = p["fornecedores"] < hoje
    return p


def planejar_prazos(ctx):
    """Antes das OCs: transportadora, frete pela tabela até o destino e prazo combinado (Enter = data da Tray).
    Fica em ctx['prazos'] e vale para as OCs, o HTML, os cards e as fichas."""
    print("\n--- Prazos do pedido ---")
    ctx["transportadora"] = pedir_transportadora(ctx["pedido"])
    ctx["data_compra"] = data_da_compra(ctx)
    destino = destino_do_pedido(ctx) if tray() else {}
    try:
        import prazos_frete
        frete = prazos_frete.prazo(ctx["transportadora"], **destino)
    except Exception as erro:
        frete = {"dias": None, "motivo": f"não consegui consultar a tabela ({erro})"}
    ctx["frete"] = frete
    combinados = pedir_prazo_combinado(ctx, obrigatorio=True)
    p = ctx["prazos"] = calcular_prazos(ctx["data_compra"], combinados, frete.get("dias"))
    br = lambda d: d.strftime("%d/%m/%Y")
    print(f"Compra: {br(p['compra'])} | prazo combinado: {combinados} dias úteis | entrega ao cliente: {br(p['entrega'])}")
    if frete.get("dias") is None:
        print(f"ATENÇÃO: {frete.get('motivo')}. Valem as datas da regra anterior (sem o prazo da transportadora).")
        return p
    print(f"Frete: {frete['detalhe']} | logística: {LOGISTICA_DIAS_UTEIS} dias úteis")
    print(f"Embarque máximo (card da Logística): {br(p['embarque'])}"
          f"{'  <<< ATRASADO' if p['embarque_atrasado'] else ''}")
    print(f"Prazo dos fornecedores (OCs e card da Fábrica): {br(p['fornecedores'])}"
          f"{'  <<< ATRASADO' if p['fornecedores_atrasado'] else ''}")
    if p["sem_folga"]:
        print("ATENÇÃO: o prazo combinado não cobre frete + logística: não sobra prazo para os fornecedores.")
    return p


def texto_itens_logistica(pedido, ocs, separador=", "):
    """Itens do pedido para o card da Logística, cada um com a origem no fim:
    '6x Cadeira Lina (Estoque), 1x Mesa Aurora (OC 1234)'.
    Item comprado em mais de uma OC (ex.: tampo e base): '(OC 1234, OC 1235)'.
    Item do estoque com personalização na fábrica: '(Estoque, personalização OC 1236)'."""
    rotulos = []
    for i, item in enumerate(pedido.get("itens", [])):
        def ocs_do_item(personalizacao):
            return [oc for oc in ocs if any(it.get("origem_pedido") == i
                                            and bool(it.get("personalizacao_linha")) == personalizacao
                                            for it in oc.get("itens", []))]
        compras = ocs_do_item(False)
        so_personalizacao = [oc for oc in ocs_do_item(True) if oc not in compras]
        partes = [f"OC {oc['numero']}" for oc in compras] or ["Estoque"]
        partes += [f"personalização OC {oc['numero']}" for oc in so_personalizacao]
        rotulos.append(f"{rotulo_loja(item)} ({', '.join(partes)})")
    return separador.join(rotulos)


# ---------------------------------------------------------------------------
# CHECKLIST DE SEPARAÇÃO NO CARD DA LOGÍSTICA (atualizada pelo Assistente)
# ---------------------------------------------------------------------------
# Os itens ficam SEMPRE desmarcados: quem marca é a equipe. O Assistente só reescreve o texto
# ao lado de cada peça: "Estoque", "OC 601 · GAL · prev. 25/10", "OC 601 · GAL · 2 dias de atraso",
# "OC 602 recebida". O vínculo item <-> OC fica no acompanhamento_trello.json (pasta do programa).

ARQUIVO_ACOMPANHAMENTO = "acompanhamento_trello.json"
SITUACAO_OC = {0: "aberta", 1: "recebida", 2: "cancelada", 3: "em andamento"}  # pedidos de compra do Bling


def fornecedor_curto(nome):
    """Nome da fábrica -> 'Fábrica'; 'Metalúrgica Aurora Ltda - ME' -> 'Metalúrgica Aurora'."""
    if e_fabrica(nome):
        return "Fábrica"
    nome = re.sub(r"\b(LTDA|ME|EPP|EIRELI|S/?A)\b\.?", "", str(nome or ""), flags=re.IGNORECASE)
    palavras = re.sub(r"[-–,&]+", " ", nome).split()
    return " ".join(palavras[:2]) or "fornecedor"


def dias_uteis_de_atraso(data_prevista, hoje=None):
    """Dias úteis depois da data prevista até hoje (0 se ainda não passou)."""
    hoje = hoje or date.today()
    dias, dia = 0, data_prevista
    while dia < hoje:
        dia += timedelta(days=1)
        if e_dia_util(dia):
            dias += 1
    return dias


def texto_status_peca(oc_numero=None, fornecedor="", data_prevista=None, situacao=0, hoje=None):
    """O que vai ao lado da peça na checklist."""
    if oc_numero is None:
        return "Estoque"
    if situacao == 1:
        return f"OC {oc_numero} recebida"
    if situacao == 2:
        return f"OC {oc_numero} cancelada"
    if data_prevista:
        prevista = datetime.strptime(str(data_prevista)[:10], "%Y-%m-%d").date()
        atraso = dias_uteis_de_atraso(prevista, hoje)
        if atraso:
            return f"OC {oc_numero} · {fornecedor} · {atraso} {'dia' if atraso == 1 else 'dias'} de atraso"
        return f"OC {oc_numero} · {fornecedor} · prev. {prevista.strftime('%d/%m')}"
    return f"OC {oc_numero} · {fornecedor}"


def pecas_da_checklist(ctx, ocs):
    """Uma entrada por peça física (componentes de produto estruturado separados) + personalizações.
    Cada entrada: {'nome', 'oc_id', 'oc_numero', 'fornecedor', 'data_prevista'} (oc_* None = estoque)."""
    pecas = ctx.get("itens") or levantar_itens(ctx["pedido"], buscar_fornecedor=False)
    entradas = []
    for peca in pecas:
        oc_da_peca, item_oc = None, None
        for oc in ocs:
            for it in oc.get("itens", []):
                if (not it.get("personalizacao_linha") and it.get("origem_pedido") == peca.get("origem_pedido")
                        and it.get("produto_id") == peca.get("produto_id") and it.get("codigo") == peca.get("codigo")):
                    oc_da_peca, item_oc = oc, it
        nome = rotulo_loja(item_oc or peca)  # nome da Tray; componente: '(peça: ...)'
        entradas.append({"nome": nome, "nome_fornecedor": rotulo_no_fornecedor(item_oc or peca),
                         **dados_oc_da_peca(oc_da_peca)})
    for oc in ocs:
        for it in oc.get("itens", []):
            if it.get("personalizacao_linha"):
                nome = (f"Personalização: {formatar_quantidade(it['quantidade'])}x "
                        f"{it.get('nome_tray') or nome_curto(it['produto_ref'])}: {it['personalizacao_texto']}")
                entradas.append({"nome": nome, **dados_oc_da_peca(oc)})
    return entradas


def rotulo_no_fornecedor(item):
    """Como o FORNECEDOR conhece o produto: '1x BASE PRETA 70CM (cód. MA-4410)'.
    Sem descrição do fornecedor no Bling, usa o nome da loja; sem código, não mostra o código."""
    nome = item.get("fornecedor_descricao") or nome_curto(item.get("descricao", ""))
    codigo = item.get("fornecedor_codigo")
    return f"{formatar_quantidade(item.get('quantidade', 1))}x {nome}" + (f" (cód. {codigo})" if codigo else "")


def dados_oc_da_peca(oc):
    if oc is None:
        return {"oc_id": None, "oc_numero": None, "fornecedor": "", "data_prevista": None}
    return {"oc_id": oc.get("id"), "oc_numero": oc.get("numero"), "fornecedor": fornecedor_curto(oc.get("fornecedor_nome")),
            "data_prevista": oc.get("data_prevista"), "fornecedor_id": oc.get("fornecedor_id"),
            "fornecedor_nome": oc.get("fornecedor_nome")}


def texto_item_checklist(entrada, situacao=0, hoje=None):
    status = texto_status_peca(entrada["oc_numero"], entrada["fornecedor"], entrada["data_prevista"], situacao, hoje)
    return f"{entrada['nome']} — {status}"


def _trello(metodo, caminho, **kwargs):
    if MODO_DEMO:
        import demo
        return demo.trello(metodo, caminho, **kwargs)
    import requests
    resposta = requests.request(metodo, f"{TRELLO_BASE_URL}{caminho}", headers=trello_auth(), timeout=30, **kwargs)
    checar_trello(resposta, f"{metodo} {caminho.split('?')[0]}")
    return resposta.json() if resposta.text else {}


def _caminho_acompanhamento():
    from configuracao import pasta_base
    return os.path.join(pasta_base(), ARQUIVO_ACOMPANHAMENTO)


def carregar_acompanhamento():
    import json
    try:
        with open(_caminho_acompanhamento(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return []


def salvar_acompanhamento(registros):
    import json
    caminho = _caminho_acompanhamento()
    with open(caminho + ".tmp", "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)
    os.replace(caminho + ".tmp", caminho)


def nome_checklist_separacao(numero_tray):
    return (f"Separação · pedido {numero_tray} — Clique no quadrado para confirmar o estoque de cada produto. "
            "O que estiver desmarcado ainda não chegou.")


def adicionar_checklist_logistica(card_id, link, ctx, ocs):
    """Cria a checklist de separação no card (itens desmarcados) e guarda o vínculo com as OCs.
    Nunca derruba o fluxo: em caso de erro, só avisa."""
    try:
        entradas = pecas_da_checklist(ctx, ocs)
        if not entradas:
            return
        checklist = _trello("POST", f"/cards/{card_id}/checklists",
                            data={"name": nome_checklist_separacao(ctx["numero_tray"])})
        itens = []
        for entrada in entradas:
            texto = texto_item_checklist(entrada)
            item = _trello("POST", f"/checklists/{checklist['id']}/checkItems",
                           data={"name": texto, "checked": "false", "pos": "bottom"})
            itens.append({**entrada, "check_id": item["id"], "texto": texto})
        if any(i["oc_id"] for i in itens):
            registros = carregar_acompanhamento()
            registros.append({"card_id": card_id, "link": link, "pedido": ctx["numero_tray"],
                              "criado": date.today().isoformat(),
                              "embarque": (ctx.get("data_embarque") or "")[:10] or None,  # data do card da Logística
                              # prazo pela tabela da transportadora: a régua usa a data da OC (prazo do fornecedor)
                              "regua_pela_oc": bool((ctx.get("prazos") or {}).get("fornecedores")),
                              "itens": itens})
            salvar_acompanhamento(registros)
        print(f"Checklist de separação criada no card ({len(itens)} itens).")
        try:  # nasce sem nada marcado: já sai com a etiqueta 'Responder checklist'
            id_quadro = _trello("GET", f"/cards/{card_id}", params={"fields": "idBoard"})["idBoard"]
            existentes = _trello("GET", f"/boards/{id_quadro}/labels", params={"fields": "name,color", "limit": 1000})
            etiqueta = _etiqueta(id_quadro, *ETIQUETA_RESPONDER, existentes)
            _trello("POST", f"/cards/{card_id}/idLabels", data={"value": etiqueta})
        except Exception as erro:
            print(f"ATENÇÃO: não consegui pôr a etiqueta 'Responder checklist' no card ({erro}).")
    except Exception as erro:
        print(f"ATENÇÃO: o card foi criado, mas não consegui criar a checklist de separação ({erro}).")


def atualizar_checklists(hoje=None):
    """Atualiza os cards acompanhados. Trello primeiro, Bling como reserva:
      - item MARCADO no Trello pela equipe = peça chegou: sai da régua de cobrança (o texto não muda mais);
      - data (due) do card da Logística = data de embarque da régua (se alguém mudar no Trello, vale a nova);
      - para o que não foi marcado, confere a OC no Bling (recebida/cancelada/data prevista) e reescreve
        só o texto dos itens que mudaram. Nunca marca nem desmarca nada. Devolve um resumo em texto."""
    registros = carregar_acompanhamento()
    if not registros:
        return "Nenhum card com OC em acompanhamento."
    alterados, pendentes, chegaram, restantes = 0, 0, 0, []
    situacoes = {}
    for registro in registros:
        try:
            card = _trello("GET", f"/cards/{registro['card_id']}",
                           params={"fields": "closed,due", "checklists": "all"})
        except RuntimeError as erro:
            if "404" in str(erro):  # card apagado: para de acompanhar
                continue
            restantes.append(registro)
            continue
        if card.get("closed"):  # card arquivado: para de acompanhar
            continue
        if card.get("due"):
            registro["embarque"] = str(card["due"])[:10]
        marcados = {ci.get("id") for cl in card.get("checklists") or [] for ci in cl.get("checkItems") or []
                    if ci.get("state") == "complete"}
        for item in registro["itens"]:
            if not item.get("oc_id") or item.get("finalizado"):
                continue
            if item.get("check_id") in marcados:  # a equipe marcou: chegou
                item["finalizado"] = True
                item["chegou_pelo_trello"] = True
                chegaram += 1
                continue
            if item["oc_id"] not in situacoes:
                try:
                    oc = chamar_bling("GET", f"/pedidos/compras/{item['oc_id']}").get("data", {})
                    situacoes[item["oc_id"]] = ((oc.get("situacao") or {}).get("valor", 0), oc.get("dataPrevista"))
                except Exception:
                    situacoes[item["oc_id"]] = None
            dados = situacoes[item["oc_id"]]
            if dados is None:
                pendentes += 1
                continue
            situacao, prevista = dados
            if prevista and prevista != "0000-00-00":
                item["data_prevista"] = prevista  # a data pode ter sido mudada no Bling
            novo = texto_item_checklist(item, situacao, hoje)
            if novo != item.get("texto"):
                _trello("PUT", f"/cards/{registro['card_id']}/checkItem/{item['check_id']}", data={"name": novo})
                item["texto"] = novo
                alterados += 1
            if situacao in (1, 2):
                item["finalizado"] = True
            else:
                pendentes += 1
        if any(i.get("oc_id") and not i.get("finalizado") for i in registro["itens"]):
            restantes.append(registro)
    salvar_acompanhamento(restantes)
    return (f"Checklists conferidas: {alterados} {'item atualizado' if alterados == 1 else 'itens atualizados'}, "
            f"{chegaram} {'marcado' if chegaram == 1 else 'marcados'} como chegou no Trello, "
            f"{pendentes} aguardando OC, {len(restantes)} {'card' if len(restantes) == 1 else 'cards'} em acompanhamento.")


# ---------------------------------------------------------------------------
# TEMPO NA LISTA "A SEPARAR" DA LOGÍSTICA
# ---------------------------------------------------------------------------
# Mede há quantos dias úteis cada card está na lista onde o Assistente cria os cards (lista_logistica_id,
# "A Separar"). Os que passaram de DIAS_UTEIS_PARADO sobem para o topo, o mais antigo primeiro, para a
# equipe adiantar. Os demais ficam na ordem em que estavam, abaixo deles.

DIAS_UTEIS_PARADO = 2
_ACOES_ENTRADA = "createCard,updateCard:idList,copyCard,convertToCardFromCheckItem,moveCardToBoard"


def _data_trello(texto):
    return datetime.strptime(texto[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).astimezone().date()


def entrada_na_lista(card_id, lista_id):
    """Dia em que o card entrou na lista (criado nela ou movido para ela)."""
    acoes = _trello("GET", f"/cards/{card_id}/actions", params={"filter": _ACOES_ENTRADA, "limit": 50})
    for acao in acoes:  # do mais recente para o mais antigo
        depois = ((acao.get("data") or {}).get("listAfter") or {}).get("id")
        if acao.get("type") != "updateCard" or depois == lista_id:
            return _data_trello(acao["date"])
    # sem histórico: usa a data de criação do card (vem embutida no id do Trello)
    return datetime.fromtimestamp(int(card_id[:8], 16)).date()


def organizar_a_separar(aplicar=True, hoje=None, limite=DIAS_UTEIS_PARADO):
    """Mede o tempo dos cards na lista A Separar e sobe para o topo os parados há mais de `limite` dias úteis.
    Com aplicar=False só mostra o que faria. Devolve um resumo (dict)."""
    hoje = hoje or date.today()
    lista_id = config()["trello"]["lista_logistica_id"]
    cards = _trello("GET", f"/lists/{lista_id}/cards", params={"fields": "name,pos,idLabels", "checklists": "all"})
    for card in cards:
        card["dias"] = dias_uteis_de_atraso(entrada_na_lista(card["id"], lista_id), hoje)
    parados = sorted((c for c in cards if c["dias"] > limite), key=lambda c: -c["dias"])
    ordem_desejada = [c["id"] for c in parados] + [c["id"] for c in cards if c["dias"] <= limite]
    ja_ordenado = [c["id"] for c in cards] == ordem_desejada
    movidos, etiquetados, desetiquetados = 0, 0, 0
    if aplicar and not ja_ordenado:
        for card in reversed(parados):  # o último a subir fica no topo: o mais antigo
            _trello("PUT", f"/cards/{card['id']}", data={"pos": "top"})
            movidos += 1
    if aplicar:
        try:  # a etiqueta é um extra: um erro nela não pode derrubar a medição nem a ordenação
            etiquetados, desetiquetados = _etiquetar_parados(lista_id, cards, limite)
        except Exception as erro:
            print(f"ATENÇÃO: não consegui atualizar a etiqueta de parados no Trello ({erro}).")
    return {"total": len(cards), "parados": parados, "movidos": movidos, "ja_ordenado": ja_ordenado,
            "mais_antigo": parados[0] if parados else None, "limite": limite,
            "responder": [c for c in cards if precisa_responder_checklist(c)],
            "etiquetados": etiquetados, "desetiquetados": desetiquetados}


ETIQUETA_RESPONDER = ("Responder checklist", "yellow")


def _etiqueta(id_quadro, nome, cor, etiquetas_do_quadro):
    """Id da etiqueta com esse nome no quadro (cria na primeira vez)."""
    for etiqueta in etiquetas_do_quadro:
        if etiqueta.get("name") == nome:
            return etiqueta["id"]
    nova = _trello("POST", "/labels", data={"name": nome, "color": cor, "idBoard": id_quadro})
    etiquetas_do_quadro.append({"id": nova["id"], "name": nome, "color": cor})
    return nova["id"]


def precisa_responder_checklist(card, limite=None):
    """Card com a checklist de separação do Assistente sem NENHUM item marcado (vale desde a criação do card,
    não depende de estar parado)."""
    separacao = [cl for cl in card.get("checklists") or [] if str(cl.get("name", "")).startswith("Separação")]
    itens = [ci for cl in separacao for ci in cl.get("checkItems") or []]
    return bool(itens) and not any(ci.get("state") == "complete" for ci in itens)


def _etiquetar_parados(lista_id, cards_da_lista, limite):
    """Etiquetas nos cards da lista A Separar:
      - 'Parado há +N dias úteis' (vermelha): nos parados;
      - 'Responder checklist' (amarela): em todo card com a checklist de separação sem nada marcado.
    Tira as duas dos que deixaram de se encaixar e dos que saíram da lista. Devolve (postas, retiradas)."""
    id_quadro = _trello("GET", f"/lists/{lista_id}", params={"fields": "idBoard"})["idBoard"]
    existentes = _trello("GET", f"/boards/{id_quadro}/labels", params={"fields": "name,color", "limit": 1000})
    regras = [
        (_etiqueta(id_quadro, f"Parado há +{limite} dias úteis", "red", existentes), lambda c: c["dias"] > limite),
        (_etiqueta(id_quadro, *ETIQUETA_RESPONDER, existentes), lambda c: precisa_responder_checklist(c, limite)),
    ]
    pos, tirou = 0, 0
    for card in cards_da_lista:
        for etiqueta, deve_ter in regras:
            tem = etiqueta in (card.get("idLabels") or [])
            if deve_ter(card) and not tem:
                _trello("POST", f"/cards/{card['id']}/idLabels", data={"value": etiqueta})
                pos += 1
            elif not deve_ter(card) and tem:
                _trello("DELETE", f"/cards/{card['id']}/idLabels/{etiqueta}")
                tirou += 1
    # cards que saíram da lista (ex.: foram para a transportadora) não ficam com essas etiquetas
    nossas = {etiqueta for etiqueta, _ in regras}
    for card in _trello("GET", f"/boards/{id_quadro}/cards", params={"fields": "idList,idLabels"}):
        if card.get("idList") != lista_id:
            for etiqueta in nossas & set(card.get("idLabels") or []):
                _trello("DELETE", f"/cards/{card['id']}/idLabels/{etiqueta}")
                tirou += 1
    return pos, tirou


def resumo_a_separar(resultado):
    if not resultado["total"]:
        return "A Separar: nenhum card."
    texto = (f"A Separar: {resultado['total']} cards, {len(resultado['parados'])} parados há mais de "
             f"{resultado['limite']} dias úteis")
    if resultado["mais_antigo"]:
        texto += f" (o mais antigo há {resultado['mais_antigo']['dias']} dias úteis)"
    if resultado.get("responder"):
        n = len(resultado["responder"])
        texto += f"; {n} {'precisa' if n == 1 else 'precisam'} responder a checklist"
    if resultado["movidos"]:
        texto += f"; {resultado['movidos']} subiram para o topo"
    if resultado.get("etiquetados"):
        texto += f"; etiqueta posta em {resultado['etiquetados']}"
    if resultado.get("desetiquetados"):
        texto += f"; etiqueta retirada de {resultado['desetiquetados']}"
    return texto + "."


# ---------------------------------------------------------------------------
# RÉGUA DE MENSAGENS AOS FORNECEDORES (WhatsApp)
# ---------------------------------------------------------------------------
# Base: data de embarque do card da Logística (dias úteis combinados - 10). Dias úteis, sem fim de semana.
#   faltando 14 dias úteis -> lembrete | faltando 7 -> confirmação | do dia do embarque em diante -> 1 cobrança
#   por dia útil, até a OC ser marcada como Atendida no Bling. Se a etapa passou num dia em que o Assistente
#   não foi aberto, ela sai no próximo dia útil (uma vez só). O que já foi enviado fica em mensagens_enviadas.json.

ARQUIVO_MENSAGENS = "mensagens_enviadas.json"
MODELOS_MENSAGEM = {
    "14": ("Olá, {fornecedor}! Tudo bem? Aqui é da {loja}. A OC {oc} (pedido {pedido}) tem embarque "
           "previsto para {data}. Itens: {itens}. Pode nos confirmar se está dentro do prazo? Obrigado!"),
    "7": ("Olá, {fornecedor}! Faltam 7 dias úteis para o embarque da OC {oc} (pedido {pedido}), previsto para "
          "{data}. Itens: {itens}. Está tudo certo com o prazo?"),
    "hoje": ("Olá, {fornecedor}! Hoje é a data de embarque da OC {oc} (pedido {pedido}). Itens: {itens}. "
             "A mercadoria já foi enviada?"),
    "atraso": ("Olá, {fornecedor}! A OC {oc} (pedido {pedido}) tinha embarque previsto para {data} e ainda não "
               "consta como recebida ({atraso}). Itens: {itens}. Qual a nova previsão?"),
}
ROTULO_ETAPA = {"14": "Faltam 14 dias úteis", "7": "Faltam 7 dias úteis", "hoje": "Dia do embarque",
                "atraso": "Em atraso"}


def dias_uteis_ate(hoje, alvo):
    """Dias úteis de hoje até a data alvo (positivo = ainda falta; 0 = é hoje; negativo = já passou)."""
    if alvo >= hoje:
        dias, dia = 0, hoje
        while dia < alvo:
            dia += timedelta(days=1)
            if e_dia_util(dia):
                dias += 1
        return dias
    return -dias_uteis_de_atraso(alvo, hoje)


def etapa_da_regua(embarque, hoje, ja_enviadas):
    """Etapa a mandar hoje para uma OC, ou None. ja_enviadas: chaves de etapas já mandadas para essa OC."""
    if not e_dia_util(hoje):
        return None
    faltam = dias_uteis_ate(hoje, embarque)
    if faltam > 14:
        return None
    if faltam > 7:
        return None if "14" in ja_enviadas else "14"
    if faltam > 0:
        return None if "7" in ja_enviadas else "7"
    etapa = "hoje" if faltam == 0 else "atraso"
    return None if f"{etapa}:{hoje.isoformat()}" in ja_enviadas else etapa


def _caminho_mensagens():
    from configuracao import pasta_base
    return os.path.join(pasta_base(), ARQUIVO_MENSAGENS)


def carregar_mensagens_enviadas():
    import json
    try:
        with open(_caminho_mensagens(), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def registrar_mensagem_enviada(mensagem):
    """Anota que a mensagem foi enviada (não volta a aparecer)."""
    import json
    enviadas = carregar_mensagens_enviadas()
    enviadas.setdefault(str(mensagem["oc_id"]), []).append(mensagem["chave"])
    caminho = _caminho_mensagens()
    with open(caminho + ".tmp", "w", encoding="utf-8") as f:
        json.dump(enviadas, f, ensure_ascii=False, indent=2)
    os.replace(caminho + ".tmp", caminho)


def normalizar_whatsapp(numero):
    """'(11) 98765-4321' -> '5511987654321'. Devolve '' se não parecer um celular/telefone."""
    digitos = re.sub(r"\D", "", str(numero or ""))
    if digitos.startswith("0"):
        digitos = digitos.lstrip("0")
    if len(digitos) in (10, 11):
        digitos = "55" + digitos
    return digitos if len(digitos) in (12, 13) and digitos.startswith("55") else ""


_cache_whatsapp = {}


def whatsapp_do_fornecedor(fornecedor_id):
    """Número do WhatsApp: config.json (whatsapp_fornecedores: {"id do contato": "número"}) ou o celular
    (senão o telefone) do contato no Bling. '' se não houver."""
    chave = str(fornecedor_id)
    if chave not in _cache_whatsapp:
        try:
            manual = (config().get("whatsapp_fornecedores") or {}).get(chave)
        except Exception:
            manual = None
        numero = normalizar_whatsapp(manual) if manual else ""
        if not numero and fornecedor_id:
            try:
                contato = chamar_bling("GET", f"/contatos/{fornecedor_id}").get("data", {})
                numero = normalizar_whatsapp(contato.get("celular")) or normalizar_whatsapp(contato.get("telefone"))
            except Exception:
                numero = ""
        _cache_whatsapp[chave] = numero
    return _cache_whatsapp[chave]


def mensagens_do_dia(hoje=None, buscar_whatsapp=True):
    """Mensagens a mandar hoje, uma por OC em aberto. Use depois de atualizar_checklists()
    (que tira do acompanhamento as OCs já recebidas)."""
    hoje = hoje or date.today()
    enviadas = carregar_mensagens_enviadas()
    mensagens = []
    for registro in carregar_acompanhamento():
        por_oc = {}
        for item in registro.get("itens", []):
            if item.get("oc_id") and not item.get("finalizado"):
                por_oc.setdefault(item["oc_id"], []).append(item)
        for oc_id, itens in por_oc.items():
            primeiro = itens[0]
            if registro.get("regua_pela_oc"):  # pedidos com prazo pela tabela: o fornecedor entrega na data da OC
                base = primeiro.get("data_prevista") or registro.get("embarque")
            else:
                base = registro.get("embarque") or primeiro.get("data_prevista")
            if not base:
                continue
            embarque = datetime.strptime(str(base)[:10], "%Y-%m-%d").date()
            etapa = etapa_da_regua(embarque, hoje, enviadas.get(str(oc_id), []))
            if etapa is None:
                continue
            atraso = dias_uteis_de_atraso(embarque, hoje)
            # Itens como o fornecedor conhece (nome e código dele); personalização vai como está
            nomes = "; ".join(i.get("nome_fornecedor") or re.sub(r"^Personalização: ", "personalização ", i["nome"])
                              for i in itens)
            fornecedor = primeiro.get("fornecedor") or "fornecedor"
            texto = MODELOS_MENSAGEM[etapa].format(loja=nome_loja(), 
                fornecedor=fornecedor, oc=primeiro.get("oc_numero"), pedido=registro.get("pedido"),
                data=embarque.strftime("%d/%m/%Y"), itens=nomes,
                atraso=f"{atraso} {'dia útil' if atraso == 1 else 'dias úteis'} de atraso")
            mensagens.append({
                "oc_id": oc_id, "oc_numero": primeiro.get("oc_numero"), "pedido": registro.get("pedido"),
                "fornecedor": fornecedor, "fornecedor_nome": primeiro.get("fornecedor_nome") or fornecedor,
                "whatsapp": whatsapp_do_fornecedor(primeiro.get("fornecedor_id")) if buscar_whatsapp else "",
                "etapa": etapa, "rotulo": ROTULO_ETAPA[etapa], "embarque": embarque.isoformat(), "texto": texto,
                "chave": etapa if etapa in ("14", "7") else f"{etapa}:{hoje.isoformat()}",
            })
    return mensagens


# ---------------------------------------------------------------------------
# RÉGUA DE MENSAGENS À LOGÍSTICA (WhatsApp) - mesmo esquema da dos fornecedores
# ---------------------------------------------------------------------------
# Base: a data (due) dos cards da lista A Separar (lista_logistica_id) = data máxima de embarque.
#   faltando 2 dias úteis -> lembrete | no dia -> aviso | depois -> 1 cobrança por dia útil enquanto o card
#   continuar em A Separar com a data não concluída. Card concluído (data marcada como feita) ou que saiu da
#   lista não recebe mais nada. Número: "whatsapp_logistica" no config.json. Também fica em mensagens_enviadas.json.

DIAS_UTEIS_AVISO_LOGISTICA = 2
MODELOS_LOGISTICA = {
    "2": ("Olá, equipe da Logística! O pedido {pedido} tem embarque máximo em {data} ({falta}). "
          "Card: {titulo}{separacao}. {link} Está tudo certo para embarcar no prazo?"),
    "hoje": ("Olá, equipe da Logística! HOJE ({data}) é a data máxima de embarque do pedido {pedido}. "
             "Card: {titulo}{separacao}. {link} O pedido já foi embarcado?"),
    "atraso": ("Olá, equipe da Logística! O pedido {pedido} tinha embarque máximo em {data} e o card ainda "
               "está em A Separar ({atraso}). Card: {titulo}{separacao}. {link} Qual a nova previsão?"),
}
ROTULO_LOGISTICA = {"2": "Faltam 2 dias úteis", "hoje": "Dia do embarque", "atraso": "Embarque em atraso"}


def etapa_logistica(embarque, hoje, ja_enviadas, aviso=DIAS_UTEIS_AVISO_LOGISTICA):
    """Etapa a mandar hoje para um card da Logística, ou None (como etapa_da_regua)."""
    if not e_dia_util(hoje):
        return None
    faltam = dias_uteis_ate(hoje, embarque)
    if faltam > aviso:
        return None
    if faltam > 0:
        return None if "2" in ja_enviadas else "2"
    etapa = "hoje" if faltam == 0 else "atraso"
    return None if f"{etapa}:{hoje.isoformat()}" in ja_enviadas else etapa


def _separacao_do_card(card):
    """' | separação: 1 de 3 itens confirmados' (checklist do Assistente), ou ''."""
    itens = [ci for cl in card.get("checklists") or [] if str(cl.get("name", "")).startswith("Separação")
             for ci in cl.get("checkItems") or []]
    if not itens:
        return ""
    feitos = sum(ci.get("state") == "complete" for ci in itens)
    return f" | separação: {feitos} de {len(itens)} itens confirmados"


def mensagens_logistica(hoje=None):
    """Mensagens a mandar hoje para a Logística, uma por card de A Separar perto ou além da data."""
    hoje = hoje or date.today()
    c = config()
    lista_id = c["trello"]["lista_logistica_id"]
    whatsapp = normalizar_whatsapp(c.get("whatsapp_logistica"))
    enviadas = carregar_mensagens_enviadas()
    cards = _trello("GET", f"/lists/{lista_id}/cards",
                    params={"fields": "name,due,dueComplete,shortUrl", "checklists": "all"})
    mensagens = []
    for card in cards:
        if not card.get("due") or card.get("dueComplete"):
            continue
        embarque = _data_trello(card["due"])
        chave_card = f"logistica:{card['id']}"
        etapa = etapa_logistica(embarque, hoje, enviadas.get(chave_card, []))
        if etapa is None:
            continue
        numero = (re.search(r"(?i)\bPed(?:ido)?\.?\s*(\d{4,})", card.get("name") or "")
                  or re.search(r"\b(\d{6})\b", card.get("name") or ""))
        pedido = numero.group(1) if numero else "-"
        faltam = dias_uteis_ate(hoje, embarque)
        atraso = dias_uteis_de_atraso(embarque, hoje)
        titulo = re.sub(r"(?i)^(ATRASADO - )?Ped(ido)?\.?\s*\d+\s*-\s*", "", card.get("name") or "")
        texto = MODELOS_LOGISTICA[etapa].format(
            pedido=pedido, data=embarque.strftime("%d/%m/%Y"), titulo=titulo, link=card.get("shortUrl") or "",
            separacao=_separacao_do_card(card),
            falta=f"falta {faltam} dia útil" if faltam == 1 else f"faltam {faltam} dias úteis",
            atraso=f"{atraso} {'dia útil' if atraso == 1 else 'dias úteis'} de atraso")
        mensagens.append({
            "tipo": "logistica", "oc_id": chave_card, "oc_numero": None, "pedido": pedido,
            "fornecedor": "Logística", "fornecedor_nome": "Logística", "whatsapp": whatsapp,
            "etapa": etapa, "rotulo": ROTULO_LOGISTICA[etapa], "embarque": embarque.isoformat(), "texto": texto,
            "chave": etapa if etapa == "2" else f"{etapa}:{hoje.isoformat()}", "link": card.get("shortUrl"),
        })
    return mensagens


# ---- Histórico de envios (log permanente: uma linha JSON por envio, só cresce) ----

ARQUIVO_HISTORICO = "historico_mensagens.jsonl"


def _caminho_historico():
    from configuracao import pasta_base
    return os.path.join(pasta_base(), ARQUIVO_HISTORICO)


def registrar_historico(mensagem, canal, modo, destino, resultado, motivo=""):
    """Anota um envio (ou tentativa) no histórico. canal: 'WhatsApp automático' / 'WhatsApp manual';
    modo: 'teste' / 'real'; resultado: 'enviada' / 'falhou'."""
    import json
    linha = {
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "canal": canal, "modo": modo, "resultado": resultado, "motivo": motivo,
        "fornecedor": mensagem.get("fornecedor_nome") or mensagem.get("fornecedor", ""),
        "destino": destino or "", "oc": mensagem.get("oc_numero") or ("card" if mensagem.get("tipo") == "logistica" else ""),
        "pedido": mensagem.get("pedido"),
        "etapa": mensagem.get("rotulo") or ROTULO_ETAPA.get(mensagem.get("etapa"), mensagem.get("etapa", "")),
        "texto": mensagem.get("texto", ""),
    }
    with open(_caminho_historico(), "a", encoding="utf-8") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")


def carregar_historico(limite=None):
    """Envios do mais recente para o mais antigo."""
    import json
    try:
        with open(_caminho_historico(), "r", encoding="utf-8") as f:
            linhas = [json.loads(l) for l in f if l.strip()]
    except FileNotFoundError:
        return []
    linhas.reverse()
    return linhas[:limite] if limite else linhas


def exportar_historico_csv(caminho=None):
    """Salva o histórico em CSV (abre direto no Excel) e devolve o caminho."""
    import csv
    from configuracao import pasta_base
    caminho = caminho or os.path.join(pasta_base(), "historico_mensagens.csv")
    colunas = [("data_hora", "Data e hora"), ("resultado", "Resultado"), ("motivo", "Motivo"), ("modo", "Modo"),
               ("canal", "Canal"), ("fornecedor", "Fornecedor"), ("destino", "WhatsApp"), ("oc", "OC"),
               ("pedido", "Pedido"), ("etapa", "Etapa"), ("texto", "Mensagem")]
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow([titulo for _, titulo in colunas])
        for linha in carregar_historico():
            escritor.writerow([linha.get(chave, "") for chave, _ in colunas])
    return caminho


def link_whatsapp(mensagem):
    """Abre a conversa com o texto já escrito (a pessoa só aperta enviar)."""
    from urllib.parse import quote
    return f"https://wa.me/{mensagem['whatsapp']}?text={quote(mensagem['texto'])}"


# ---------------------------------------------------------------------------
# FICHAS (imagens) PARA OS CARDS, NO LUGAR DOS PRINTS MANUAIS
# ---------------------------------------------------------------------------

def _data_br(texto):
    texto = str(texto or "")[:10]
    return f"{texto[8:10]}/{texto[5:7]}/{texto[:4]}" if len(texto) == 10 and not texto.startswith("0000") else ""


def baixar_imagem(url, ctx=None, limite=4_000_000):
    """Foto do produto (CDN da loja). Guardada no ctx para não baixar duas vezes. None se não der."""
    if not url:
        return None
    cache = ctx.setdefault("_fotos", {}) if ctx is not None else {}
    if url not in cache:
        cache[url] = None
        if MODO_DEMO:
            import demo
            cache[url] = demo.foto(url)
            return cache[url]
        try:
            import requests
            resposta = requests.get(url, timeout=15)
            if resposta.ok and resposta.headers.get("content-type", "").startswith("image/") \
                    and len(resposta.content) <= limite:
                cache[url] = resposta.content
        except Exception:
            pass
    return cache[url]


def partes_nome_tray(nome):
    """'Nome (Ref. X)<br><strong>Cor</strong> Azul' -> ('Nome', 'Cor: Azul')."""
    partes = re.split(r"(?i)<br\s*/?>", str(nome or ""), maxsplit=1)
    titulo = unescape(re.sub(r"<[^>]+>", "", partes[0]))
    titulo = " ".join(nome_curto(re.sub(r"\s*\(Ref\.[^)]*\)", "", titulo)).split())
    return titulo, (limpar_nome_tray(partes[1]) if len(partes) > 1 else "")


def _rotulo_ocs_do_item(indice_bling, ocs):
    """'OC 601 · OC 602', 'Estoque', ou None se não deu para ligar o item da Tray ao do Bling."""
    if indice_bling is None:
        return None
    compras = [oc for oc in ocs if any(it.get("origem_pedido") == indice_bling and not it.get("personalizacao_linha")
                                       for it in oc.get("itens", []))]
    pers = [oc for oc in ocs if oc not in compras and any(it.get("origem_pedido") == indice_bling
                                                          and it.get("personalizacao_linha") for it in oc.get("itens", []))]
    partes = [f"OC {oc['numero']}" for oc in compras] or ["Estoque"]
    partes += [f"Pers. OC {oc['numero']}" for oc in pers]
    return " · ".join(partes)


def _linhas_do_html(h):
    """O que foi preenchido no HTML do pedido, no formato da ficha: [(rótulo, valor, em destaque)]."""
    if not h:
        return []
    extras, pj = h.get("extras") or {}, h.get("tipo") == "J"
    linhas = []
    if pj:
        linhas += [("Pedido faturado", f"{extras['faturado']} dias" if extras.get("faturado") else "-", True),
                   ("Checklist realizado?", extras.get("checklist") or "-", True)]
    linhas.append(("Data combinada", f"{h['dias']} dias úteis", True))
    linhas.append(("Personalização", "; ".join(h.get("personalizacao") or []) or "-", False))
    if pj:
        linhas.append(("Pasta", extras.get("pasta") or "-", False))
    linhas += [("Data para embarque máxima", h["embarque"].strftime("%d/%m/%Y"), True),
               ("Data prevista para entrega", h["entrega"].strftime("%d/%m/%Y"), True)]
    if pj:
        linhas.append(("Informações adicionais de nota fiscal", extras.get("info_nf") or "-", False))
    return linhas


def _pedido_tray_completo(ctx):
    if "_pedido_tray" not in ctx:
        modulo = tray()
        ctx["_pedido_tray"] = modulo.pedido_completo(ctx["numero_tray"]) if modulo else None
    return ctx["_pedido_tray"]


def dados_ficha_pedido(ctx, ocs, transportadora):
    """Dados da ficha do pedido (card da Logística), da Tray + OCs + HTML. Sem CPF/CNPJ, e-mail ou valores."""
    o = _pedido_tray_completo(ctx)
    if not o:
        raise RuntimeError("a Tray não está configurada")
    cliente = o.get("Customer") or {}
    enderecos = [(e.get("CustomerAddress") or e) for e in cliente.get("CustomerAddresses") or []]
    entrega = (next((e for e in enderecos if str(e.get("type_delivery")) == "1"), None)
               or next((e for e in enderecos if str(e.get("active")) == "1"), None) or (enderecos[0] if enderecos else {}))
    rua = ", ".join(x for x in (entrega.get("address"), entrega.get("number")) if x)
    if entrega.get("complement"):
        rua += f" - {entrega['complement']}"
    cidade = "/".join(x for x in (entrega.get("city"), entrega.get("state")) if x)
    bairro_cidade = " - ".join(x for x in (entrega.get("neighborhood"), cidade) if x)
    cep = re.sub(r"\D", "", str(entrega.get("zip_code") or ""))
    endereco = [x for x in (rua, bairro_cidade, f"CEP {cep[:5]}-{cep[5:]}" if len(cep) == 8 else "") if x]

    por_tray = {it.get("indice_tray"): i for i, it in enumerate(ctx["pedido"].get("itens", []))
                if it.get("indice_tray") is not None}
    itens = []
    itens_bling = ctx["pedido"].get("itens", [])
    for t, vendido in enumerate(o.get("ProductsSold") or []):
        vendido = vendido.get("ProductsSold") or vendido
        titulo, variacao = partes_nome_tray(vendido.get("name"))
        url = ((vendido.get("ProductSoldImage") or [{}])[0] or {}).get("https")
        qtd_tray = formatar_quantidade(vendido.get("quantity") or 1)
        indice = por_tray.get(t)
        # a quantidade é a do Bling (a mesma da OC e do card); se a Tray diverge, a ficha avisa
        qtd = formatar_quantidade(itens_bling[indice].get("quantidade", 1)) if indice is not None else qtd_tray
        itens.append({"qtd": qtd, "titulo": titulo, "variacao": variacao,
                      "ref": str(vendido.get("reference") or "").strip(), "ocs": _rotulo_ocs_do_item(indice, ocs),
                      "foto": baixar_imagem(url, ctx),
                      "aviso": f"Atenção: na Tray consta {qtd_tray} un." if qtd_tray != qtd else ""})
    h = ctx.get("html_pedido")
    entrega_prevista = h["entrega"].strftime("%d/%m/%Y") if h else _data_br(o.get("estimated_delivery_date"))
    if not h and entrega_prevista and entrega_prevista == _data_br(o.get("date")):
        entrega_prevista = ""  # a Tray às vezes repete a data da compra: não é prazo de entrega
    pz = ctx.get("prazos") or {}
    prazos = None
    if pz.get("embarque"):  # prazo pela tabela da transportadora: vai em destaque na ficha
        br = lambda d: d.strftime("%d/%m/%Y")
        entrega_prevista = br(pz["entrega"])
        prazos = {"embarque": br(pz["embarque"]), "atrasado": pz.get("embarque_atrasado"), "compra": br(pz["compra"]),
                  "entrega": br(pz["entrega"]), "fornecedores": br(pz["fornecedores"]),
                  "combinados": pz["combinados"], "frete": (ctx.get("frete") or {}).get("detalhe", "-"),
                  "logistica": pz["logistica"]}
    return {"numero": ctx["numero_tray"], "data": _data_br(o.get("date")), "status": o.get("status"),
            "entrega": entrega_prevista, "prazos": prazos, "cliente": cliente.get("name"),
            "telefone": cliente.get("cellphone") or cliente.get("phone"), "endereco": endereco,
            "recebe": entrega.get("recipient"), "itens": itens, "html": _linhas_do_html(h),
            "frete": o.get("shipment"), "transportadora": transportadora, "pagamento": o.get("payment_method"),
            "observacao_cliente": (o.get("customer_note") or "").strip()}


def dados_ficha_oc(ctx, f):
    """Dados da ficha da OC (card da Fábrica): nome da Tray e, embaixo, o do Bling; sem valores."""
    oc = f["oc"]
    o = None
    try:
        o = _pedido_tray_completo(ctx)
    except Exception:
        pass
    vendidos = [(v.get("ProductsSold") or v) for v in ((o or {}).get("ProductsSold") or [])]
    itens_pedido = ctx["pedido"].get("itens", [])

    def foto(item):
        origem = item.get("origem_pedido")
        indice = itens_pedido[origem].get("indice_tray") if origem is not None and origem < len(itens_pedido) else None
        if indice is None or indice >= len(vendidos):
            return None
        return baixar_imagem(((vendidos[indice].get("ProductSoldImage") or [{}])[0] or {}).get("https"), ctx)

    sem_ref = lambda texto: " ".join(re.sub(r"\s*\(Ref\.[^)]*\)", "", str(texto or "")).split())
    itens = []
    for it in oc["itens"]:
        if it.get("personalizacao_linha"):
            continue
        titulo = sem_ref(nome_da_loja(it))
        bling = nome_curto(it.get("descricao", ""))
        mesmo = lambda texto: re.sub(r"[^a-z0-9]", "", sem_acento(texto))  # ignora pontuação e espaços
        itens.append({"qtd": formatar_quantidade(it.get("quantidade", 1)), "titulo": titulo,
                      "nome_bling": bling if mesmo(bling) != mesmo(titulo) else "", "foto": foto(it)})
    personalizacao = [(f"{formatar_quantidade(it['quantidade'])}x {sem_ref(it.get('nome_tray') or nome_curto(it['produto_ref']))}",
                       it["personalizacao_texto"]) for it in oc["itens"] if it.get("personalizacao_linha")]
    h = ctx.get("html_pedido")
    pz = ctx.get("prazos") or {}
    embarque = pz.get("embarque") or (h or {}).get("embarque")
    entrega = pz.get("entrega") if pz.get("embarque") else (h or {}).get("entrega")
    return {"numero": oc["numero"], "fornecedor": "Fábrica" if oc.get("fabrica") else oc.get("fornecedor_nome"),
            "pedido": ctx["numero_tray"], "venda_bling": ctx["pedido"].get("numero"),
            "emissao": date.today().strftime("%d/%m/%Y"), "urgente": f.get("urgente"),
            "atrasado": bool(pz.get("fornecedores_atrasado")),
            "data_prevista": _data_br(oc.get("data_prevista")),
            "embarque": embarque.strftime("%d/%m/%Y") if embarque else "",
            "entrega_cliente": entrega.strftime("%d/%m/%Y") if entrega else "",
            "itens": itens, "personalizacao": personalizacao, "observacoes": oc.get("observacoes_ficha") or ""}


def gerar_ficha_pedido(ctx, ocs, transportadora):
    """PNG da ficha do pedido, ou None (aí o Assistente volta a pedir o print manual)."""
    try:
        import fichas
        imagem = fichas.ficha_pedido(dados_ficha_pedido(ctx, ocs, transportadora))
        print("Ficha do pedido gerada (no lugar do print da Tray).")
        return imagem
    except Exception as erro:
        print(f"ATENÇÃO: não consegui gerar a ficha do pedido ({erro}). Vamos pelo print manual.")
        return None


def gerar_ficha_oc(ctx, f):
    try:
        import fichas
        imagem = fichas.ficha_oc(dados_ficha_oc(ctx, f))
        print(f"Ficha da OC Nº {f['oc']['numero']} gerada (no lugar do print do Bling).")
        return imagem
    except Exception as erro:
        print(f"ATENÇÃO: não consegui gerar a ficha da OC Nº {f['oc']['numero']} ({erro}). Vamos pelo print manual.")
        return None


def enviar_trello(ctx, ocs):
    """
    Card da LOGÍSTICA (sempre) + um card na FÁBRICA para cada OC da fábrica
    (com print do pedido e print da OC). Devolve True se tudo foi criado.
    """
    numero_tray = ctx["numero_tray"]
    ocs_fabrica = [o for o in ocs if o.get("fabrica")]

    print("\n--- Trello: Logística ---")
    itens_pedido = texto_itens_logistica(ctx["pedido"], ocs)
    print(f"Itens (puxados do pedido): {itens_pedido}")
    transportadora = ctx.get("transportadora") or pedir_transportadora(ctx["pedido"])
    data_limite_iso = pedir_data_limite(ctx)
    ctx["data_embarque"] = data_limite_iso  # data do card da Logística (a régua usa a da OC quando há tabela)
    prazos = ctx.get("prazos") or {}

    fabricas = []
    for oc in ocs_fabrica:
        print(f"\n--- Trello: Fábrica (OC Nº {oc['numero']}) ---")
        itens_fabricar = texto_itens(oc["itens"])
        personalizacao = texto_personalizacoes(oc["itens"])
        print(f"Itens a fabricar: {itens_fabricar or '(nenhum, só personalização)'}")
        if personalizacao:
            print(f"Personalização: {personalizacao}")
        urgente = sim("Urgente?")
        nome_aba, lista_id = escolher_lista_fabrica()
        fabricas.append({"oc": oc, "itens": itens_fabricar, "personalizacao": personalizacao,
                         "urgente": urgente, "aba": nome_aba, "lista_id": lista_id,
                         "atrasado": bool(prazos.get("fornecedores_atrasado"))})

    nome_log = f"{'ATRASADO - ' if prazos.get('embarque_atrasado') else ''}Pedido {numero_tray} - {itens_pedido} - {transportadora}"
    print("\nResumo do Trello:")
    print(f"  Logística: {nome_log}")
    for f in fabricas:
        print(f"  Fábrica ({f['aba']}): {titulo_fabrica(f, numero_tray)}")
    if not sim("Confirma o envio para o Trello?"):
        print("Cancelado, nada foi criado no Trello.")
        return False

    # Imagens dos cards, todas antes de criar qualquer card:
    #   Logística -> FICHA DO PEDIDO gerada da Tray (se falhar: print manual do pedido na Tray)
    #   Fábrica   -> FICHA DA OC gerada do Bling (se falhar: print manual da OC no Bling)
    print_tray = gerar_ficha_pedido(ctx, ocs, transportadora) or capturar_print(
        "\nTire o print do PEDIDO DA TRAY (Win+Shift+S) e deixe copiado. [Logística]")
    if print_tray is None:
        print("A ficha (ou o print) do pedido é obrigatória. Nada foi criado no Trello.")
        return False
    for f in fabricas:
        f["print_oc"] = gerar_ficha_oc(ctx, f) or capturar_print(
            f"\nTire o print da OC Nº {f['oc']['numero']} no BLING (Win+Shift+S) e deixe copiado. [Fábrica]")
        if f["print_oc"] is None:
            print("A ficha (ou o print) da OC é obrigatória para a fábrica. Nada foi criado no Trello.")
            return False

    criados = []
    try:
        descricao_log = f"Itens do Pedido: {itens_pedido}\nTransportadora: {transportadora}"
        if prazos.get("embarque"):
            br = lambda d: d.strftime("%d/%m/%Y")
            if prazos.get("embarque_atrasado"):
                descricao_log += f"\n\n⚠ PEDIDO ATRASADO: o embarque máximo era {br(prazos['embarque'])}."
            descricao_log += (f"\n\nDATA MÁXIMA PARA EMBARQUE: {br(prazos['embarque'])}"
                              f"\nFrete: {(ctx.get('frete') or {}).get('detalhe', '-')}"
                              f"\nLogística: {LOGISTICA_DIAS_UTEIS} dias úteis | fornecedores até {br(prazos['fornecedores'])}"
                              f"\nEntrega ao cliente: {br(prazos['entrega'])} (compra em {br(prazos['compra'])}, "
                              f"{prazos['combinados']} dias úteis combinados)")
        if ocs:
            descricao_log += "\nOC(s) geradas: " + "; ".join(
                f"Nº {o['numero']} ({o['fornecedor_nome']})" for o in ocs)
        pers_total = ctx.get("personalizacao")
        if pers_total:
            descricao_log += f"\nPersonalização: {pers_total}"
        card_log, link_log = criar_card(config()["trello"]["lista_logistica_id"], nome_log,
                                        data_limite_iso, descricao_log)
        criados.append("Logística")
        anexar_imagem(card_log, print_tray, nome_arquivo_seguro(f"ficha_pedido_{numero_tray}"))
        print("Card criado na Logística com a ficha do pedido.")
        adicionar_checklist_logistica(card_log, link_log, ctx, ocs)

        for f in fabricas:
            oc = f["oc"]
            arquivo_oc = nome_arquivo_seguro(f"ficha_OC_{oc['numero']}")
            descricao_fab = f"Pedido Tray: {numero_tray}"
            if link_log:
                descricao_fab += f" (card da Logística: {link_log})"
            descricao_fab += f"\nOC Bling: Nº {oc['numero']}"
            descricao_fab += f"\nItens a serem fabricados: {f['itens'] or '-'}"
            if f["personalizacao"]:
                descricao_fab += f"\nPersonalização: {f['personalizacao']}"
            card_fab, _ = criar_card(f["lista_id"], titulo_fabrica(f, numero_tray),
                                     iso_da_data_bling(oc["data_prevista"]), descricao_fab)
            criados.append(f"Fábrica ({f['aba']})")
            anexar_imagem(card_fab, f["print_oc"], arquivo_oc)
            print(f"Card criado na Fábrica ({f['aba']}) com a ficha da OC.")
    except Exception as erro:
        if criados:
            print(f"\nATENÇÃO: estes cards JÁ foram criados: {', '.join(criados)}.")
            print("Confira no Trello antes de rodar de novo, para não duplicar.")
        raise erro
    return True


# ---------------------------------------------------------------------------
# DESCRIÇÃO EM HTML (padrão Tray)
# ---------------------------------------------------------------------------

def formatar_linha(rotulo, valor, cor=None, quebra=False):
    separador = "<br />" if quebra else " "
    texto = f"<strong>{rotulo}</strong>{separador}{valor}"
    if cor:
        texto = f'<span style="color: {cor};">{texto}</span>'
    return texto


FERIADOS_FIXOS = ["01/01", "21/04", "01/05", "07/09", "12/10", "02/11", "15/11", "20/11", "25/12"]


def _pascoa(ano):
    """Domingo de Páscoa (algoritmo de Meeus/Jones/Butcher)."""
    a, b, c = ano % 19, ano // 100, ano % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = (h + l - 7 * m + 114) % 31 + 1
    return date(ano, mes, dia)


_FERIADOS_CACHE = {}


def feriados(ano):
    """Feriados nacionais (fixos + Carnaval seg/ter, Sexta-feira Santa e Corpus Christi) e os da configuração
    'feriados_extras' (ex.: ["25/01", "09/07", "2026-12-24"]: 'dd/mm' repete todo ano)."""
    if ano not in _FERIADOS_CACHE:
        pascoa = _pascoa(ano)
        dias = {date(ano, int(t[3:5]), int(t[:2])) for t in FERIADOS_FIXOS}
        dias |= {pascoa + timedelta(days=n) for n in (-48, -47, -2, 60)}
        try:
            extras = config().get("feriados_extras") or []
        except Exception:
            extras = []
        for texto in extras:
            texto = str(texto).strip()
            try:
                if len(texto) == 5:
                    dias.add(date(ano, int(texto[3:5]), int(texto[:2])))
                elif texto[:4] == str(ano):
                    dias.add(datetime.strptime(texto[:10], "%Y-%m-%d").date())
            except ValueError:
                print(f"(feriado ignorado na configuração: {texto!r})")
        _FERIADOS_CACHE[ano] = dias
    return _FERIADOS_CACHE[ano]


def e_dia_util(dia):
    """Segunda a sexta que não é feriado."""
    return dia.weekday() < 5 and dia not in feriados(dia.year)


def somar_dias_uteis(inicio, dias):
    data = inicio
    while dias > 0:
        data += timedelta(days=1)
        if e_dia_util(data):
            dias -= 1
    return data


def pedir(pergunta, padrao=""):
    sufixo = f" [Enter = {padrao}]" if padrao else ""
    return input(f"{pergunta}{sufixo}: ").strip() or padrao


def separar_lista(texto, digitado=True):
    """Separa por ';'. Se o texto foi DIGITADO sem ';', separa por vírgula (jeito antigo),
    mas sem quebrar números como 1,20m ou 2,5x. O texto padrão (vindo do pedido) só separa por ';'."""
    separador = r";" if ";" in texto or not digitado else r",(?!\d)"
    return [p.strip() for p in re.split(separador, texto) if p.strip()]


def pedir_lista(pergunta, padrao=""):
    sufixo = f" [Enter = {padrao}]" if padrao else ""
    digitado = input(f"{pergunta} (separe os itens por ;){sufixo}: ").strip()
    return separar_lista(digitado or padrao, bool(digitado))


def pedir_tipo():
    return escolher("O pedido é pessoa física ou jurídica?", [("F", "Pessoa física"), ("J", "Pessoa jurídica")])


def pedir_dias_uteis():
    while True:
        try:
            return int(input("Data combinada (quantos dias úteis?): ").strip())
        except ValueError:
            print("Digite apenas o número de dias, por exemplo: 10")


def montar_html(linhas):
    return "<p>" + "<br />".join(linhas) + "</p>"


def itens_do_pedido_bling(numero_tray):
    """'2x Produto A; 1x Produto B' a partir do pedido de venda no Bling ('' se não achar)."""
    try:
        id_pedido = buscar_id_pedido_tray(numero_tray)
        if id_pedido is None:
            print(f"Não encontrei o pedido {numero_tray} no Bling: os itens serão digitados.")
            return ""
        pedido = chamar_bling("GET", f"/pedidos/vendas/{id_pedido}").get("data", {})
    except Exception as erro:
        print(f"Não consegui puxar os itens do Bling ({erro}): os itens serão digitados.")
        return ""
    itens = texto_itens(pedido.get("itens", []), "; ")
    if itens:
        print(f"Itens puxados do Bling: {itens}")
    return itens


def montar_descricao_html(tipo, dias, itens, personalizacoes, extras=None, hoje=None, dias_transporte=None):
    """Monta o HTML padrão Tray. itens/personalizacoes: listas de textos simples.
    extras (só pessoa jurídica): faturado, checklist, pasta, info_nf.
    hoje: base da contagem (no fluxo de compras, a data da compra). dias_transporte: frete da tabela da
    transportadora (sem ele, o padrão da configuração).
    Devolve (html, data_embarque, data_entrega)."""
    extras = extras or {}
    hoje = hoje or date.today()
    # OC ao lado do produto ('1x Mesa (OC 1234)') fica em negrito
    lista = lambda partes: "<br />".join(re.sub(r"\bOC (\d+)", r"<strong>OC \1</strong>", escape(p)) for p in partes)
    entrega = somar_dias_uteis(hoje, dias)
    transporte = prazo_transporte() if dias_transporte is None else dias_transporte
    embarque = somar_dias_uteis(hoje, max(dias - transporte, 0))

    linhas = []
    if tipo == "J":
        linhas.append(formatar_linha("Pedido faturado", f"{escape(extras.get('faturado', ''))} dias", AZUL))
        linhas.append(formatar_linha("Checklist realizado?", escape(extras.get("checklist", "")), AZUL))
    linhas.append(formatar_linha("Data combinada:", f"{dias} dias úteis", VERMELHO))
    linhas.append(formatar_linha("Itens do Pedido:", lista(itens), quebra=True))
    personalizacoes = [p for p in personalizacoes if str(p).strip()]
    if personalizacoes:
        linhas.append(formatar_linha("Personalização:", lista(personalizacoes), quebra=True))
    if tipo == "J":
        linhas.append(formatar_linha("Pasta:", escape(extras.get("pasta", "")), AZUL))
    linhas.append(formatar_linha("Data para embarque máxima:", embarque.strftime("%d/%m/%Y"), VERMELHO))
    linhas.append(formatar_linha("Data prevista para entrega:", entrega.strftime("%d/%m/%Y"), VERMELHO))
    if tipo == "J":
        linhas.append(formatar_linha("Informações adicionais de nota fiscal:", escape(extras.get("info_nf", ""))))
    return montar_html(linhas), embarque, entrega


def gerar_descricao_html(numero_tray=None, itens_padrao="", personalizacao_padrao="", dias_combinados=None,
                         ocs_vinculadas=None, ctx=None):
    """Gera o HTML padrão Tray. Com o número do pedido, puxa os itens do Bling e,
    no final, grava o HTML nas observações do pedido na Tray.
    dias_combinados: o prazo já informado (aí não pergunta de novo).
    ocs_vinculadas: OCs que já aparecem ao lado dos produtos no HTML; as linhas soltas delas saem da observação.
    ctx (fluxo de compras): o prazo é perguntado aqui uma vez só (Enter = data da Tray) e vale também para o card
    da Logística; o que foi preenchido fica em ctx['html_pedido'] para a ficha do pedido."""
    if ctx is not None and dias_combinados is None:
        dias_combinados = pedir_prazo_combinado(ctx, obrigatorio=True)
    if numero_tray is None:
        numero_tray = input("Número do pedido da Tray (Enter para preencher tudo à mão): ").strip()
        if numero_tray and not itens_padrao:
            itens_padrao = itens_do_pedido_bling(numero_tray)
    tipo = pedir_tipo()
    extras = {}
    if tipo == "J":
        extras["faturado"] = pedir("Pedido faturado (quantos dias?)")
        extras["checklist"] = escolher("Checklist realizado?", [("Sim", "Sim"), ("Não", "Não")])
    if dias_combinados is not None:
        dias = dias_combinados
        print(f"Data combinada: {dias} dias úteis (vale também para o card da Logística).")
    else:
        dias = pedir_dias_uteis()
    itens = pedir_lista("Itens do pedido", itens_padrao)
    personalizacao = pedir_lista("Personalização", personalizacao_padrao)
    if tipo == "J":
        extras["pasta"] = pedir("Pasta")
        extras["info_nf"] = pedir("Informações adicionais de nota fiscal")

    frete = ((ctx or {}).get("prazos") or {}).get("frete")
    if frete is not None:  # prazo pela tabela: conta da data da compra, com o frete real até o destino
        html, embarque, entrega = montar_descricao_html(tipo, dias, itens, personalizacao, extras,
                                                        hoje=ctx["prazos"]["compra"], dias_transporte=frete)
    else:
        html, embarque, entrega = montar_descricao_html(tipo, dias, itens, personalizacao, extras)
    if ctx is not None:
        ctx["html_pedido"] = {"tipo": tipo, "dias": dias, "personalizacao": personalizacao, "extras": extras,
                              "embarque": embarque, "entrega": entrega}
    print("\n===== HTML GERADO =====\n")
    print(html)
    print()
    partes = {"prazo": html}
    if ocs_vinculadas and any("OC " in i for i in itens):  # OC ao lado do produto: tira as linhas soltas repetidas
        partes.update({f"oc-{oc['id']}": None for oc in ocs_vinculadas if oc.get("id")})
    if not numero_tray or not na_tray(
        f"gravar o HTML nas observações do pedido {numero_tray}",
        "atualizar_observacao_gerenciada", numero_tray, partes,
    ):
        print("Copie o HTML acima e cole nas observações do pedido na Tray.")


# ---------------------------------------------------------------------------
# RAMOS DO FLUXO
# ---------------------------------------------------------------------------

def resumo_personalizacoes(itens):
    return "; ".join(f"{formatar_quantidade(i['quantidade'])}x {nome_da_loja(i)}: {i['personalizacao']}"
                     for i in itens if i["personalizacao"])


def texto_oc_tray(oc):
    """'OC 1234 Fornecedor Y - 2x Produto Z, 1x Produto W - Personalização: 2x Produto Z: logo'."""
    texto = f"OC {oc['numero']} {oc['fornecedor_nome']}"
    produtos = texto_itens(oc["itens"])
    personalizacao = texto_personalizacoes(oc["itens"])
    if produtos:
        texto += f" - {produtos}"
    if personalizacao:
        texto += f" - Personalização: {personalizacao}"
    return texto


def html_oc_tray(oc):
    """Uma linha por OC na observação da Tray, com o número em destaque:
    '<p><strong>OC 1234</strong> - Fornecedor Y: 2x Produto Z, 1x Produto W - Personalização: ...</p>' (só hífen: a Tray troca o travessão por '?')."""
    texto = f"<strong>OC {escape(str(oc['numero']))}</strong> - {escape(str(oc['fornecedor_nome']))}"
    produtos = texto_itens(oc["itens"])
    personalizacao = texto_personalizacoes(oc["itens"])
    if produtos:
        texto += f": {escape(produtos)}"
    if personalizacao:
        texto += f" - Personalização: {escape(personalizacao)}"
    return f"<p>{texto}</p>"


def anotar_oc_na_tray(numero_tray, oc, numero_bling=None):
    """Grava 'OC xxxx Fornecedor - Produtos' no pedido da Tray, sem nunca travar a criação das OCs."""
    try:
        texto = texto_oc_tray(oc)
    except Exception as erro:
        print(f"ATENÇÃO: não consegui montar o texto da OC Nº {oc.get('numero')} para a Tray ({erro}).")
        return
    if not numero_bling or not oc.get("id") or not oc.get("numero"):
        raise RuntimeError("Venda Bling e OC relida obrigatórias antes da anotação Tray.")
    partes = {
        "origem": (
            f"<p>Pedido Tray: {escape(str(numero_tray))} | "
            f"Venda Bling: {escape(str(numero_bling))}</p>"
        ),
        f"oc-{oc['id']}": html_oc_tray(oc),
    }
    na_tray(
        f"anotar a OC Nº {oc['numero']} no pedido {numero_tray}",
        "atualizar_observacao_gerenciada", numero_tray, partes,
    )


def lista_ocs(ocs):
    return "; ".join(f"Nº {o['numero']} ({o['fornecedor_nome']})" for o in ocs)


def etapa_html(ctx, ocs):
    """HTML do pedido ANTES do card da Logística: o prazo é perguntado aqui (Enter = data da Tray) e vale para o
    card; o que for preenchido também entra na ficha do pedido. Sem HTML, o card pergunta o prazo como antes."""
    if not sim("\nDeseja formalizar a observação em HTML?"):
        return
    pedido = ctx["pedido"]
    itens = texto_itens_logistica(pedido, ocs, "; ") if ocs else texto_itens(pedido.get("itens", []), "; ")
    gerar_descricao_html(ctx["numero_tray"], itens, ctx.get("personalizacao") or "", ocs_vinculadas=ocs, ctx=ctx)


def trello_apos_ocs(ctx, ocs):
    """Envia ao Trello. Se não concluir (cancelado ou erro), avisa que as OCs já existem no Bling."""
    try:
        if enviar_trello(ctx, ocs):
            return True
    except Exception:
        avisar_ocs_sem_trello(ocs)
        raise
    avisar_ocs_sem_trello(ocs)
    return False


def avisar_ocs_sem_trello(ocs):
    if ocs:
        print(f"\nATENÇÃO: a(s) OC(s) já foram criadas no Bling ({lista_ocs(ocs)}), "
              "mas o Trello não foi concluído.")
        print("O status do pedido não foi alterado.")


def criar_ocs_do_plano(ctx, grupos):
    """Revisa/cria cada OC do plano. Devolve a lista de OCs criadas."""
    print(f"\nSerão {len(grupos)} OC(s):")
    for g in grupos:
        print(f"  - {g['fornecedor_nome']}{' (fábrica)' if g['fabrica'] else ''}")

    texto_obs_padrao = f"Pedido Tray: {ctx['numero_tray']}"  # os itens de cada OC entram no processar_grupo
    ocs = []
    try:
        for g in grupos:
            oc = processar_grupo(g, texto_obs_padrao, ctx["numero_tray"],
                                 data_sugerida=(ctx.get("prazos") or {}).get("fornecedores"))
            if oc:
                ocs.append(oc)
                anotar_oc_na_tray(
                    ctx["numero_tray"], oc,
                    numero_bling=(ctx.get("pedido") or {}).get("numero"),
                )
    except Exception:
        if ocs:
            print(f"\nATENÇÃO: estas OCs JÁ foram criadas no Bling: {lista_ocs(ocs)}.")
            print("Confira no Bling antes de rodar de novo, para não duplicar.")
        raise
    if ocs:
        print("\n=== OCs criadas ===")
        for oc in ocs:
            print(f"  OC Nº {oc['numero']} - {oc['fornecedor_nome']}")
        print("\nA seguir, cada OC abre no Bling para o envio por e-mail (botão do próprio Bling).")
        print("Deixe a tela da OC aberta: você vai precisar dela para o print do Trello da fábrica.")
    return ocs


URL_LISTA_OCS_BLING = "https://www.bling.com.br/pedidos.compra.php#list"


def link_lista_ocs_bling():
    """Lista de pedidos de compra do Bling, onde o 'Enviar por e-mail' de cada OC fica a um clique
    (config: bling.url_lista_ocs)."""
    try:
        return (config().get("bling") or {}).get("url_lista_ocs") or URL_LISTA_OCS_BLING
    except Exception:
        return URL_LISTA_OCS_BLING


def email_do_fornecedor(fornecedor_id):
    """E-mail do contato no Bling (só leitura): '' se não houver; None se não deu para conferir."""
    try:
        contato = chamar_bling("GET", f"/contatos/{fornecedor_id}").get("data", {}) or {}
    except Exception:
        return None
    return str(contato.get("email") or "").strip()


def enviar_ocs_pelo_bling(ctx, ocs):
    """O Bling envia a OC por e-mail (a API não tem esse envio): abre a lista de pedidos de compra do Bling
    (uma vez), a pessoa clica em 'Enviar por e-mail' em cada OC e confirma aqui, uma a uma.
    Registra no histórico. Devolve True só se TODAS foram enviadas."""
    import webbrowser
    fabrica = [oc for oc in ocs if oc.get("fabrica")]
    ocs = [oc for oc in ocs if not oc.get("fabrica")]
    if fabrica:  # a OC da fábrica vai pelo card do Trello (com a ficha), não por e-mail
        print("\nOC(s) da fábrica: " + ", ".join(f"Nº {oc['numero']}" for oc in fabrica)
              + " - enviada(s) pelo card da Fábrica no Trello.")
    if not ocs:
        return True
    print("\n--- Envio das OCs pelo Bling ---")
    for oc in ocs:
        print(f"  OC Nº {oc['numero']} - {oc['fornecedor_nome']}")
        if email_do_fornecedor(oc["fornecedor_id"]) == "":
            print(f"  ATENÇÃO: {oc['fornecedor_nome']} está SEM e-mail no cadastro do Bling: o 'Enviar por e-mail' "
                  "ficará sem destinatário. Cadastre o e-mail no contato ou envie a OC por outro meio.")
    link = link_lista_ocs_bling()
    try:
        if MODO_DEMO:
            raise RuntimeError("demonstração: o Bling não é aberto")
        webbrowser.open(link)
        print(f"Lista de pedidos de compra aberta no Bling: {link}")
    except Exception:
        print(f"Abra a lista de pedidos de compra no Bling: {link}")
    print("Em cada OC acima, clique em 'Enviar por e-mail' na lista do Bling e confirme aqui.")
    todas = True
    for oc in ocs:
        enviada = escolher(f"Enviou a OC Nº {oc['numero']} ({oc['fornecedor_nome']}) pelo Bling?",
                           [("s", "Sim, enviei"), ("n", "Não enviei")]) == "s"
        registrar_historico({"oc_numero": oc["numero"], "pedido": ctx["numero_tray"],
                             "fornecedor_nome": oc["fornecedor_nome"], "rotulo": "Envio da OC",
                             "texto": "Enviada pelo botão 'Enviar por e-mail' do Bling"},
                            "E-mail (Bling)", "real", "e-mail do cadastro no Bling",
                            "enviada" if enviada else "não enviada", "" if enviada else "envio não confirmado")
        todas = todas and enviada
    if not todas:
        print("\nNem todas as OCs foram enviadas: o status NÃO vai para 'OC enviada'. Depois de enviar, altere no Bling.")
    return todas


def checar_config_trello():
    problemas = validar_config_trello()
    if not problemas:
        return True
    print("\nAVISO: problemas no config.json (Trello):")
    for p in problemas:
        print(f"  - {p}")
    return sim("Continuar mesmo assim?")


def aplicar_status_final(ctx, ocs, email_enviado):
    """
    Regra do status no Bling (e o equivalente na Tray):
      - teve OC (compra OU personalização) -> 'OC enviada' (só se o e-mail já foi enviado)
                                              Tray: 'Aguardando fornecedor';
      - nenhuma OC, tudo em estoque         -> 'Em separação'
                                              Tray: 'Pedido em separação'.
    """
    if ocs:
        if not email_enviado:
            print("\nComo o e-mail da(s) OC(s) ainda não foi enviado, o status NÃO foi mudado para 'OC enviada'.")
            print("Depois de enviar, altere o status no Bling.")
            return
        id_situacao, nome = ctx["id_oc_enviada"], "OC enviada"
    else:
        id_situacao, nome = ctx["id_separacao"], "Em separação"
    mudar_situacao_venda(ctx["id_pedido"], id_situacao)
    print(f"Pedido mudado para '{nome}' no Bling.")
    status_tray = status_tray_equivalente(nome)
    na_tray(f"mudar o pedido {ctx['numero_tray']} para '{status_tray}'",
            "mudar_status", ctx["numero_tray"], status_tray)


def ramo_estoque(ctx):
    """Em estoque: sem personalização -> 'Em separação'; com personalização -> OC da fábrica + 'OC enviada'."""
    if not checar_config_trello():
        return False
    planejar_prazos(ctx)

    print("\n--- Produtos em estoque ---")
    itens = levantar_itens(ctx["pedido"], buscar_fornecedor=False)
    ctx["itens"] = itens
    tem_personalizacao = perguntar_personalizacoes(itens, mostrar_origem=False)

    # Status necessário, conferido ANTES de criar qualquer coisa
    if tem_personalizacao:
        ctx["id_oc_enviada"] = id_situacao_oc_enviada()
        if ctx["id_oc_enviada"] is None:
            print("Sem o status 'OC enviada' não dá para concluir. Nada foi criado.")
            return False
    else:
        ctx["id_separacao"] = id_situacao_separacao()
        if ctx["id_separacao"] is None:
            print("Sem o status 'Em separação' não dá para concluir. Nada foi criado.")
            return False

    ocs, email_enviado = [], False
    if tem_personalizacao:
        ctx["personalizacao"] = resumo_personalizacoes(itens)
        grupos = montar_plano(itens, comprar_produtos=False)
        ocs = criar_ocs_do_plano(ctx, grupos) if grupos else []
        if not ocs:
            print("\nNenhuma OC de personalização foi criada. Nada mais será feito.")
            return False
        ctx["ocs"] = ocs
        email_enviado = enviar_ocs_pelo_bling(ctx, ocs)

    etapa_html(ctx, ocs)
    if not trello_apos_ocs(ctx, ocs):
        return False

    aplicar_status_final(ctx, ocs, email_enviado)
    return True


def ramo_compra(ctx):
    """Compra: personalização por produto -> OCs (1 por fornecedor) -> Trello -> 'OC enviada'."""
    if not checar_config_trello():
        return False
    ctx["id_oc_enviada"] = id_situacao_oc_enviada()
    if ctx["id_oc_enviada"] is None:
        print("Sem o status 'OC enviada' não dá para concluir. Nada foi criado.")
        return False
    planejar_prazos(ctx)                                 # prazo combinado, frete e prazo dos fornecedores

    comprar = perguntar_o_que_comprar(ctx["pedido"])    # fase 0: item a item, compra ou estoque
    if any(comprar):
        print("\nBuscando fornecedor e preço de cada item a comprar...")
    itens = levantar_itens(ctx["pedido"], comprar=comprar)  # fase 1
    ctx["itens"] = itens
    perguntar_personalizacoes(itens)                    # fase 2
    ctx["personalizacao"] = resumo_personalizacoes(itens)

    grupos = montar_plano(itens)                        # fase 3
    if not grupos:
        if any(comprar):
            print("\nNenhum item com fornecedor cadastrado e nenhuma personalização. Nada a comprar.")
            return False
        # Marcou tudo como estoque e sem personalização: segue como pedido de estoque
        print("\nNenhum item para comprar: o pedido segue como estoque.")
        ctx["id_separacao"] = id_situacao_separacao()
        if ctx["id_separacao"] is None:
            print("Sem o status 'Em separação' não dá para concluir. Nada foi criado.")
            return False
        etapa_html(ctx, [])
        if not trello_apos_ocs(ctx, []):
            return False
        aplicar_status_final(ctx, [], False)
        return True

    ocs = criar_ocs_do_plano(ctx, grupos)               # fase 4
    if not ocs:
        print("\nNenhuma OC foi criada. Nada mais será feito.")
        return False
    ctx["ocs"] = ocs
    email_enviado = enviar_ocs_pelo_bling(ctx, ocs)

    etapa_html(ctx, ocs)
    if not trello_apos_ocs(ctx, ocs):
        return False

    aplicar_status_final(ctx, ocs, email_enviado)
    return True


# ---------------------------------------------------------------------------
# FLUXO PRINCIPAL
# ---------------------------------------------------------------------------

STATUS_PARA_COMPRAR = ["A Enviar", "Liberado"]
_OC_NA_OBSERVACAO = re.compile(r"parte:oc-\d+|\bOC\s*(?:N[ºo°]\s*)?\d{3,}", re.IGNORECASE)


def pedidos_para_comprar():
    """Pedidos da Tray nos status de compra (config: compras.status_tray), do mais antigo para o mais novo, cada um
    com os itens (nomes da Tray) e avisos de que já tem OC anotada na Tray ou card no Trello. Só leitura."""
    modulo = tray()
    if modulo is None:
        raise RuntimeError("a Tray não está configurada")
    try:
        nomes = (config().get("compras") or {}).get("status_tray") or STATUS_PARA_COMPRAR
    except Exception:
        nomes = STATUS_PARA_COMPRAR
    pedidos = modulo.pedidos_por_status(nomes)
    com_card = {str(r.get("pedido")) for r in carregar_acompanhamento()}
    for p in pedidos:
        try:
            detalhes = modulo.detalhes_pedido(p["numero"])
            p["itens"] = [f"{formatar_quantidade(i.get('quantidade') or 1)}x {limpar_nome_tray(i['nome'])}"
                          for i in detalhes["itens"]]
            p["ja_tem_oc"] = bool(_OC_NA_OBSERVACAO.search(detalhes["observacao"]))
        except Exception:
            p["itens"], p["ja_tem_oc"] = [], False
        p["ja_tem_card"] = p["numero"] in com_card
        try:  # dias úteis desde a compra (sem fim de semana nem feriado)
            p["dias_esperando"] = max(dias_uteis_ate(datetime.strptime(str(p.get("data"))[:10], "%Y-%m-%d").date(),
                                                     date.today()), 0)
        except ValueError:
            p["dias_esperando"] = 0
    pedidos.sort(key=lambda p: (str(p.get("data") or ""), p["numero"]))
    return pedidos


def processar_pedido(numero_tray=None):
    """numero_tray: vindo do card da tela de Compras; sem ele, pergunta."""
    if numero_tray:
        numero_tray = str(numero_tray).strip()
        print(f"\nPedido da Tray: {numero_tray}")
    else:
        numero_tray = input("\nNúmero do pedido da Tray: ").strip()
    if not numero_tray:
        print("Número do pedido é obrigatório.")
        return

    id_pedido = buscar_id_pedido_tray(numero_tray)
    if id_pedido is None:
        print(f"Não encontrei no Bling nenhum pedido com o número da Tray {numero_tray}.")
        return

    pedido = mostrar_pedido(id_pedido)
    buscar_nomes_na_tray(numero_tray, pedido)  # nomes do Trello e das observações como o cliente comprou
    ctx = {"numero_tray": numero_tray, "id_pedido": id_pedido, "pedido": pedido,
           "ocs": [], "personalizacao": ""}

    opcao = escolher("Os produtos estão em estoque?", [("1", "Sim, tem em estoque (logística)"),
                                                       ("2", "Não, precisa comprar algum item (OC)"),
                                                       ("0", "Cancelar")])

    if opcao == "1":
        concluiu = ramo_estoque(ctx)
    elif opcao == "2":
        concluiu = ramo_compra(ctx)
    else:
        print("Cancelado, nada foi alterado.")
        return

    # o HTML do pedido agora é feito antes do card da Logística (etapa_html), dentro dos ramos


# ---------------------------------------------------------------------------
# OPÇÃO 1: CALCULADORA DE DESCONTO
# ---------------------------------------------------------------------------

def formatar_reais(valor):
    """1425.475 -> 'R$ 1.425,48'."""
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def ler_valor(pergunta, mensagem_negativo):
    while True:
        try:
            valor = converter_numero(input(pergunta).strip())
        except ValueError:
            print("Digite apenas números, por exemplo: 1.500,50")
            continue
        if valor < 0:
            print(mensagem_negativo)
            continue
        return valor


def calcular_desconto():
    val_prod = ler_valor("Qual o valor total dos produtos? ", "O valor não pode ser negativo.")
    frete = ler_valor("Qual o valor do frete? ", "O frete não pode ser negativo.")

    valores = valores_desconto(val_prod, frete)
    print(f"\nValor parcelado em até 12x sem juros: {formatar_reais(valores['12x'])}")
    print(f"Valor parcelado em até 3x sem juros: {formatar_reais(valores['3x'])}")
    print(f"Valor à vista no pix: {formatar_reais(valores['pix'])}")


def valores_desconto(val_prod, frete):
    """Valores com desconto (o frete não tem desconto)."""
    return {
        "12x": round(val_prod * 0.95 + frete, 2),
        "3x": round(val_prod * 0.95 * 0.95 + frete, 2),
        "pix": round(val_prod * 0.95 * 0.90 + frete, 2),
    }


# ---------------------------------------------------------------------------
# OPÇÃO 2: REALIZAR COMPRAS
# ---------------------------------------------------------------------------

def realizar_compras():
    print("\n=== Realizar compras: Tray -> Bling -> Trello ===")
    while True:
        try:
            processar_pedido()
        except Exception as erro:
            print("\n=== ERRO ===")
            print(erro)
        if not sim("\nProcessar outro pedido?"):
            break


# ---------------------------------------------------------------------------
# MENU PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    while True:
        print("\n=== Assistente do Vendedor ===")
        print("[1] Calcular desconto de 5%")
        print("[2] Realizar compras (Tray -> Bling -> Trello)")
        print("[3] Gerar descrição detalhada em HTML")
        print("[0] Sair")
        opcao = input("Escolha uma opção: ").strip()
        try:
            if opcao == "1":
                calcular_desconto()
            elif opcao == "2":
                realizar_compras()
            elif opcao == "3":
                gerar_descricao_html()
            elif opcao == "0":
                print("Encerrado.")
                break
            else:
                print("Opção inválida, tente novamente.")
        except Exception as erro:
            print("\n=== ERRO ===")
            print(erro)


if __name__ == "__main__":
    main()
