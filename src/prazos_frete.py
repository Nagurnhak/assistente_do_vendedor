"""
Prazos de frete das transportadoras (dias úteis da coleta até o cliente).

As tabelas que as transportadoras mandam (Excel) são convertidas para um arquivo único e leve,
prazos_frete.json (na pasta do programa), que o Assistente consulta na hora de cada pedido.
Quando chegar tabela nova: coloque o Excel na pasta das tabelas e rode
    py prazos_frete.py            (ou informe outra pasta: py prazos_frete.py "C:\\...\\pasta")

Cada transportadora é descrita no config.json (seção "prazos_frete"), porque cada uma manda a
planilha num formato. Exemplo:
    "prazos_frete": {
      "pasta": "C:\\...\\Prazos de Transportadoras",
      "regiao_local": {"nome": "Grande São Paulo", "uf": "SP", "cep_inicio": "01000000",
                       "cep_fim": "09999999", "dias": 1},
      "transportadoras": [
        {"chave": "rapida", "nome": "Transportadora Rápida", "arquivo": "rapida", "tipo": "cidade",
         "colunas": {"uf": 4, "cidade": 5, "pj": 9, "pf": 10}, "primeira_linha": 2},
        {"chave": "expressa", "nome": "Expressa Cargas", "arquivo": "expressa", "tipo": "cep",
         "aba": "Faixa de CEP", "colunas": {"cep_inicio": 6, "cep_fim": 7, "dias": 10},
         "filtro": {"coluna": 0, "valor": "SP-CAP"}}
      ]
    }
(colunas contadas a partir de 0: A = 0, B = 1...)

Regras:
- região local (opcional; ex.: a região metropolitana de onde sai a mercadoria): prazo fixo, qualquer transportadora;
- tabelas "cidade": prazo por cidade/UF, de pessoa jurídica (pj) ou física (pf);
- tabelas "cep": prazo por faixa de CEP;
- cidade/faixa com mais de um prazo na tabela: vale o MAIOR (mais seguro);
- transportadora ou destino fora das tabelas: None (o Assistente usa a regra anterior).
Lê o Excel só com a biblioteca padrão (o .xlsx é um pacote de XMLs).
"""

import json
import os
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

ARQUIVO = "prazos_frete.json"
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_CACHE = None


def _cfg():
    try:
        import ferramentas_internas as fi
        return fi.config().get("prazos_frete") or {}
    except Exception:
        return {}


def transportadoras_configuradas():
    return [t for t in (_cfg().get("transportadoras") or []) if t.get("chave")]


def nomes():
    """{'chave': 'Nome da transportadora'} das transportadoras com tabela."""
    return {t["chave"]: t.get("nome") or t["chave"] for t in transportadoras_configuradas()}


def pasta_tabelas():
    return _cfg().get("pasta") or os.path.join(_pasta_programa(), "tabelas_frete")


# ---------------------------------------------------------------------------
# leitura do Excel (sem bibliotecas externas)
# ---------------------------------------------------------------------------

def _coluna(ref):
    n = 0
    for c in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(c) - 64
    return n - 1


def _abas(caminho):
    z = zipfile.ZipFile(caminho)
    textos = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            textos.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    alvo = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    abas = {}
    for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", _NS):
        caminho_aba = alvo[s.get(f"{{{_NS['r']}}}id")].lstrip("/")
        abas[s.get("name").strip()] = caminho_aba if caminho_aba.startswith("xl/") else "xl/" + caminho_aba
    return z, textos, abas


def _linhas(z, textos, caminho_aba):
    for row in ET.fromstring(z.read(caminho_aba)).iter(f"{{{_NS['m']}}}row"):
        valores = {}
        for c in row.findall("m:c", _NS):
            v = c.find("m:v", _NS)
            texto = v.text if v is not None else "".join(t.text or "" for t in c.iter(f"{{{_NS['m']}}}t"))
            if c.get("t") == "s" and texto is not None:
                texto = textos[int(texto)]
            valores[_coluna(c.get("r"))] = (texto or "").strip()
        if valores:
            yield [valores.get(i, "") for i in range(max(valores) + 1)]


# ---------------------------------------------------------------------------
# normalização
# ---------------------------------------------------------------------------

def _sem_acento(texto):
    base = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _simples(texto):
    """'Transportes Rápida_Ltda' -> 'transportes rapida ltda' (para comparar nomes e arquivos)."""
    return re.sub(r"[^a-z0-9]+", " ", _sem_acento(texto).lower()).strip()


def chave_cidade(uf, cidade):
    """'SP', "Santa Bárbara d'Oeste" -> 'SP|SANTA BARBARA D OESTE'."""
    nome = re.sub(r"[^A-Z0-9]+", " ", _sem_acento(cidade).upper()).strip()
    return f"{str(uf or '').strip().upper()}|{nome}"


def _cep(texto):
    numeros = re.sub(r"\D", "", str(texto or ""))
    return int(numeros) if numeros else None


def _inteiro(texto):
    try:
        return int(float(str(texto).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def identificar_transportadora(nome):
    """'TRANSPORTADORA RÁPIDA LTDA' -> 'rapida' (pela chave ou pelo nome configurado); None se não tiver tabela."""
    texto = f" {_simples(nome)} "
    for t in transportadoras_configuradas():
        for termo in (t["chave"], t.get("nome")):
            if termo and f" {_simples(termo)} " in texto:
                return t["chave"]
    return None


# ---------------------------------------------------------------------------
# conversão das planilhas -> prazos_frete.json
# ---------------------------------------------------------------------------

def _maior(destino, chave, valor):
    if valor is not None:
        destino[chave] = max(destino.get(chave, valor), valor)


def _aba(abas, nome):
    return abas[nome] if nome else next(iter(abas.values()))


def _por_cidade(caminho, t):
    z, textos, abas = _abas(caminho)
    col = t["colunas"]
    pj, pf = {}, {}
    for n, l in enumerate(_linhas(z, textos, _aba(abas, t.get("aba")))):
        if n < t.get("primeira_linha", 1) or len(l) <= max(col["pj"], col["pf"]) or not l[col["cidade"]]:
            continue
        chave = chave_cidade(l[col["uf"]], l[col["cidade"]])
        _maior(pj, chave, _inteiro(l[col["pj"]]))
        _maior(pf, chave, _inteiro(l[col["pf"]]))
    return {"tipo": "cidade", "pj": pj, "pf": pf}


def _por_cep(caminho, t):
    z, textos, abas = _abas(caminho)
    col, filtro = t["colunas"], t.get("filtro")
    faixas = {}
    for l in _linhas(z, textos, _aba(abas, t.get("aba"))):
        if len(l) <= max(col["cep_inicio"], col["cep_fim"], col["dias"]):
            continue
        if filtro and l[filtro["coluna"]].strip().upper() != str(filtro["valor"]).upper():
            continue
        ini, fim, dias = _cep(l[col["cep_inicio"]]), _cep(l[col["cep_fim"]]), _inteiro(l[col["dias"]])
        if ini and fim and dias is not None and ini <= fim:
            _maior(faixas, (ini, fim), dias)
    return {"tipo": "cep", "faixas": sorted([ini, fim, dias] for (ini, fim), dias in faixas.items())}


def converter(pasta=None, destino=None):
    """Lê as planilhas da pasta (uma por transportadora configurada) e grava prazos_frete.json."""
    pasta = pasta or pasta_tabelas()
    arquivos = [a for a in sorted(os.listdir(pasta)) if a.lower().endswith(".xlsx") and not a.startswith("~$")]
    tabelas, fontes = {}, {}
    for t in transportadoras_configuradas():
        trecho = _simples(t.get("arquivo") or t["chave"])
        arquivo = next((a for a in arquivos if trecho in _simples(a)), None)
        if not arquivo:
            continue
        caminho = os.path.join(pasta, arquivo)
        tabelas[t["chave"]] = _por_cidade(caminho, t) if t.get("tipo") == "cidade" else _por_cep(caminho, t)
        fontes[t["chave"]] = arquivo
    dados = {"gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M"), "fontes": fontes, "transportadoras": tabelas}
    destino = destino or os.path.join(_pasta_programa(), ARQUIVO)
    with open(destino + ".tmp", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(destino + ".tmp", destino)
    global _CACHE
    _CACHE = None
    return {chave: (len(t["pj"]) if t["tipo"] == "cidade" else len(t["faixas"])) for chave, t in tabelas.items()}


# ---------------------------------------------------------------------------
# consulta
# ---------------------------------------------------------------------------

def _pasta_programa():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def carregar():
    global _CACHE
    try:
        import ferramentas_internas as fi
        if fi.MODO_DEMO:
            import demo
            return demo.PRAZOS_FRETE
    except ImportError:
        pass
    if _CACHE is None:
        try:
            with open(os.path.join(_pasta_programa(), ARQUIVO), encoding="utf-8") as f:
                _CACHE = json.load(f)
        except (OSError, ValueError):
            _CACHE = {"transportadoras": {}}
    return _CACHE


def dias_texto(dias):
    return f"{dias} dia útil" if dias == 1 else f"{dias} dias úteis"


def regiao_local(cep, uf):
    """A região de prazo fixo (config: prazos_frete.regiao_local) se o destino estiver nela, senão None."""
    r = _cfg().get("regiao_local")
    numero = _cep(cep)
    if not r or numero is None:
        return None
    dentro = (str(uf or "").strip().upper() == str(r.get("uf", "")).upper()
              and _cep(r["cep_inicio"]) <= numero <= _cep(r["cep_fim"]))
    return r if dentro else None


def prazo(transportadora, cep=None, cidade=None, uf=None, pessoa_juridica=False):
    """Dias úteis de frete até o destino: {'dias', 'transportadora', 'detalhe'} ou {'dias': None, 'motivo'}."""
    local = regiao_local(cep, uf)
    if local:
        dias = int(local.get("dias", 1))
        return {"dias": dias, "transportadora": transportadora or "-",
                "detalhe": f"{local.get('nome') or 'Região local'}: {dias_texto(dias)} de entrega"}
    chave = identificar_transportadora(transportadora)
    tabela = (carregar().get("transportadoras") or {}).get(chave) if chave else None
    if not tabela:
        return {"dias": None, "motivo": f"sem tabela de prazos para a transportadora '{transportadora or '-'}'"}
    nome = nomes().get(chave, chave)
    if tabela["tipo"] == "cidade":
        coluna = "pj" if pessoa_juridica else "pf"
        dias = tabela[coluna].get(chave_cidade(uf, cidade))
        if dias is None:
            return {"dias": None, "motivo": f"{cidade}/{uf} não está na tabela da {nome}"}
        return {"dias": dias, "transportadora": nome,
                "detalhe": f"{nome}: {dias_texto(dias)} até {cidade}/{uf} ({'PJ' if pessoa_juridica else 'PF'})"}
    numero = _cep(cep)
    for ini, fim, dias in tabela["faixas"]:
        if numero is not None and ini <= numero <= fim:
            return {"dias": dias, "transportadora": nome, "detalhe": f"{nome}: {dias_texto(dias)} até o CEP {cep}"}
    return {"dias": None, "motivo": f"o CEP {cep or '-'} não está na tabela da {nome}"}


if __name__ == "__main__":
    pasta = sys.argv[1] if len(sys.argv) > 1 else None
    print("Tabelas convertidas:", converter(pasta))
