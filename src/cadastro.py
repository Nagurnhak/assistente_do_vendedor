"""
Cadastro: varredura das tabelas de fornecedor e correção de valores (Bling -> Tray).

Fluxo:
  1. ler_tabela()   lê a tabela do fornecedor (código, descrição, preço de tabela);
  2. varredura()    cruza com o Bling (vínculo produto x fornecedor, pelo código do fornecedor)
                    e com a Tray (vínculo produto x loja do Bling -> produto/variação da Tray);
  3. aplicar()      grava no Bling (custo no vínculo do fornecedor, preço de venda no produto e
                    no vínculo da loja) e envia os mesmos valores para a Tray pela API.

Produtos "sob consulta" na Tray (preço 0 + upon_request) só têm o CUSTO atualizado: o preço de venda
não é gravado em lugar nenhum, para não aparecer no site.

Cada aplicação fica registrada em cadastro_historico.jsonl (valores antes/depois), para conferência.

Teste rápido (só leitura):  py cadastro.py "caminho/da/tabela.xlsx"
"""

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime

from configuracao import carregar_config, pasta_base

ARQUIVO_HISTORICO = os.path.join(pasta_base(), "cadastro_historico.jsonl")
TOLERANCIA = 0.05  # diferença em R$ abaixo da qual o valor é considerado em dia

# Perfis de fornecedor (EXEMPLOS fictícios: os reais ficam no config.json, em "cadastro" -> "fornecedores",
# que pode sobrescrever qualquer campo). Margens e descontos são condição comercial: não vão para o código.
FORNECEDORES = {
    # Aba única com cabeçalho "CÓDIGO", descrição e preço de tabela; código numérico exato.
    "Fornecedor A": {
        "contatos_bling": [710],
        "aba": "Tabela",
        "desconto": 0.10,
        "ipi": 0.05,
        "frete": 0.05,
        "margem": 2.0,
    },
    # Tabela semanal: uma aba por linha de produto, código na coluna C só na 1ª linha de cada produto (as cores
    # vêm embaixo), preço na coluna I e, na J, o preço destacado em VERMELHO quando é promocional.
    "Fornecedor B": {
        "contatos_bling": [711],
        "formato": "semanal_por_abas",
        "abas_ignorar": ["CAPA"],
        "colunas": {"codigo": 3, "nome": 4, "cor": 5, "preco": 9, "destaque": 10},
        "casar": "prefixo",                              # Bling: código da tabela + cor/sufixo ("FB-1100 PAI")
        "padrao_base": r"FB-\d+",
        "desconto": 0.20,
        "desconto_promocional": 0.05,
        "ipi": 0.03,
        "frete": 0.0,
        "margem": 1.8,
    },
}


def _cfg():
    try:
        return carregar_config().get("cadastro") or {}
    except Exception:
        return {}


ARQUIVO_PERFIS = os.path.join(pasta_base(), "cadastro_fornecedores.json")  # ajustes salvos pela tela
CAMPOS_CALCULO = ("desconto", "ipi", "frete", "margem")


def _perfis_salvos():
    try:
        with open(ARQUIVO_PERFIS, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def fornecedores():
    """Perfis: padrão do código < config.json ("cadastro" -> "fornecedores") < o que a tela salvou."""
    perfis = {nome: dict(p) for nome, p in FORNECEDORES.items()}
    for origem in ((_cfg().get("fornecedores") or {}), _perfis_salvos()):
        for nome, extra in origem.items():
            perfis.setdefault(nome, {}).update(extra)
    return perfis


def salvar_calculo(nome, valores):
    """Grava desconto, IPI, frete e margem do fornecedor (frações; margem em vezes) e, se houver,
    o desconto dos preços em vermelho (promocionais)."""
    salvos = _perfis_salvos()
    salvo = salvos.setdefault(nome, {})
    salvo.update({k: float(valores[k]) for k in CAMPOS_CALCULO})
    if valores.get("desconto_promocional") is not None:
        salvo["desconto_promocional"] = float(valores["desconto_promocional"])
    else:
        salvo.pop("desconto_promocional", None)
    temporario = ARQUIVO_PERFIS + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(salvos, f, ensure_ascii=False, indent=1)
    os.replace(temporario, ARQUIVO_PERFIS)


def loja_tray_bling():
    return int(_cfg().get("loja_tray_bling") or 0)


def so_digitos(texto):
    return re.sub(r"\D", "", str(texto or ""))


def _sem_acento(texto):
    base = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in base if unicodedata.category(c) != "Mn").upper().strip()


def calcular(preco_tabela, perfil, promocional=False):
    """(compra, custo, venda) a partir do preço de tabela: compra = tabela - desconto (valor da OC);
    custo = compra + IPI + frete; venda = custo x margem. Preço promocional usa o desconto promocional."""
    desconto = perfil.get("desconto", 0)
    if promocional and "desconto_promocional" in perfil:
        desconto = perfil["desconto_promocional"]
    compra = round(preco_tabela * (1 - desconto), 2)
    custo = round(preco_tabela * (1 - desconto) * (1 + perfil.get("ipi", 0)) * (1 + perfil.get("frete", 0)), 2)
    return compra, custo, round(custo * perfil["margem"], 2)


def normalizar_codigo(texto):
    """Código alfanumérico comparável: maiúsculo, sem espaços/acentos e sem o 'PAI' do produto pai."""
    codigo = re.sub(r"\s+", "", _sem_acento(texto))
    return re.sub(r"PAI$", "", codigo)


# ---------------------------------------------------------------------------
# TABELA DO FORNECEDOR
# ---------------------------------------------------------------------------

def ler_tabela(arquivo, perfil, avisar=print):
    """{codigo: {'descricao', 'preco', 'promocional', 'linhas'}} conforme o formato do fornecedor."""
    if perfil.get("formato") == "semanal_por_abas":
        return _ler_tabela_semanal(arquivo, perfil, avisar)
    return _ler_tabela_codigo(arquivo, perfil, avisar)


def _vermelho(celula):
    cor = celula.font.color if celula.font else None
    return bool(cor is not None and cor.type == "rgb" and str(cor.rgb).upper().endswith("FF0000"))


def _ler_tabela_semanal(arquivo, perfil, avisar):
    """Uma aba por linha de produto. O código vale para as linhas de baixo (cores) até o próximo código;
    linhas de cor sem preço herdam o preço do código. Vermelho na coluna do preço = promocional."""
    import openpyxl

    avisar("Abrindo a tabela (leva um pouco: ela tem as fotos dos produtos)...")
    wb = openpyxl.load_workbook(arquivo)  # sem read_only: a cor da fonte só vem assim
    col = perfil["colunas"]
    ignorar = {_sem_acento(a) for a in perfil.get("abas_ignorar", [])}
    tabela = {}
    for ws in wb.worksheets:
        if _sem_acento(ws.title) in ignorar:
            continue
        codigo = None
        for r in range(1, ws.max_row + 1):
            bruto = ws.cell(r, col["codigo"]).value
            if bruto and re.search(perfil.get("padrao_base", r"\w"), str(bruto).upper()):
                codigo = normalizar_codigo(bruto)
            preco = ws.cell(r, col["preco"]).value
            if not codigo or not isinstance(preco, (int, float)) or preco <= 0:
                continue
            promocional = _vermelho(ws.cell(r, col["destaque"])) or _vermelho(ws.cell(r, col["preco"]))
            linha = {"cor": " ".join(str(ws.cell(r, col["cor"]).value or "").split()),
                     "preco": float(preco), "promocional": promocional}
            if codigo not in tabela:
                nome = " ".join(str(ws.cell(r, col["nome"]).value or "").split())
                tabela[codigo] = {"descricao": nome, "preco": linha["preco"], "promocional": promocional,
                                  "aba": ws.title.strip(), "linhas": []}
            tabela[codigo]["linhas"].append(linha)
    wb.close()
    promo = sum(1 for t in tabela.values() if t["promocional"])
    avisar(f"{len(tabela)} produtos com preço na tabela ({promo} com preço promocional em vermelho).")
    return tabela


def _ler_tabela_codigo(arquivo, perfil, avisar):
    """Aba única com cabeçalho 'CÓDIGO'."""
    import openpyxl

    avisar("Abrindo a tabela (arquivos grandes demoram um pouco)...")
    wb = openpyxl.load_workbook(arquivo, read_only=True, data_only=True)
    if perfil["aba"] not in wb.sheetnames:
        raise RuntimeError(f"A tabela não tem a aba '{perfil['aba']}'. Abas: {', '.join(wb.sheetnames)}")
    linhas = wb[perfil["aba"]].iter_rows(values_only=True)

    col_cod = col_desc = col_preco = None
    for linha in linhas:
        cab = [_sem_acento(c) for c in linha]
        if "CODIGO" in cab:
            col_cod = cab.index("CODIGO")
            col_desc = next((i for i, c in enumerate(cab) if c.startswith("DESCRICAO")), col_cod + 1)
            col_preco = next((i for i, c in enumerate(cab) if c.startswith(("TAB", "PRECO"))), col_desc + 1)
            break
    if col_cod is None:
        raise RuntimeError(f"Não achei a coluna 'CÓDIGO' na aba '{perfil['aba']}'.")

    tabela = {}
    for linha in linhas:
        if len(linha) <= col_preco:
            continue
        codigo, preco = so_digitos(linha[col_cod]), linha[col_preco]
        if codigo and isinstance(preco, (int, float)) and preco > 0:
            descricao = " ".join(str(linha[col_desc] or "").replace("\xa0", " ").split())
            tabela[codigo] = {"descricao": descricao, "preco": float(preco), "promocional": False}
    wb.close()
    avisar(f"{len(tabela)} itens com preço na tabela.")
    return tabela


# ---------------------------------------------------------------------------
# LEITURAS (Bling e Tray)
# ---------------------------------------------------------------------------

def _paginar_bling(caminho, params, avisar=None, rotulo=""):
    from BLING import chamar_bling
    todos, pagina = [], 1
    while True:
        dados = chamar_bling("GET", caminho, params={**params, "pagina": pagina, "limite": 100}).get("data") or []
        todos += dados
        if avisar and pagina % 20 == 0:
            avisar(f"  {rotulo}: {len(todos)} lidos...")
        if len(dados) < 100:
            return todos
        pagina += 1


def vinculos_fornecedor(perfil, avisar=print):
    avisar("Lendo os produtos do fornecedor no Bling...")
    vinculos = []
    for contato in perfil["contatos_bling"]:
        vinculos += _paginar_bling("/produtos/fornecedores", {"idFornecedor": contato})
    return vinculos


def vinculos_ocultos(vinc_forn, prod_bling, perfil, avisar=print):
    """Variações cujo vínculo com o fornecedor não aparece na listagem do Bling (nem no GET pelo id), mas
    existe: o produto mostra fornecedor, código e preços, e o PUT pelo id altera normalmente. Acha as
    variações pelos produtos pai do fornecedor e monta o vínculo a partir do que está no produto."""
    from BLING import chamar_bling
    com_vinculo = {v["produto"]["id"] for v in vinc_forn}
    pais = {p["id"] for p in prod_bling.values() if p.get("formato") == "V"}
    pais |= {p["idProdutoPai"] for p in prod_bling.values() if p.get("idProdutoPai")}
    contatos = set(perfil["contatos_bling"])
    avisar(f"Procurando variações sem vínculo listado em {len(pais)} produtos pai...")
    ocultos = []
    for n, pai in enumerate(pais, 1):
        variacoes = (chamar_bling("GET", f"/produtos/{pai}").get("data") or {}).get("variacoes") or []
        for var in variacoes:
            if var["id"] in com_vinculo:
                continue
            produto = chamar_bling("GET", f"/produtos/{var['id']}").get("data") or {}
            f = produto.get("fornecedor") or {}
            if f.get("id") and (f.get("contato") or {}).get("id") in contatos:
                ocultos.append({"id": f["id"], "descricao": produto.get("nome", ""), "codigo": f.get("codigo") or "",
                                "precoCusto": f.get("precoCusto"), "precoCompra": f.get("precoCompra"),
                                "padrao": True, "produto": {"id": var["id"]},
                                "fornecedor": {"id": f["contato"]["id"]}, "oculto": True})
        if n % 25 == 0:
            avisar(f"  {n}/{len(pais)} produtos pai...")
    avisar(f"{len(ocultos)} variações com vínculo oculto encontradas.")
    return ocultos


def produtos_bling(ids, avisar=print):
    from BLING import chamar_bling
    avisar(f"Lendo preços de {len(ids)} produtos no Bling...")
    produtos, ids = {}, list(ids)
    for i in range(0, len(ids), 100):
        lote = ids[i:i + 100]
        dados = chamar_bling("GET", "/produtos", params={"idsProdutos[]": lote, "limite": 100}).get("data") or []
        for p in dados:
            produtos[p["id"]] = p
    return produtos


def vinculos_loja(avisar=print):
    avisar("Lendo os vínculos dos produtos com a loja Tray no Bling (leva 1 a 2 minutos)...")
    vinculos = _paginar_bling("/produtos/lojas", {"idLoja": loja_tray_bling()}, avisar, "vínculos de loja")
    return {v["produto"]["id"]: v for v in vinculos}


def catalogo_tray(avisar=print):
    """Produtos e variações da Tray, por id (para achar o item apontado pelo vínculo do Bling)."""
    from TRAY import chamar_tray

    def paginar(caminho, chave):
        itens, pagina = [], 1
        while True:
            r = chamar_tray("GET", caminho, params={"limit": 50, "page": pagina})
            itens += [x[chave] for x in r.get(chave + "s") or []]
            if pagina * 50 >= int(r["paging"]["total"]):
                return itens
            pagina += 1
            if pagina % 20 == 0:
                avisar(f"  Tray: {len(itens)} {chave.lower()}s lidos...")

    avisar("Lendo produtos e variações da Tray (leva alguns minutos)...")
    produtos = {p["id"]: p for p in paginar("/products", "Product")}
    variacoes = {v["id"]: v for v in paginar("/products/variants", "Variant")}
    return produtos, variacoes


# ---------------------------------------------------------------------------
# VARREDURA
# ---------------------------------------------------------------------------

def _num(valor):
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _ligar_tray(pb, vl, prod_tray, var_tray):
    """Campos tray_* do item do Bling. O código do vínculo com a loja é o id da VARIAÇÃO na Tray quando o
    produto do Bling é filho de outro, e o id do PRODUTO quando é simples (os dois tipos de id se repetem
    na Tray, por isso a regra)."""
    codigo_loja = str((vl or {}).get("codigo") or "").strip()
    filho = bool(pb.get("idProdutoPai"))
    if filho and codigo_loja in var_tray:
        v = var_tray[codigo_loja]
        pai = prod_tray.get(v["product_id"]) or {}
        return dict(tray_tipo="variacao", tray_id=codigo_loja, tray_produto_id=v["product_id"],
                    tray_nome=pai.get("name", ""), tray_venda=_num(v.get("price")),
                    tray_custo=_num(v.get("cost_price")), sob_consulta=str(pai.get("upon_request")) == "1",
                    tray_ativo=str(pai.get("available")) == "1")
    if not filho and codigo_loja in prod_tray:
        p = prod_tray[codigo_loja]
        return dict(tray_tipo="produto", tray_id=codigo_loja, tray_produto_id=codigo_loja,
                    tray_nome=p.get("name", ""), tray_venda=_num(p.get("price")),
                    tray_custo=_num(p.get("cost_price")), sob_consulta=str(p.get("upon_request")) == "1",
                    tray_ativo=str(p.get("available")) == "1")
    return {}


def casar_codigo(codigo_bling, tabela, perfil):
    """Liga o código do fornecedor gravado no Bling a uma linha da tabela.
    Devolve (situação, código da tabela, linha | motivo), com situação:
      ok        achou a linha (preço e se é promocional);
      fora      código válido que não está na tabela (provável saída de linha);
      invalido  código que não parece do fornecedor (ex.: "160" da medida);
      ambiguo   bate com mais de um preço na tabela e não dá para saber qual;
      vazio     vínculo sem código."""
    if not str(codigo_bling or "").strip():
        return "vazio", None, None
    if perfil.get("casar") != "prefixo":  # código numérico exato 
        codigo = so_digitos(codigo_bling)
        if not codigo:  # produto pai com código só de nome ("LINA PAI"): não tem preço próprio na tabela
            return "vazio", None, None
        if len(codigo) < perfil.get("digitos_minimos", 6):
            return "invalido", None, "código curto demais para ser da tabela"
        return ("ok", codigo, tabela[codigo]) if codigo in tabela else ("fora", codigo, None)

    codigo = normalizar_codigo(codigo_bling)
    if not codigo:  # era só "PAI"
        return "vazio", None, None
    base = re.match(perfil.get("padrao_base", r".+"), codigo)
    if not base:
        return "invalido", None, "não começa com o padrão de código do fornecedor"

    def escolher(chave, sufixo):
        """Linha do código; se as cores têm preços diferentes, usa a cor que aparece no sufixo."""
        linhas = tabela[chave]["linhas"]
        if len({(l["preco"], l["promocional"]) for l in linhas}) == 1:
            return "ok", chave, {**tabela[chave], **linhas[0]}
        sufixo = normalizar_codigo(sufixo)
        achadas = [l for l in linhas if sufixo and normalizar_codigo(l["cor"]) and
                   (normalizar_codigo(l["cor"]) in sufixo or sufixo in normalizar_codigo(l["cor"]))]
        if len({(l["preco"], l["promocional"]) for l in achadas}) == 1:
            return "ok", chave, {**tabela[chave], **achadas[0]}
        return "ambiguo", chave, f"o código {chave} tem preços diferentes por cor/modelo na tabela"

    # 1) o código da tabela é o começo do código do Bling (FB-1100 -> "FB-1100 PAI", "FB-1100CINZA").
    #    Cuidado com letras do modelo que são o começo de uma cor: "FB-1102BRANCA" é a FB-1102 Branca,
    #    não o modelo FB-1102B + "RANCA". Se as letras do modelo + o resto formam uma cor da tabela, não vale.
    cores = {normalizar_codigo(l["cor"]) for t in tabela.values() for l in t.get("linhas", []) if len(l["cor"]) >= 3}

    def letras_viram_cor(c):
        letras = c[len(base.group(0)):]
        resto = codigo[len(base.group(0)):]
        return bool(letras) and any(resto.startswith(cor) and len(cor) > len(letras) for cor in cores
                                    if cor.startswith(letras))

    prefixos = [c for c in tabela if codigo.startswith(c) and not codigo[len(c):len(c) + 1].isdigit()
                and not letras_viram_cor(c)]
    if prefixos:
        chave = max(prefixos, key=len)
        return escolher(chave, codigo[len(chave):])
    # 2) só a base bate (FB-1102CINZA x FB-1102CR / FB-1102B; FB-2216BASE x FB-2216COMPLETA): não dá para
    #    saber o modelo pelo código, então vai para conferência em vez de ganhar um preço por palpite.
    candidatos = sorted(c for c in tabela if c.startswith(base.group(0)) and
                        not c[len(base.group(0)):len(base.group(0)) + 1].isdigit())
    if candidatos:
        return "ambiguo", None, (f"o código do Bling não bate inteiro com a tabela; modelos parecidos: "
                                 f"{', '.join(candidatos[:4])}")
    return "fora", base.group(0), None


def varredura(arquivo, nome_fornecedor, avisar=print, calculo=None):
    """
    Devolve {'itens': [...], 'novos': [...], 'fora': [...], 'invalidos': [...], 'resumo': {...}}.
    Cada item (código da tabela já vinculado no Bling) tem os valores atuais, os calculados e o status:
      em_dia | desatualizado | sob_consulta (só custo) | sem_tray (produto do Bling sem item na Tray)
    calculo: desconto/ipi/frete/margem desta tabela (sobrepõe o perfil salvo).
    """
    perfil = {**fornecedores()[nome_fornecedor], **{k: v for k, v in (calculo or {}).items() if v is not None}}
    if calculo and calculo.get("desconto_promocional") is None:
        perfil.pop("desconto_promocional", None)  # campo vazio na tela: sem regra do vermelho
    avisar("Cálculo: tabela −{desconto:.2%} de desconto, +{ipi:.2%} IPI, +{frete:.2%} frete, margem {margem}x"
           .format(**{k: perfil.get(k, 0) for k in CAMPOS_CALCULO})
           + (f"; preço em vermelho: −{perfil['desconto_promocional']:.2%}" if "desconto_promocional" in perfil else ""))
    tabela = ler_tabela(arquivo, perfil, avisar)
    vinc_forn = vinculos_fornecedor(perfil, avisar)
    prod_bling = produtos_bling({v["produto"]["id"] for v in vinc_forn}, avisar)
    ocultos = vinculos_ocultos(vinc_forn, prod_bling, perfil, avisar)
    vinc_forn += ocultos
    prod_bling.update(produtos_bling({v["produto"]["id"] for v in ocultos}, avisar))
    casados = {}                       # código da tabela -> [(vínculo, linha da tabela)]
    fora_vinc, invalidos_vinc = [], []  # (vínculo, motivo)
    for v in vinc_forn:
        situacao, codigo, linha = casar_codigo(v.get("codigo"), tabela, perfil)
        if situacao == "ok":
            casados.setdefault(codigo, []).append((v, linha))
        elif situacao == "fora":
            fora_vinc.append((v, codigo))
        elif situacao in ("invalido", "ambiguo"):
            invalidos_vinc.append((v, linha))

    vinc_loja = vinculos_loja(avisar)
    prod_tray, var_tray = catalogo_tray(avisar)

    itens = []
    for codigo, pares in casados.items():
        for vf, linha_tab in pares:
            compra, custo, venda = calcular(linha_tab["preco"], perfil, linha_tab.get("promocional"))
            pid = vf["produto"]["id"]
            pb = prod_bling.get(pid) or {}
            vl = vinc_loja.get(pid)
            item = {
                "codigo": codigo,
                "codigo_bling": str(vf.get("codigo") or ""),
                "descricao_tabela": linha_tab["descricao"],
                "preco_tabela": linha_tab["preco"],
                "promocional": bool(linha_tab.get("promocional")),
                "compra_nova": compra,
                "custo_novo": custo,
                "venda_nova": venda,
                "bling_produto_id": pid,
                "bling_pai_id": pb.get("idProdutoPai"),
                "bling_formato": pb.get("formato"),
                "bling_nome": pb.get("nome") or vf.get("descricao") or "",
                "bling_venda": _num(pb.get("preco")),
                "bling_vinculo_fornecedor": vf,
                "bling_custo": _num(vf.get("precoCusto")),
                "bling_compra": _num(vf.get("precoCompra")),
                "bling_vinculo_loja": vl,
                "tray_tipo": None, "tray_id": None, "tray_produto_id": None,
                "tray_nome": "", "tray_venda": None, "tray_custo": None, "sob_consulta": False,
            }
            item.update(_ligar_tray(pb, vl, prod_tray, var_tray))

            difere = lambda a, b: a is None or abs(a - b) > TOLERANCIA
            custos = ((item["bling_compra"], compra), (item["bling_custo"], custo), (item["tray_custo"], custo))
            if pb.get("formato") == "E":
                # Kit/estrutura: o Bling calcula o custo pelos componentes e o preço pode incluir peças a mais
                # (ex.: cadeira com assento). O preço da tabela é o da peça básica: não aplica sozinho.
                item["status"] = "kit"
            elif item["tray_id"] is None:
                item["status"] = "sem_tray"
            elif item["sob_consulta"]:
                item["status"] = "sob_consulta" if any(difere(a, b) for a, b in custos) else "em_dia"
            elif pb.get("formato") == "V":
                # Produto pai: a venda dele é a menor das variações ("a partir de"), não o preço da tabela.
                item["status"] = "desatualizado" if any(difere(a, b) for a, b in custos) else "em_dia"
            elif any(difere(a, b) for a, b in custos + ((item["bling_venda"], venda), (item["tray_venda"], venda))):
                item["status"] = "desatualizado"
            else:
                item["status"] = "em_dia"
            itens.append(item)

    novos = []
    for c, t in tabela.items():
        if c not in casados:
            _, custo, venda = calcular(t["preco"], perfil, t.get("promocional"))
            novos.append({"codigo": c, "descricao": t["descricao"], "preco": t["preco"],
                          "promocional": t.get("promocional", False), "custo_novo": custo, "venda_nova": venda})

    def resumo_bling(v, codigo, motivo=""):
        pb = prod_bling.get(v["produto"]["id"]) or {}
        item = {"codigo": codigo or str(v.get("codigo") or ""), "codigo_bling": str(v.get("codigo") or ""),
                "motivo": motivo, "bling_nome": pb.get("nome") or v.get("descricao") or "",
                "bling_produto_id": v["produto"]["id"], "bling_ativo": pb.get("situacao") == "A",
                "tray_id": None, "tray_tipo": None, "tray_nome": "", "tray_ativo": False}
        item.update(_ligar_tray(pb, vinc_loja.get(v["produto"]["id"]), prod_tray, var_tray))
        return item

    # Fora da tabela: código válido que sumiu da tabela nova (provável saída de linha -> pode inativar).
    fora = [resumo_bling(v, c) for v, c in fora_vinc]
    invalidos = [resumo_bling(v, None, motivo) for v, motivo in invalidos_vinc]
    resumo = {s: sum(1 for i in itens if i["status"] == s)
              for s in ("em_dia", "desatualizado", "sob_consulta", "sem_tray", "kit")}
    resumo.update(novos=len(novos), fora=len(fora), codigo_invalido=len(invalidos), tabela=len(tabela))
    avisar("Varredura concluída: " + ", ".join(f"{k} {v}" for k, v in resumo.items()))
    return {"fornecedor": nome_fornecedor, "arquivo": arquivo, "itens": itens, "novos": novos, "fora": fora,
            "invalidos": invalidos, "resumo": resumo, "quando": datetime.now().isoformat(timespec="seconds"),
            "calculo": {k: perfil.get(k, 0) for k in CAMPOS_CALCULO}}


def inativar(itens, avisar=print):
    """Item que saiu de linha: situação Inativo no Bling e produto desligado na Tray (sem apagar nada).
    Variação: só a variação fica indisponível; o produto principal continua."""
    from BLING import chamar_bling
    from TRAY import chamar_tray
    lote = datetime.now().isoformat(timespec="seconds")
    ok, falhas = 0, []
    for item in itens:
        try:
            chamar_bling("PATCH", f"/produtos/{item['bling_produto_id']}", json={"situacao": "I"})
            if item["tray_tipo"] == "produto":
                chamar_tray("PUT", f"/products/{item['tray_id']}", json={"Product": {"available": 0}})
            elif item["tray_tipo"] == "variacao":
                chamar_tray("PUT", f"/products/variants/{item['tray_id']}", json={"Variant": {"available": 0}})
            ok += 1
            _registrar({"lote": lote, "acao": "inativar", "codigo": item["codigo"],
                        "bling_produto_id": item["bling_produto_id"], "tray_id": item["tray_id"],
                        "tray_tipo": item["tray_tipo"]})
        except Exception as erro:
            falhas.append((item, str(erro)))
    avisar(f"{ok} itens inativados.")
    return ok, falhas


# ---------------------------------------------------------------------------
# APLICAÇÃO (Bling primeiro, depois Tray)
# ---------------------------------------------------------------------------

def _registrar(evento):
    with open(ARQUIVO_HISTORICO, "a", encoding="utf-8") as f:
        f.write(json.dumps(evento, ensure_ascii=False) + "\n")


def _com_nova_tentativa(funcao, *args, **kwargs):
    """O Bling às vezes recusa (400) ou falha (500) uma gravação que passa logo depois: tenta mais 2 vezes."""
    for tentativa in range(3):
        try:
            return funcao(*args, **kwargs)
        except Exception as erro:
            status = getattr(getattr(erro, "response", None), "status_code", None)
            if tentativa == 2 or status not in (400, 409, 500, 502, 503, 504):
                raise
            time.sleep(2 * (tentativa + 1))


def gravar_preco_loja(id_vinculo, preco):
    """Preço do produto na loja Tray dentro do Bling. Relê o vínculo atual; se a promoção cadastrada ficar
    igual ou acima do preço novo, o Bling recusa a gravação: nesse caso a promoção é zerada."""
    from BLING import chamar_bling
    atual = _com_nova_tentativa(chamar_bling, "GET", f"/produtos/lojas/{id_vinculo}").get("data") or {}
    corpo, feito = {**atual, "preco": preco}, []
    if _num(atual.get("precoPromocional")) >= preco:
        corpo["precoPromocional"] = 0
        feito.append("promoção antiga zerada")
    _com_nova_tentativa(chamar_bling, "PUT", f"/produtos/lojas/{id_vinculo}", json=corpo)
    return feito + ["Bling loja"]


def aplicar_item(item):
    """Grava os valores novos de um item. Devolve a lista do que foi alterado."""
    from BLING import chamar_bling as _chamar_bling
    from TRAY import chamar_tray
    chamar_bling = lambda *a, **k: _com_nova_tentativa(_chamar_bling, *a, **k)

    custo, venda, feito = item["custo_novo"], item["venda_nova"], []
    so_custo = item["sob_consulta"]

    # 1) Bling: vínculo produto x fornecedor. Compra = tabela com desconto (valor da OC);
    #    custo = compra + frete. Relê o vínculo inteiro: a listagem não traz o id do fornecedor.
    vf = item["bling_vinculo_fornecedor"]
    compra = item["compra_nova"]
    if abs(_num(vf.get("precoCusto")) - custo) > TOLERANCIA or abs(_num(vf.get("precoCompra")) - compra) > TOLERANCIA:
        atual = chamar_bling("GET", f"/produtos/fornecedores/{vf['id']}").get("data") or {}
        if not isinstance(atual, dict) or not atual:  # vínculo oculto: o GET vem vazio, o PUT funciona
            atual = {k: vf[k] for k in ("id", "descricao", "codigo", "padrao", "produto", "fornecedor") if k in vf}
        if not (atual.get("fornecedor") or {}).get("id"):
            raise RuntimeError("vínculo do fornecedor sem id de contato no Bling")
        chamar_bling("PUT", f"/produtos/fornecedores/{vf['id']}", json={**atual, "precoCusto": custo, "precoCompra": compra})
        feito.append("Bling custo")

    if not so_custo:
        # 2) Bling: preço de venda do produto
        # Produto pai com variações (formato V): salvar o pai faz o Bling regravar todas as variações dele
        # (e pode voltar preços ou travar por erro numa variação). A venda do pai fica só na loja e na Tray.
        if item.get("bling_formato") != "V" and abs(item["bling_venda"] - venda) > TOLERANCIA:
            chamar_bling("PATCH", f"/produtos/{item['bling_produto_id']}", json={"preco": venda})
            feito.append("Bling venda")
        # 3) Bling: preço do vínculo com a loja Tray
        vl = item["bling_vinculo_loja"]
        if vl and abs(_num(vl.get("preco")) - venda) > TOLERANCIA:
            feito += gravar_preco_loja(vl["id"], venda)

    # 4) Tray: os mesmos valores (sob consulta: só o custo)
    if item["tray_id"]:
        dados = {"cost_price": custo} if so_custo else {"cost_price": custo, "price": venda}
        if item["tray_tipo"] == "variacao":
            chamar_tray("PUT", f"/products/variants/{item['tray_id']}", json={"Variant": dados})
        else:
            chamar_tray("PUT", f"/products/{item['tray_id']}", json={"Product": dados})
        feito.append("Tray")
    return feito


def aplicar(itens, avisar=print):
    """Aplica uma lista de itens da varredura. Erros num item não param os outros."""
    lote = datetime.now().isoformat(timespec="seconds")
    ok, falhas = 0, []
    for n, item in enumerate(itens, 1):
        antes = {k: item[k] for k in ("bling_compra", "bling_custo", "bling_venda", "tray_custo", "tray_venda")}
        try:
            feito = aplicar_item(item)
            ok += 1
            _registrar({"lote": lote, "codigo": item["codigo"], "bling_produto_id": item["bling_produto_id"],
                        "tray_id": item["tray_id"], "tray_tipo": item["tray_tipo"], "antes": antes,
                        "depois": {"compra": item["compra_nova"], "custo": item["custo_novo"],
                                   "venda": None if item["sob_consulta"] else item["venda_nova"]},
                        "alterado": feito})
        except Exception as erro:
            falhas.append((item, str(erro)))
            _registrar({"lote": lote, "codigo": item["codigo"], "erro": str(erro)})
        if n % 10 == 0 or n == len(itens):
            avisar(f"  {n}/{len(itens)} aplicados...")

    # A vitrine mostra o preço do produto principal: no Bling (pai e vínculo da loja) e na Tray,
    # ele acompanha a menor variação.
    pais = {(i["bling_pai_id"], i["tray_produto_id"]) for i in itens
            if i["tray_tipo"] == "variacao" and not i["sob_consulta"]}
    for pai_bling, pai_tray in pais:
        try:
            ajustar_preco_do_pai(pai_bling, pai_tray)
        except Exception as erro:
            falhas.append(({"codigo": f"produto principal {pai_tray}"}, f"preço do produto principal: {erro}"))

    # Conferência: relê o Bling e regrava o que não ficou (uma rodada), para o lote terminar conferido.
    gravados = [i for i in itens if not any(i is f[0] for f in falhas)]
    divergentes = conferir(gravados, avisar)
    if divergentes:
        avisar(f"{len(divergentes)} itens não ficaram certos no Bling; gravando de novo...")
        for item in divergentes:
            # Força regravar tudo do item (os valores da varredura podem dizer que já estava certo).
            item.update(bling_compra=-1, bling_custo=-1, bling_venda=-1)
            item["bling_vinculo_fornecedor"] = {**item["bling_vinculo_fornecedor"], "precoCusto": -1}
            if item.get("bling_vinculo_loja"):
                item["bling_vinculo_loja"] = {**item["bling_vinculo_loja"], "preco": -1}
            try:
                aplicar_item(item)
            except Exception as erro:
                falhas.append((item, f"na regravação: {erro}"))
        divergentes = conferir(divergentes, avisar)
        for item in divergentes:
            falhas.append((item, "o Bling não manteve o valor nem depois de gravar de novo"))
    _registrar({"lote": lote, "acao": "conferencia", "conferidos": len(gravados),
                "nao_ficaram": [i["codigo"] for i in divergentes]})
    return ok, falhas


def conferir(itens, avisar=print):
    """Relê no Bling compra/custo (vínculo do fornecedor) e venda (produto) e devolve os itens diferentes."""
    from BLING import chamar_bling
    avisar(f"Conferindo {len(itens)} itens no Bling...")
    divergentes = []
    for n, item in enumerate(itens, 1):
        try:
            vf = chamar_bling("GET", f"/produtos/fornecedores/{item['bling_vinculo_fornecedor']['id']}").get("data") or {}
            if not isinstance(vf, dict) or not vf:  # vínculo oculto: confere pelo que o produto mostra
                vf = (chamar_bling("GET", f"/produtos/{item['bling_produto_id']}").get("data") or {}).get("fornecedor") or {}
            certo = (abs(_num(vf.get("precoCompra")) - item["compra_nova"]) <= TOLERANCIA and
                     abs(_num(vf.get("precoCusto")) - item["custo_novo"]) <= TOLERANCIA)
            if certo and not item["sob_consulta"] and item.get("bling_formato") != "V":
                pb = chamar_bling("GET", f"/produtos/{item['bling_produto_id']}").get("data") or {}
                certo = abs(_num(pb.get("preco")) - item["venda_nova"]) <= TOLERANCIA
        except Exception:
            certo = False
        if not certo:
            divergentes.append(item)
        if n % 50 == 0:
            avisar(f"  {n}/{len(itens)} conferidos...")
    return divergentes


def ajustar_preco_do_pai(pai_bling, pai_tray):
    from BLING import chamar_bling as _chamar_bling
    from TRAY import chamar_tray
    chamar_bling = lambda *a, **k: _com_nova_tentativa(_chamar_bling, *a, **k)
    if pai_bling:
        pai = chamar_bling("GET", f"/produtos/{pai_bling}").get("data") or {}
        precos = [_num(v.get("preco")) for v in pai.get("variacoes") or [] if _num(v.get("preco")) > 0]
        # Não grava o preço do pai no Bling: isso regrava todas as variações (ver aplicar_item).
        for vl in chamar_bling("GET", "/produtos/lojas",
                               params={"idProduto": pai_bling, "idLoja": loja_tray_bling()}).get("data") or []:
            if precos and abs(_num(vl.get("preco")) - min(precos)) > TOLERANCIA:
                gravar_preco_loja(vl["id"], min(precos))
    variacoes = chamar_tray("GET", "/products/variants", params={"product_id": pai_tray, "limit": 50}).get("Variants") or []
    precos = [float(v["Variant"]["price"]) for v in variacoes if float(v["Variant"]["price"] or 0) > 0]
    if precos:
        chamar_tray("PUT", f"/products/{pai_tray}", json={"Product": {"price": min(precos)}})


# ---------------------------------------------------------------------------
# RELATÓRIO
# ---------------------------------------------------------------------------

STATUS_TEXTO = {"em_dia": "Em dia", "desatualizado": "Desatualizado", "sob_consulta": "Sob consulta (só custo)",
                "sem_tray": "Sem item na Tray", "kit": "Kit/estrutura (conferir à mão)"}


def exportar_excel(resultado, caminho):
    import openpyxl
    from openpyxl.styles import Font

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Vinculados"
    ws.append(["Status", "Código tabela", "Código Bling", "Descrição (tabela)", "Produto Bling", "Produto Tray",
               "Preço tabela", "Promocional (vermelho)", "Compra Bling", "Compra nova", "Custo Bling", "Custo Tray",
               "Custo novo", "Venda Bling", "Venda Tray", "Venda nova"])
    for i in sorted(resultado["itens"], key=lambda x: (x["status"], x["descricao_tabela"])):
        ws.append([STATUS_TEXTO[i["status"]], i["codigo"], i.get("codigo_bling", ""), i["descricao_tabela"],
                   i["bling_nome"], i["tray_nome"], i["preco_tabela"], "sim" if i.get("promocional") else "",
                   i["bling_compra"], i["compra_nova"], i["bling_custo"], i["tray_custo"], i["custo_novo"],
                   i["bling_venda"], i["tray_venda"], None if i["sob_consulta"] else i["venda_nova"]])
    novos = wb.create_sheet("Novos na tabela")
    novos.append(["Código", "Descrição", "Preço tabela", "Promocional (vermelho)", "Custo", "Venda"])
    for n in resultado["novos"]:
        novos.append([n["codigo"], n["descricao"], n["preco"], "sim" if n.get("promocional") else "",
                      n["custo_novo"], n["venda_nova"]])
    for titulo, chave in (("Fora da tabela", "fora"), ("Código a conferir no Bling", "invalidos")):
        aba = wb.create_sheet(titulo)
        aba.append(["Código", "Código no Bling", "Motivo", "Produto Bling", "ID Bling", "Produto Tray",
                    "Ativo na Tray"])
        for f in resultado.get(chave) or []:
            aba.append([f["codigo"], f.get("codigo_bling", ""), f.get("motivo", ""), f["bling_nome"],
                        f["bling_produto_id"], f.get("tray_nome", ""), "sim" if f.get("tray_ativo") else "não"])
    for aba in wb.worksheets:
        for c in aba[1]:
            c.font = Font(bold=True)
        aba.freeze_panes = "A2"
    wb.save(caminho)
    return caminho


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    resultado = varredura(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Fornecedor A")
    saida = os.path.join(pasta_base(), "varredura_teste.xlsx")
    print("Relatório:", exportar_excel(resultado, saida))
