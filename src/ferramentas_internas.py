"""
Assistente do Vendedor - menu único.

[1] Calcular desconto de 5%
[2] Realizar compras (Tray -> Bling -> Trello)
[3] Gerar descrição detalhada em HTML (padrão Tray)

Produtos ESTRUTURADOS no Bling (ex.: mesa = tampo + base) são desmembrados
e comprados por componente, cada um com seu próprio fornecedor.

Status no Bling (e na Tray):
    Tudo em estoque, sem personalização -> Em separação (Tray: Pedido em separação)
    Qualquer OC (compra ou personalização) -> OC enviada (Tray: Mercadoria Solicitada ao depósito central)

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
from datetime import date, datetime, timedelta
from html import escape
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
    "OC enviada": ("status_oc_enviada", "Mercadoria Solicitada ao depósito central"),
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


def texto_itens(itens, separador=", "):
    """'10x Base Aurora, 2x Tampo Redondo'. Linhas de personalização ficam de fora."""
    return separador.join(rotulo_item(i) for i in itens if not i.get("personalizacao_linha"))


def texto_personalizacoes(itens, separador="; "):
    """'2x Cadeira X: bordado azul; 1x Mesa Y: logo gravado'."""
    return separador.join(
        f"{formatar_quantidade(i['quantidade'])}x {nome_curto(i['produto_ref'])}: {i['personalizacao_texto']}"
        for i in itens
        if i.get("personalizacao_linha")
    )


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


def item_base(produto_id, codigo, descricao, quantidade, kit=None):
    return {
        "produto_id": produto_id,
        "codigo": codigo or "?",
        "descricao": descricao or "",
        "quantidade": float(quantidade or 1),
        "kit": kit,                    # nome do produto estruturado de origem (se for componente)
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
    info["valor"] = float(
        fornecedor.get("precoCompra") or fornecedor.get("precoCusto") or produto.get("precoCusto") or 0
    )


def expandir_produto(produto_id, quantidade, descricao=None, codigo=None, kit=None, nivel=0):
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
                itens += expandir_produto(cid, quantidade * qtd_comp, kit=kit or descricao, nivel=nivel + 1)
            return itens
        print(f"{recuo}ATENÇÃO: {descricao} está como estruturado, mas não achei os componentes. "
              "Vai ser comprado como produto único.")

    info = item_base(produto_id, codigo, descricao, quantidade, kit)
    preencher_fornecedor(info, produto)
    if nivel > 0:
        print(f"{recuo}• {rotulo_item(info)} [{info['fornecedor_nome'] or 'SEM fornecedor'}]")
    return [info]


def levantar_itens(pedido, buscar_fornecedor=True):
    """
    Monta a lista de itens a comprar.
    - buscar_fornecedor=True (compra): consulta cada produto no Bling; produtos
      ESTRUTURADOS são desmembrados nos componentes, com fornecedor e preço de cada um.
    - buscar_fornecedor=False (estoque): só a lista do pedido, sem consultar o Bling.
    """
    itens = []
    for item in pedido.get("itens", []):
        produto_id = (item.get("produto", {}) or {}).get("id")
        codigo, descricao = item.get("codigo", "?"), item.get("descricao", "")
        quantidade = float(item.get("quantidade", 1) or 1)
        if produto_id and buscar_fornecedor:
            itens += expandir_produto(produto_id, quantidade, descricao, codigo)
        else:
            itens.append(item_base(produto_id, codigo, descricao, quantidade))
    return itens


# ---------------------------------------------------------------------------
# COMPRA - FASE 2: PERSONALIZAÇÃO PRODUTO A PRODUTO
# ---------------------------------------------------------------------------

def perguntar_personalizacoes(itens, mostrar_origem=True):
    """Pergunta, para cada produto, se ele tem personalização (texto + valor por unidade).
    Devolve True se algum produto tiver personalização."""
    print("\n--- Personalização (produto a produto) ---")
    for it in itens:
        if mostrar_origem:
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
        "origem": item,  # para acompanhar a quantidade revisada do produto
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

    sem_fornecedor = [it for it in itens if not it["fornecedor_id"]]
    pers_externas = [it for it in itens if it["personalizacao"] and not e_fabrica(it["fornecedor_nome"])]

    if sem_fornecedor:
        print("\nATENÇÃO: estes itens estão SEM fornecedor no cadastro e não entram em nenhuma OC de compra:")
        for it in sem_fornecedor:
            print(f"  - {it['codigo']} - {it['descricao']}")

    # Identifica a fábrica: pelos próprios itens ou, se precisar, pelo cadastro.
    fabrica = next(((it["fornecedor_id"], it["fornecedor_nome"]) for it in itens
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

    # Itens com fornecedor (fábrica: produto + personalização em sequência)
    for it in itens:
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


def pedir_data_prevista():
    """Data prevista de entrega do fornecedor (obrigatória no Bling). Devolve 'aaaa-mm-dd'."""
    while True:
        texto = input("Data prevista de entrega do fornecedor (dd/mm/aaaa): ").strip()
        try:
            return datetime.strptime(texto, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            print("Data inválida, use o formato dd/mm/aaaa (ex: 20/10/2026).")


def pedir_observacoes_internas(texto_padrao):
    print(f"Observação interna padrão: {texto_padrao}")
    extra = input("Complemento das observações internas (Enter para usar só o padrão): ").strip()
    return f"{texto_padrao} | {extra}" if extra else texto_padrao


def criar_oc(fornecedor_id, itens, data_prevista, observacoes="", observacoes_internas=""):
    """Cria o pedido de compra no Bling e devolve (id, numero)."""
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
    if observacoes:
        payload["observacoes"] = observacoes
    if observacoes_internas:
        payload["observacoesInternas"] = observacoes_internas

    id_oc = chamar_bling("POST", "/pedidos/compras", json=payload).get("data", {}).get("id")
    numero = None
    if id_oc:
        try:  # a OC já existe: uma falha aqui não pode interromper o fluxo
            numero = chamar_bling("GET", f"/pedidos/compras/{id_oc}").get("data", {}).get("numero")
        except Exception as erro:
            print(f"OC criada (ID {id_oc}), mas não consegui ler o número dela ({erro}).")
    return id_oc, numero


def processar_grupo(grupo, texto_obs_padrao):
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

    data_prevista = pedir_data_prevista()
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
    id_oc, numero = criar_oc(grupo["fornecedor_id"], finais, data_prevista, obs_padrao, obs)
    print(f"OC criada! Nº {numero} (ID {id_oc})")
    return {
        "id": id_oc,
        "numero": numero,
        "fornecedor_id": grupo["fornecedor_id"],
        "fornecedor_nome": grupo["fornecedor_nome"],
        "fabrica": grupo["fabrica"],
        "itens": finais,
        "data_prevista": data_prevista,
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


def pedir_data_limite():
    """Pergunta o prazo combinado em dias úteis e devolve a data do card (ISO) ou None."""
    while True:
        texto = input("Prazo de entrega combinado (quantos dias úteis? Enter para pular): ").strip()
        if not texto:
            return None
        if not texto.isdigit():
            print("Digite só o número de dias úteis, por exemplo: 20")
            continue
        combinados = int(texto)
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
    prefixo = "URGENTE: " if f["urgente"] else ""
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
        return input("Transportadora utilizada: ").strip()
    digitada = input(f"Transportadora utilizada [Enter = {sugerida}]: ").strip()
    return digitada or sugerida


def enviar_trello(ctx, ocs):
    """
    Card da LOGÍSTICA (sempre) + um card na FÁBRICA para cada OC da fábrica
    (com print do pedido e print da OC). Devolve True se tudo foi criado.
    """
    numero_tray = ctx["numero_tray"]
    ocs_fabrica = [o for o in ocs if o.get("fabrica")]

    print("\n--- Trello: Logística ---")
    itens_pedido = texto_itens(ctx["pedido"].get("itens", []))
    print(f"Itens (puxados do pedido): {itens_pedido}")
    transportadora = pedir_transportadora(ctx["pedido"])
    data_limite_iso = pedir_data_limite()

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
                         "urgente": urgente, "aba": nome_aba, "lista_id": lista_id})

    nome_log = f"Pedido {numero_tray} - {itens_pedido} - {transportadora}"
    print("\nResumo do Trello:")
    print(f"  Logística: {nome_log}")
    for f in fabricas:
        print(f"  Fábrica ({f['aba']}): {titulo_fabrica(f, numero_tray)}")
    if not sim("Confirma o envio para o Trello?"):
        print("Cancelado, nada foi criado no Trello.")
        return False

    # Prints: todos antes de criar qualquer card
    #   Logística -> print do PEDIDO DA TRAY (obrigatório)
    #   Fábrica   -> print da OC do Bling (o pedido da Tray fica só na descrição do card)
    print_tray = capturar_print("\nTire o print do PEDIDO DA TRAY (Win+Shift+S) e deixe copiado. [Logística]")
    if print_tray is None:
        print("O print do pedido da Tray é obrigatório. Nada foi criado no Trello.")
        return False
    for f in fabricas:
        f["print_oc"] = capturar_print(
            f"\nTire o print da OC Nº {f['oc']['numero']} no BLING (Win+Shift+S) e deixe copiado. [Fábrica]")
        if f["print_oc"] is None:
            print("O print da OC é obrigatório para a fábrica. Nada foi criado no Trello.")
            return False

    criados = []
    try:
        descricao_log = f"Itens do Pedido: {itens_pedido}\nTransportadora: {transportadora}"
        if ocs:
            descricao_log += "\nOC(s) geradas: " + "; ".join(
                f"Nº {o['numero']} ({o['fornecedor_nome']})" for o in ocs)
        pers_total = ctx.get("personalizacao")
        if pers_total:
            descricao_log += f"\nPersonalização: {pers_total}"
        card_log, link_log = criar_card(config()["trello"]["lista_logistica_id"], nome_log,
                                        data_limite_iso, descricao_log)
        criados.append("Logística")
        anexar_imagem(card_log, print_tray, nome_arquivo_seguro(f"pedido_tray_{numero_tray}"))
        print("Card criado na Logística com o print do pedido da Tray.")

        for f in fabricas:
            oc = f["oc"]
            arquivo_oc = nome_arquivo_seguro(f"OC_{oc['numero']}")
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
            print(f"Card criado na Fábrica ({f['aba']}) com o print da OC.")
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


def somar_dias_uteis(inicio, dias):
    data = inicio
    while dias > 0:
        data += timedelta(days=1)
        if data.weekday() < 5:
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


def montar_descricao_html(tipo, dias, itens, personalizacoes, extras=None, hoje=None):
    """Monta o HTML padrão Tray. itens/personalizacoes: listas de textos simples.
    extras (só pessoa jurídica): faturado, checklist, pasta, info_nf.
    Devolve (html, data_embarque, data_entrega)."""
    extras = extras or {}
    hoje = hoje or date.today()
    lista = lambda partes: "<br />".join(escape(p) for p in partes)
    entrega = somar_dias_uteis(hoje, dias)
    embarque = somar_dias_uteis(hoje, max(dias - prazo_transporte(), 0))

    linhas = []
    if tipo == "J":
        linhas.append(formatar_linha("Pedido faturado", f"{escape(extras.get('faturado', ''))} dias", AZUL))
        linhas.append(formatar_linha("Checklist realizado?", escape(extras.get("checklist", "")), AZUL))
    linhas.append(formatar_linha("Data combinada:", f"{dias} dias úteis", VERMELHO))
    linhas.append(formatar_linha("Itens do Pedido:", lista(itens), quebra=True))
    linhas.append(formatar_linha("Personalização:", lista(personalizacoes), quebra=True))
    if tipo == "J":
        linhas.append(formatar_linha("Pasta:", escape(extras.get("pasta", "")), AZUL))
    linhas.append(formatar_linha("Data para embarque máxima:", embarque.strftime("%d/%m/%Y"), VERMELHO))
    linhas.append(formatar_linha("Data prevista para entrega:", entrega.strftime("%d/%m/%Y"), VERMELHO))
    if tipo == "J":
        linhas.append(formatar_linha("Informações adicionais de nota fiscal:", escape(extras.get("info_nf", ""))))
    return montar_html(linhas), embarque, entrega


def gerar_descricao_html(numero_tray=None, itens_padrao="", personalizacao_padrao=""):
    """Gera o HTML padrão Tray. Com o número do pedido, puxa os itens do Bling e,
    no final, grava o HTML nas observações do pedido na Tray."""
    if numero_tray is None:
        numero_tray = input("Número do pedido da Tray (Enter para preencher tudo à mão): ").strip()
        if numero_tray and not itens_padrao:
            itens_padrao = itens_do_pedido_bling(numero_tray)
    tipo = pedir_tipo()
    extras = {}
    if tipo == "J":
        extras["faturado"] = pedir("Pedido faturado (quantos dias?)")
        extras["checklist"] = escolher("Checklist realizado?", [("Sim", "Sim"), ("Não", "Não")])
    dias = pedir_dias_uteis()
    itens = pedir_lista("Itens do pedido", itens_padrao)
    personalizacao = pedir_lista("Personalização", personalizacao_padrao)
    if tipo == "J":
        extras["pasta"] = pedir("Pasta")
        extras["info_nf"] = pedir("Informações adicionais de nota fiscal")

    html, _, _ = montar_descricao_html(tipo, dias, itens, personalizacao, extras)
    print("\n===== HTML GERADO =====\n")
    print(html)
    print()
    if not numero_tray or not na_tray(f"gravar o HTML nas observações do pedido {numero_tray}",
                                      "adicionar_observacao", numero_tray, html):
        print("Copie o HTML acima e cole nas observações do pedido na Tray.")


# ---------------------------------------------------------------------------
# RAMOS DO FLUXO
# ---------------------------------------------------------------------------

def resumo_personalizacoes(itens):
    return "; ".join(f"{formatar_quantidade(i['quantidade'])}x {nome_curto(i['descricao'])}: {i['personalizacao']}"
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


def anotar_oc_na_tray(numero_tray, oc):
    """Grava 'OC xxxx Fornecedor - Produtos' no pedido da Tray, sem nunca travar a criação das OCs."""
    try:
        texto = texto_oc_tray(oc)
    except Exception as erro:
        print(f"ATENÇÃO: não consegui montar o texto da OC Nº {oc.get('numero')} para a Tray ({erro}).")
        return
    na_tray(f"anotar a OC Nº {oc['numero']} no pedido {numero_tray}", "adicionar_observacao", numero_tray, texto)


def lista_ocs(ocs):
    return "; ".join(f"Nº {o['numero']} ({o['fornecedor_nome']})" for o in ocs)


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
            oc = processar_grupo(g, texto_obs_padrao)
            if oc:
                ocs.append(oc)
                anotar_oc_na_tray(ctx["numero_tray"], oc)
    except Exception:
        if ocs:
            print(f"\nATENÇÃO: estas OCs JÁ foram criadas no Bling: {lista_ocs(ocs)}.")
            print("Confira no Bling antes de rodar de novo, para não duplicar.")
        raise
    if ocs:
        print("\n=== OCs criadas ===")
        for oc in ocs:
            print(f"  OC Nº {oc['numero']} - {oc['fornecedor_nome']}")
        print("\nAbra a(s) OC(s) no Bling e clique em 'Enviar por e-mail'.")
        print("Deixe a tela da OC aberta: você vai precisar dela para o print do Trello da fábrica.")
    return ocs


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
                                              Tray: 'Mercadoria Solicitada ao depósito central';
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

    print("\n--- Produtos em estoque ---")
    itens = levantar_itens(ctx["pedido"], buscar_fornecedor=False)
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
        email_enviado = sim("Já enviou o e-mail da OC para a fábrica?")

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

    print("\nBuscando fornecedor e preço de cada item...")
    itens = levantar_itens(ctx["pedido"])               # fase 1
    perguntar_personalizacoes(itens)                    # fase 2
    ctx["personalizacao"] = resumo_personalizacoes(itens)

    grupos = montar_plano(itens)                        # fase 3
    if not grupos:
        print("\nNenhum item com fornecedor cadastrado e nenhuma personalização. Nada a comprar.")
        return False

    ocs = criar_ocs_do_plano(ctx, grupos)               # fase 4
    if not ocs:
        print("\nNenhuma OC foi criada. Nada mais será feito.")
        return False
    ctx["ocs"] = ocs
    email_enviado = sim("Já enviou o(s) e-mail(s) das OCs?")

    if not trello_apos_ocs(ctx, ocs):
        return False

    aplicar_status_final(ctx, ocs, email_enviado)
    return True


# ---------------------------------------------------------------------------
# FLUXO PRINCIPAL
# ---------------------------------------------------------------------------

def processar_pedido():
    numero_tray = input("\nNúmero do pedido da Tray: ").strip()
    if not numero_tray:
        print("Número do pedido é obrigatório.")
        return

    id_pedido = buscar_id_pedido_tray(numero_tray)
    if id_pedido is None:
        print(f"Não encontrei no Bling nenhum pedido com o número da Tray {numero_tray}.")
        return

    pedido = mostrar_pedido(id_pedido)
    ctx = {"numero_tray": numero_tray, "id_pedido": id_pedido, "pedido": pedido,
           "ocs": [], "personalizacao": ""}

    opcao = escolher("Os produtos estão em estoque?", [("1", "Sim, tem em estoque (logística)"),
                                                       ("2", "Não, precisa comprar (OC)"),
                                                       ("0", "Cancelar")])

    if opcao == "1":
        concluiu = ramo_estoque(ctx)
    elif opcao == "2":
        concluiu = ramo_compra(ctx)
    else:
        print("Cancelado, nada foi alterado.")
        return

    if concluiu and sim("\nDeseja formalizar a observação em HTML?"):
        gerar_descricao_html(numero_tray, texto_itens(pedido.get("itens", []), "; "), ctx["personalizacao"])


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
