"""
Lançar pedido na Tray pela API (tela "Lançar pedido" do Assistente).

- Cliente: busca na Tray por CNPJ/CPF (só números) ou pelo nome. Usa o cadastro existente.
- Produtos: busca pelo nome no Bling (a busca por nome da API da Tray volta vazia). O código do Bling
  aponta para a Tray: '12345' = produto 12345; '12345_678' = produto 12345, variação 678.
- Item sob medida: cria um produto na Tray no padrão "Sofá Personalizado ..." (marca Personalizados).
- Lançamento (POST /orders): os endereços vão numa LISTA com o tipo (0 = cobrança, 1 = entrega), como
  na documentação da Tray. Mandar um endereço só e sem tipo faz a Tray trocar o endereço principal do
  cadastro e deixar o pedido sem entrega.
- Depois de lançar: confere o pedido, devolve o endereço principal do cadastro se a Tray tiver trocado
  e avisa se a entrega não entrou (aí é corrigir em "Editar endereço" no painel; a API bloqueia a edição).

Só usa a Tray (TRAY.py) e o Bling (BLING.py). Nada aqui pergunta nada: a janela faz as perguntas.
"""

import re

import ferramentas_internas as fi

MARCA_PERSONALIZADOS = "Personalizados"
CAMPOS_ENDERECO = ("address", "number", "complement", "neighborhood", "city", "state", "zip_code")
STATUS_PADRAO = "PENDENTE"  # os outros status são trocados direto na Tray
_cache_parceiros = None


def parceiros_fixos():
    """Parceiros que aparecem direto na tela (id na Tray, nome): config.json -> "vendedores".
    Os demais só em "Outro parceiro"."""
    return [(str(v["id"]), v["nome"]) for v in fi.config().get("vendedores") or []]


def _tray(*args, **kwargs):
    """Carrega o TRAY.py só quando precisa (a demonstração troca o módulo antes)."""
    import TRAY
    return TRAY.chamar_tray(*args, **kwargs)


def _bling(*args, **kwargs):
    from BLING import chamar_bling
    return chamar_bling(*args, **kwargs)


def _so_numeros(texto):
    return re.sub(r"\D", "", str(texto or ""))


def _dinheiro(valor):
    return f"{float(valor):.2f}"


# ---------------------------------------------------------------------------
# CLIENTE
# ---------------------------------------------------------------------------

def _formatar_documento(numeros):
    if len(numeros) == 14:
        return f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/{numeros[8:12]}-{numeros[12:]}"
    if len(numeros) == 11:
        return f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}"
    return numeros


def buscar_clientes(texto):
    """[{id, nome, razao, documento, email}] pelo CNPJ/CPF (só os números servem) ou pelo nome."""
    texto = str(texto or "").strip()
    numeros = _so_numeros(texto)
    if len(numeros) == 14:
        params = {"cnpj": _formatar_documento(numeros)}
    elif len(numeros) == 11:
        params = {"cpf": _formatar_documento(numeros)}
    elif "@" in texto:
        params = {"email": texto}
    else:
        params = {"name": f"%{texto}%"}  # a Tray aceita % como curinga
    params["limit"] = 30
    achados = []
    for c in _tray("GET", "/customers", params=params).get("Customers", []):
        c = c.get("Customer", c)
        achados.append({"id": c.get("id"), "nome": c.get("name") or "", "razao": c.get("company_name") or "",
                        "documento": c.get("cnpj") or c.get("cpf") or "", "email": c.get("email") or ""})
    return achados


def dados_cliente(cliente_id):
    return _tray("GET", f"/customers/{cliente_id}").get("Customer", {})


def enderecos_cliente(cliente_id):
    """Endereços ATIVOS do cliente, o de cobrança (tipo 0) primeiro: [{id, tipo, texto, ...campos}].
    Cliente cadastrado agora não tem endereço tipo 0 na lista: aí o endereço do cadastro entra como cobrança."""
    r = _tray("GET", "/customers/addresses", params={"customer_id": cliente_id, "limit": 50})
    lista = []
    for e in r.get("CustomerAddresses", []):
        e = e.get("CustomerAddress", e)
        if str(e.get("active")) != "1":
            continue
        lista.append({**{k: e.get(k) or "" for k in CAMPOS_ENDERECO}, "id": e.get("id"), "tipo": str(e.get("type")),
                      "recipient": e.get("recipient") or "", "texto": texto_endereco(e)})
    if not any(e["tipo"] == "0" for e in lista):
        principal = endereco_principal(dados_cliente(cliente_id))
        if principal.get("address"):
            lista.append({**principal, "id": "cadastro", "tipo": "0", "recipient": "",
                          "texto": texto_endereco(principal)})
    return sorted(lista, key=lambda e: e["tipo"] != "0")


def texto_endereco(e):
    rua = ", ".join(x for x in (e.get("address"), e.get("number")) if x)
    if e.get("complement"):
        rua += f" - {e['complement']}"
    resto = " - ".join(x for x in (e.get("neighborhood"), "/".join(x for x in (e.get("city"), e.get("state")) if x))
                       if x)
    cep = _so_numeros(e.get("zip_code"))
    cep = f"CEP {cep[:5]}-{cep[5:]}" if len(cep) == 8 else ""
    return ", ".join(x for x in (rua, resto, cep) if x)


def endereco_principal(cliente):
    """O endereço do cadastro (que a Tray às vezes troca ao lançar o pedido)."""
    return {k: cliente.get(k) or "" for k in CAMPOS_ENDERECO}


# ---------------------------------------------------------------------------
# CLIENTE NOVO (dados mandados pelo WhatsApp)
# ---------------------------------------------------------------------------

# Ordem do modelo que mandamos ao cliente. Cada campo: (chave, rótulo no modelo, sinônimos aceitos na resposta)
CAMPOS_CLIENTE = [
    ("nome", "Nome completo (ou nome da empresa)", ("nome", "nome completo", "cliente", "nome da empresa",
                                                     "empresa", "razao social", "razão social")),
    ("documento", "CPF ou CNPJ", ("cpf", "cnpj", "cpf/cnpj", "cpf ou cnpj", "documento")),
    ("ie", "Inscrição estadual (empresa; ou Isento)", ("ie", "inscricao estadual", "insc estadual", "inscrição")),
    ("email", "E-mail", ("email", "e-mail", "e mail")),
    ("celular", "Celular / WhatsApp", ("celular", "whatsapp", "whats", "telefone", "tel", "fone", "contato")),
    ("cep", "CEP", ("cep",)),
    ("rua", "Endereço (rua / avenida)", ("endereco", "endereço", "rua", "avenida", "logradouro")),
    ("numero", "Número", ("numero", "número", "nº", "n°", "no")),
    ("complemento", "Complemento", ("complemento", "compl", "apto", "apartamento", "bloco")),
    ("bairro", "Bairro", ("bairro",)),
    ("cidade", "Cidade / UF", ("cidade", "cidade/uf", "municipio", "município")),
    ("recebe", "Quem recebe a entrega", ("quem recebe", "recebedor", "responsavel", "responsável",
                                          "destinatario", "destinatário", "recebe")),
]


def modelo_mensagem_cliente():
    """Texto para mandar ao cliente pelo WhatsApp, com os campos na ordem que o Assistente lê."""
    linhas = ["Para fazermos o seu cadastro, por favor responda com os dados abaixo (nessa ordem):", ""]
    linhas += [f"{rotulo}: " for _, rotulo, _ in CAMPOS_CLIENTE]
    return "\n".join(linhas)


def _limpar_rotulo(texto):
    import unicodedata
    base = unicodedata.normalize("NFD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z/ ]", "", base.lower()).strip()


def _chave_do_rotulo(rotulo):
    limpo = _limpar_rotulo(rotulo)
    for chave, texto_modelo, sinonimos in CAMPOS_CLIENTE:
        if limpo == _limpar_rotulo(texto_modelo) or limpo in (_limpar_rotulo(s) for s in sinonimos):
            return chave
    for chave, _, sinonimos in CAMPOS_CLIENTE:  # "CPF do responsável", "Endereço completo"...
        if any(limpo.startswith(_limpar_rotulo(s)) for s in sinonimos if len(s) > 3):
            return chave
    return None


# rótulos curtos que o cliente costuma escrever SEM dois-pontos ("CNPJ 12.345...", "cep 05417001")
_ROTULO_SEM_DOIS_PONTOS = re.compile(r"^(cpf|cnpj|cep|e-?mail|tel|telefone|celular|whats(?:app)?|ie|rg)\b[\s.:-]*(.+)$",
                                     re.I)
# linhas sem rótulo que sobram, na ordem do modelo (os campos com formato próprio já saíram antes)
_ORDEM_SEM_ROTULO = ("nome", "rua", "complemento", "bairro", "recebe")


def interpretar_dados_cliente(texto):
    """Lê a mensagem colada do WhatsApp e devolve {chave: valor} (só o que reconheceu).
    1) linhas 'Rótulo: valor' (o modelo ou nomes comuns) e 'CPF 123...' sem dois-pontos;
    2) linhas sem rótulo: pelo formato (e-mail, CPF/CNPJ, CEP, celular, número, 'Cidade/UF', 'Isento') e,
       o resto, pela ordem do modelo. completar_endereco() depois confere rua/bairro com o CEP."""
    dados, soltas = {}, []
    for bruta in str(texto or "").splitlines():
        linha = re.sub(r"^\[\d{1,2}:\d{2}.*?\]\s*[^:]+:\s*", "", bruta.strip())  # "[14:05, 28/10/2026] Fulano: "
        linha = re.sub(r"^\s*(?:[-•*]|\d{1,2}[.)])\s+", "", linha).strip().strip("*_ ")
        if not linha:
            continue
        achado = re.match(r"^([^:]{1,40}):\s*(.*)$", linha)
        chave = _chave_do_rotulo(achado[1]) if achado else None
        valor = achado[2].strip() if chave else ""
        if not chave:
            sem = _ROTULO_SEM_DOIS_PONTOS.match(linha)
            if sem:
                chave, valor = _chave_do_rotulo(sem[1]), sem[2].strip()
        if chave:
            if valor:
                dados.setdefault(chave, valor)
            continue
        soltas.append(linha)
    for linha in soltas:
        numeros = _so_numeros(linha)
        if "email" not in dados and re.fullmatch(r"\S+@\S+\.\S+", linha):
            dados["email"] = linha
        elif "documento" not in dados and len(numeros) in (11, 14) and re.fullmatch(r"[\d.\-/ ]+", linha) \
                and not re.fullmatch(r"\(?\d{2}\)?\s*9\d{4}-?\d{4}", linha.strip()):
            dados["documento"] = linha
        elif "cep" not in dados and re.fullmatch(r"\d{5}-?\d{3}", linha.strip()):
            dados["cep"] = linha
        elif "celular" not in dados and len(numeros) in (10, 11, 12, 13) and re.fullmatch(r"[\d()+\-. ]+", linha):
            dados["celular"] = linha
        elif "ie" not in dados and (re.fullmatch(r"isent[oa]", linha, re.I) or re.fullmatch(r"[\d.\-]{9,15}", linha)):
            dados["ie"] = linha
        elif "numero" not in dados and re.fullmatch(r"(?:n[º°o.]?\s*)?\d+[a-zA-Z]?|s/?n", linha, re.I):
            dados["numero"] = linha
        elif "cidade" not in dados and re.fullmatch(r".+?\s*[/\-,]\s*[A-Za-z]{2}", linha) and len(linha) < 40:
            dados["cidade"] = linha
        else:
            proxima = next((c for c in _ORDEM_SEM_ROTULO if c not in dados), None)
            if proxima:
                dados[proxima] = linha
    return _normalizar_cliente(dados)


def completar_endereco(dados, cep_info):
    """Usa o ViaCEP para preencher o que faltou e acertar linhas sem rótulo que caíram no campo errado
    (ex.: sem complemento, o bairro cai em 'complemento')."""
    d = dict(dados)
    if not cep_info:
        return d
    igual = lambda a, b: bool(a and b) and _limpar_rotulo(a) == _limpar_rotulo(b)
    for chave in ("rua", "complemento", "bairro", "recebe"):
        if igual(d.get(chave), cep_info.get("bairro")) and chave != "bairro":
            d.setdefault("bairro_tmp", d.pop(chave))
        elif igual(d.get(chave), cep_info.get("rua")) and chave != "rua":
            d.setdefault("rua_tmp", d.pop(chave))
    if "bairro_tmp" in d:
        d["bairro"] = d.pop("bairro_tmp")
    if "rua_tmp" in d:
        d["rua"] = d.pop("rua_tmp")
    for chave in ("rua", "bairro", "cidade", "uf"):
        if not d.get(chave) and cep_info.get(chave):
            d[chave] = cep_info[chave]
    return d


def _normalizar_cliente(d):
    d = dict(d)
    if d.get("documento"):
        d["documento"] = _formatar_documento(_so_numeros(d["documento"]))
    if d.get("cep"):
        cep = _so_numeros(d["cep"])
        d["cep"] = f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else d["cep"]
    if d.get("celular"):
        numeros = _so_numeros(d["celular"])
        d["celular"] = numeros[2:] if numeros.startswith("55") and len(numeros) > 11 else numeros
    if d.get("cidade") and "uf" not in d:
        achado = re.match(r"^(.*?)\s*[/\-,]\s*([A-Za-z]{2})$", d["cidade"].strip())
        if achado:
            d["cidade"], d["uf"] = achado[1].strip(), achado[2].upper()
    if d.get("rua") and not d.get("numero"):  # "Rua das Flores, nº 100"
        achado = re.match(r"^(.*?),?\s+(?:n[º°o.]?\s*)?(\d+[a-zA-Z]?)\s*(?:[,-]\s*(.*))?$", d["rua"])
        if achado and re.search(r"[A-Za-zÀ-ú]", achado[1]):
            d["rua"], d["numero"] = achado[1].strip(" ,"), achado[2]
            if achado[3] and not d.get("complemento"):
                d["complemento"] = achado[3].strip()
    if d.get("numero"):
        d["numero"] = re.sub(r"^(n[º°o.]?\s*)", "", d["numero"], flags=re.I).strip()
    return d


def consultar_cep(cep):
    """{rua, bairro, cidade, uf} pelo ViaCEP (ou {} se não achar)."""
    numeros = _so_numeros(cep)
    if len(numeros) != 8:
        return {}
    if fi.MODO_DEMO:
        import demo
        return dict(demo.CEPS.get(numeros) or {})
    import requests
    try:
        r = requests.get(f"https://viacep.com.br/ws/{numeros}/json/", timeout=10)
        j = r.json() if r.ok else {}
    except Exception:
        return {}
    if not j or j.get("erro"):
        return {}
    return {"rua": j.get("logradouro") or "", "bairro": j.get("bairro") or "", "cidade": j.get("localidade") or "",
            "uf": j.get("uf") or ""}


def consultar_cnpj(cnpj):
    """{razao, fantasia, rua, numero, complemento, bairro, cidade, uf, cep, situacao} na base pública da Receita."""
    numeros = _so_numeros(cnpj)
    if len(numeros) != 14 or fi.MODO_DEMO:  # a demonstração não consulta a base pública
        return {}
    import requests
    try:
        r = requests.get(f"https://brasilapi.com.br/api/cnpj/v1/{numeros}", timeout=15)
        j = r.json() if r.ok else {}
    except Exception:
        return {}
    if not j.get("razao_social"):
        return {}
    cep = _so_numeros(j.get("cep"))
    rua = " ".join(x for x in (j.get("descricao_tipo_de_logradouro"), j.get("logradouro")) if x).title()
    return {"razao": j.get("razao_social") or "", "fantasia": j.get("nome_fantasia") or "", "rua": rua,
            "numero": j.get("numero") or "", "complemento": (j.get("complemento") or "").title(),
            "bairro": (j.get("bairro") or "").title(), "cidade": (j.get("municipio") or "").title(),
            "uf": j.get("uf") or "", "cep": f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else "",
            "situacao": j.get("descricao_situacao_cadastral") or ""}


def cliente_existente(documento="", email=""):
    """O cliente já cadastrado com esse CPF/CNPJ ou e-mail (ou None)."""
    for texto in (documento, email):
        if texto and (len(_so_numeros(texto)) in (11, 14) or "@" in texto):
            achados = buscar_clientes(texto)
            if achados:
                return achados[0]
    return None


def cadastrar_cliente(d):
    """Cadastra na Tray. d: nome, documento, ie, razao, email, celular, cep, rua, numero, complemento, bairro,
    cidade, uf, recebe. O endereço vai como cadastro (cobrança) e como entrega. Devolve o id do cliente."""
    numeros = _so_numeros(d.get("documento"))
    if len(numeros) not in (11, 14):
        raise ValueError("CPF ou CNPJ inválido.")
    obrigatorios = {"nome": "nome", "email": "e-mail", "cep": "CEP", "rua": "endereço", "numero": "número",
                    "bairro": "bairro", "cidade": "cidade", "uf": "UF"}
    faltando = [rotulo for chave, rotulo in obrigatorios.items() if not str(d.get(chave) or "").strip()]
    if faltando:
        raise ValueError("Faltando: " + ", ".join(faltando) + ".")
    existente = cliente_existente(d.get("documento"), d.get("email"))
    if existente:
        raise ValueError(f"Já existe cliente com esse documento/e-mail: {existente['nome']} (id {existente['id']}).")
    pj = len(numeros) == 14
    endereco = {"address": d["rua"].strip(), "number": str(d["numero"]).strip(),
                "complement": (d.get("complemento") or "").strip(), "neighborhood": d["bairro"].strip(),
                "city": d["cidade"].strip(), "state": d["uf"].strip().upper()[:2], "zip_code": d["cep"].strip()}
    cliente = {"name": d["nome"].strip(), "email": d["email"].strip(), "type": "1" if pj else "0",
               "cellphone": _so_numeros(d.get("celular")), **endereco,
               "CustomerAddress": [{**endereco, "recipient": (d.get("recebe") or d["nome"]).strip(), "country": "BRA",
                                    "type": "1", "active": "1"}]}
    if pj:
        cliente.update({"cnpj": _formatar_documento(numeros), "company_name": (d.get("razao") or d["nome"]).strip(),
                        "state_inscription": (d.get("ie") or "Isento").strip()})
    else:
        cliente["cpf"] = _formatar_documento(numeros)
    r = _tray("POST", "/customers", json={"Customer": cliente})
    if not r.get("id"):
        raise RuntimeError(f"A Tray não devolveu o id do cliente: {r}")
    return str(r["id"])


# ---------------------------------------------------------------------------
# PRODUTOS
# ---------------------------------------------------------------------------

def ids_tray_do_codigo(codigo):
    """'12345' -> (12345, 0); '12345_678' -> (12345, 678); outro formato -> None."""
    achado = re.fullmatch(r"(\d+)(?:_(\d+))?", str(codigo or "").strip())
    if not achado:
        return None
    return int(achado[1]), int(achado[2] or 0)


def buscar_produtos(texto, limite=40):
    """Produtos cujo código aponta para a Tray: [{nome, codigo, product_id, variant_id, preco}].
    Primeiro o Bling (já traz cada variação com nome); depois a própria Tray, para pegar o que ainda não
    chegou no Bling (ex.: produto sob medida criado agora). Pai de variação fica de fora: escolhe-se a
    variação."""
    texto = str(texto or "").strip()
    if not texto:
        return []
    vistos, achados = set(), []
    ids = ids_tray_do_codigo(texto)
    buscas = [{"codigo": texto}] if ids else []
    buscas.append({"nome": texto})
    for filtro in buscas:
        for p in _bling("GET", "/produtos", params={**filtro, "limite": 100, "criterio": 2}).get("data", []):
            ids = ids_tray_do_codigo(p.get("codigo"))
            if p.get("formato") == "V" or not ids or ids in vistos:
                continue
            vistos.add(ids)
            achados.append({"nome": p.get("nome") or "", "codigo": p.get("codigo"), "product_id": ids[0],
                            "variant_id": ids[1], "preco": float(p.get("preco") or 0)})
            if len(achados) >= limite:
                return achados
    for p in _produtos_tray(texto):
        if len(achados) >= limite:
            break
        if (p["product_id"], p["variant_id"]) not in vistos:
            vistos.add((p["product_id"], p["variant_id"]))
            achados.append(p)
    return achados


def _produtos_tray(texto):
    """Busca direto na Tray (pelo id, se for número, ou pelo nome com o curinga %)."""
    ids = ids_tray_do_codigo(texto)
    try:
        if ids:
            produtos = [_tray("GET", f"/products/{ids[0]}").get("Product", {})]
        else:
            produtos = [x.get("Product", x) for x in _tray(
                "GET", "/products", params={"name": f"%{texto}%", "limit": 20}).get("Products", [])]
    except Exception:
        return []
    saida = []
    for p in produtos:
        if not p.get("id"):
            continue
        if str(p.get("has_variation")) == "1":
            variantes = _tray("GET", "/products/variants",
                                         params={"product_id": p["id"], "limit": 50}).get("Variants", [])
            for v in variantes:
                v = v.get("Variant", v)
                sku = "; ".join(f"{s.get('type')}: {s.get('value')}" for s in v.get("Sku") or [])
                saida.append({"nome": f"{p.get('name')} {sku}".strip(), "codigo": v.get("reference") or "",
                              "product_id": int(p["id"]), "variant_id": int(v["id"]),
                              "preco": float(v.get("price") or 0)})
        else:
            saida.append({"nome": p.get("name") or "", "codigo": p.get("reference") or str(p["id"]),
                          "product_id": int(p["id"]), "variant_id": 0, "preco": float(p.get("price") or 0)})
    return saida


def preco_tray(product_id, variant_id=0):
    """Preço de venda na Tray (o da variação, se houver)."""
    if variant_id:
        v = _tray("GET", f"/products/variants/{variant_id}").get("Variant", {})
        return float(v.get("price") or 0)
    p = _tray("GET", f"/products/{product_id}").get("Product", {})
    return float(p.get("price") or 0)


def criar_produto_personalizado(nome, preco, descricao="", largura_cm=0, profundidade_cm=0, altura_cm=0,
                                peso_kg=50, quantidade=1):
    """Cria o produto sob medida na Tray (padrão dos sofás personalizados) e devolve o id.
    O estoque nasce igual à quantidade do pedido: com menos, a Tray recusa o pedido ("out of stock")."""
    corpo = {"name": nome.strip(), "price": _dinheiro(preco), "category_id": (fi.config().get("tray") or {}).get("categoria_personalizados"),
             "brand": MARCA_PERSONALIZADOS, "weight": int(float(peso_kg) * 1000), "stock": max(1, int(quantidade)), "available": 1}
    if descricao.strip():
        corpo["description"] = "".join(f"<p>{linha.strip()}</p>" for linha in descricao.splitlines() if linha.strip())
    for chave, valor in (("width", largura_cm), ("length", profundidade_cm), ("height", altura_cm)):
        if valor:
            corpo[chave] = int(float(valor))
    pid = _tray("POST", "/products", json={"Product": corpo}).get("id")
    if not pid:
        raise RuntimeError("A Tray não devolveu o id do produto criado.")
    _tray("PUT", f"/products/{pid}", json={"Product": {"reference": str(pid)}})
    return int(pid)


# ---------------------------------------------------------------------------
# PARCEIROS
# ---------------------------------------------------------------------------

def parceiros():
    """[(id, nome)] de todos os parceiros da Tray (lidos uma vez por sessão)."""
    global _cache_parceiros
    if _cache_parceiros is None:
        lista, pagina = [], 1
        while True:
            r = _tray("GET", "/partners", params={"limit": 50, "page": pagina})
            for p in r.get("Partners", []):
                p = p.get("Partner", p)
                lista.append((str(p.get("id")), (p.get("name") or "").strip()))
            total = int((r.get("paging") or {}).get("total") or 0)
            if pagina * 50 >= total or not r.get("Partners"):
                break
            pagina += 1
        _cache_parceiros = sorted(lista, key=lambda x: x[1].lower())
    return _cache_parceiros


# ---------------------------------------------------------------------------
# LANÇAMENTO
# ---------------------------------------------------------------------------

def _endereco_para_tray(e, tipo):
    saida = {k: (e.get(k) or "") for k in CAMPOS_ENDERECO}
    saida.update({"country": "BRA", "type": str(tipo)})
    if e.get("recipient"):
        saida["recipient"] = e["recipient"]
    return saida


def montar_corpo(cliente, cobranca, entrega, itens, parceiro_id, frete_nome, frete_valor, pagamento, status):
    """Corpo do POST /orders. itens: [{product_id, variant_id, preco, quantidade}]."""
    tipo = "1" if cliente.get("cnpj") else "0"
    dados = {"type": tipo, "name": cliente.get("name"), "email": cliente.get("email"),
             "CustomerAddress": [_endereco_para_tray(cobranca, 0), _endereco_para_tray(entrega, 1)]}
    if tipo == "1":
        dados.update({"cnpj": cliente.get("cnpj"), "company_name": cliente.get("company_name"),
                      "state_inscription": cliente.get("state_inscription")})
    else:
        dados["cpf"] = cliente.get("cpf")
    for campo in ("cellphone", "phone"):
        if cliente.get(campo):
            dados[campo] = cliente[campo]
    pedido = {"customer_id": int(cliente["id"]), "point_sale": "PARTICULAR", "shipment": frete_nome.strip(),
              "shipment_value": _dinheiro(frete_valor or 0), "payment_form": pagamento.strip(), "Customer": dados,
              "ProductsSold": [{"product_id": int(i["product_id"]), "variant_id": int(i.get("variant_id") or 0),
                                "price": _dinheiro(i["preco"]), "original_price": _dinheiro(i["preco"]),
                                "quantity": int(i["quantidade"])} for i in itens]}
    if parceiro_id:
        pedido["partner_id"] = int(parceiro_id)
    if status:
        pedido["status"] = status
    return {"Order": pedido}


def conferir_pedido(numero, entrega):
    """Relê o pedido: (total, entrega_ok, texto_do_endereço_de_entrega_que_ficou)."""
    o = _tray("GET", f"/orders/{numero}/complete").get("Order", {})
    ends = [(e.get("CustomerAddress") or e) for e in (o.get("Customer") or {}).get("CustomerAddresses") or []]
    de_entrega = [e for e in ends if str(e.get("type")) == "1"]
    cep = _so_numeros(entrega.get("zip_code"))
    ok = any(_so_numeros(e.get("zip_code")) == cep and str(e.get("number") or "").strip()
             == str(entrega.get("number") or "").strip() for e in de_entrega)
    ficou = texto_endereco(de_entrega[0]) if de_entrega else ""
    return float(o.get("total") or 0), ok, ficou


def lancar(cliente_id, cobranca, entrega, itens, parceiro_id, frete_nome, frete_valor, pagamento, status):
    """Lança o pedido e confere. Devolve {numero, total, avisos: [...]}."""
    if not itens:
        raise ValueError("Inclua pelo menos um produto.")
    cliente = dados_cliente(cliente_id)
    if not cliente.get("id"):
        raise RuntimeError(f"Cliente {cliente_id} não encontrado na Tray.")
    principal = endereco_principal(cliente)
    corpo = montar_corpo(cliente, cobranca, entrega, itens, parceiro_id, frete_nome, frete_valor, pagamento, status)
    r = _tray("POST", "/orders", json=corpo)
    numero = r.get("order_id") or r.get("id")
    if not numero:
        raise RuntimeError(f"A Tray não devolveu o número do pedido: {r}")
    avisos = []
    if str(r.get("customer_id") or cliente_id) != str(cliente_id):
        avisos.append(f"A Tray ligou o pedido a outro cliente ({r.get('customer_id')}): confira o cadastro.")

    # a Tray pode trocar o endereço principal do cadastro pelo do pedido: devolve o original
    try:
        depois = endereco_principal(dados_cliente(cliente_id))
        if any(_so_numeros(depois[k]) != _so_numeros(principal[k]) if k in ("zip_code", "number")
               else depois[k] != principal[k] for k in CAMPOS_ENDERECO) and principal.get("address"):
            _tray("PUT", f"/customers/{cliente_id}", json={"Customer": principal})
            avisos.append("A Tray tinha trocado o endereço do cadastro do cliente; o original foi devolvido.")
    except Exception as erro:
        avisos.append(f"Não consegui conferir o endereço do cadastro do cliente ({erro}).")

    total, entrega_ok = None, False
    try:
        total, entrega_ok, ficou = conferir_pedido(numero, entrega)
        if not entrega_ok:
            avisos.append("O endereço de entrega NÃO entrou no pedido"
                          + (f" (ficou: {ficou})" if ficou else "")
                          + ". Corrija em 'Editar endereço' no painel da Tray (a API não deixa editar o pedido).")
    except Exception as erro:
        avisos.append(f"Pedido lançado, mas não consegui relê-lo para conferir ({erro}).")
    return {"numero": str(numero), "total": total, "entrega_ok": entrega_ok, "avisos": avisos}


def link_painel():
    """Painel da Tray (o pedido se abre pela busca 'Pedidos, Clientes e Recursos' no topo)."""
    api = (fi.config().get("tray") or {}).get("api_address") or ""
    return api.replace("/web_api", "/admin") if api else "https://www.tray.com.br"
