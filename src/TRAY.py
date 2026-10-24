"""
Autenticação com a API da Tray + funções usadas pelo ferramentas_internas.py.

- consumer_key, consumer_secret, code e api_address ficam no config.json (seção "tray").
  O code aparece na loja em "Meus aplicativos" -> acessar (ou na URL de retorno da autorização).
- Os tokens ficam em tray_tokens.json, na mesma pasta do script/.exe.
- O access_token (~3 h) é renovado sozinho com o refresh_token (~30 dias). Se o refresh
  também vencer, gera de novo com o code; se o code não for aceito, pede um novo.
- Respeita os limites da Tray (180 requisições por minuto e 10.000 por dia): intervalo mínimo,
  janela de 60 s, contador diário e nova tentativa no erro 429 (respeitando o Retry-After).

Enquanto a seção "tray" não estiver preenchida, tray_configurada() devolve False e o
ferramentas_internas.py simplesmente pula a parte da Tray.

Teste rápido:  py TRAY.py 12345   (mostra o pedido 12345 da Tray, só leitura)
"""

import json
import os
import sys
import time
import unicodedata
from collections import deque
from datetime import datetime

import requests

from configuracao import carregar_config, pasta_base

ARQUIVO_TOKENS = os.path.join(pasta_base(), "tray_tokens.json")
INTERVALO_MINIMO = 0.35  # segundos entre chamadas (180 por minuto = 1 a cada 0,33 s)
TENTATIVAS_429 = 4
VALIDADE_PADRAO = 3 * 3600  # se a Tray não informar a data de expiração do access_token

_ultima_chamada = 0.0
_cache_status = None


# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------

def _cfg():
    return carregar_config().get("tray") or {}


def _preenchido(valor):
    return bool(valor) and not str(valor).upper().startswith(("SUA_", "SEU_", "URL_"))


def tray_configurada():
    """True se o config.json tem as chaves da Tray preenchidas."""
    try:
        c = _cfg()
    except Exception:
        return False
    return all(_preenchido(c.get(k)) for k in ("consumer_key", "consumer_secret", "api_address"))


def _api():
    endereco = _cfg()["api_address"].strip().rstrip("/")
    return endereco if endereco.startswith("http") else f"https://{endereco}"


def campo_observacao():
    """Campo do pedido onde as observações são gravadas (padrão: store_note)."""
    return _cfg().get("campo_observacao") or "store_note"


# ---------------------------------------------------------------------------
# TOKENS
# ---------------------------------------------------------------------------

def _sem_segredos(texto):
    """Tira chaves e tokens de mensagens de erro."""
    texto = str(texto)
    try:
        c = _cfg()
        tokens = _carregar_tokens() or {}
    except Exception:
        return texto
    for segredo in (c.get("consumer_secret"), c.get("code"),
                    tokens.get("access_token"), tokens.get("refresh_token")):
        if segredo:
            texto = texto.replace(str(segredo), "***")
    return texto


def _requisicao(metodo, url, **kwargs):
    """requests.request sem deixar a URL (que leva o access_token) aparecer em erros."""
    try:
        return requests.request(metodo, url, timeout=30, **kwargs)
    except requests.RequestException as erro:
        raise RuntimeError(f"Falha de conexão com a Tray ({type(erro).__name__}): {_sem_segredos(erro)}") from None


def _expiracao(texto_data):
    """'2026-10-15 18:30:00' -> timestamp (com 1 min de folga)."""
    try:
        return datetime.strptime(texto_data, "%Y-%m-%d %H:%M:%S").timestamp() - 60
    except (TypeError, ValueError):
        return time.time() + VALIDADE_PADRAO - 60


def _salvar_tokens(resposta):
    dados = {
        "access_token": resposta["access_token"],
        "refresh_token": resposta["refresh_token"],
        "expira_em": _expiracao(resposta.get("date_expiration_access_token")),
        "refresh_expira_em": resposta.get("date_expiration_refresh_token"),
        "api_address": _api(),  # de qual loja é este token
    }
    # Grava num temporário e troca de uma vez (o refresh_token não se perde se o programa fechar).
    temporario = ARQUIVO_TOKENS + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    os.replace(temporario, ARQUIVO_TOKENS)
    return dados


def _carregar_tokens():
    if not os.path.isfile(ARQUIVO_TOKENS):
        return None
    with open(ARQUIVO_TOKENS, "r", encoding="utf-8") as f:
        tokens = json.load(f)
    # Token de outra loja (ex.: trocou da loja de teste para a real no config.json): gera um novo.
    if tokens.get("api_address") and tokens["api_address"] != _api():
        return None
    return tokens


def _checar_auth(resposta, acao):
    if resposta.status_code in (200, 201):
        dados = resposta.json()
        if dados.get("access_token"):
            return dados
    raise RuntimeError(f"A Tray recusou ao {acao}: erro {resposta.status_code} - "
                       f"{_sem_segredos(resposta.text[:300])}")


def _gerar_com_code(code):
    c = _cfg()
    resposta = _requisicao("POST", f"{_api()}/auth", data={
        "consumer_key": c["consumer_key"],
        "consumer_secret": c["consumer_secret"],
        "code": code,
    })
    return _salvar_tokens(_checar_auth(resposta, "gerar o token com o code"))


def _autenticar_do_zero():
    """Gera os tokens com o code do config.json; se não for aceito, pede um novo."""
    code = (_cfg().get("code") or "").strip()
    if _preenchido(code):
        try:
            return _gerar_com_code(code)
        except RuntimeError as erro:
            print(f"\n{erro}")
    print("\n=== Autorização da Tray ===")
    print("Na loja: Meus aplicativos -> nosso aplicativo -> acessar. Copie o 'code' que aparece ali")
    print("(ou cole a URL de retorno da autorização inteira).")
    texto = input("Cole aqui o code (Enter cancela): ").strip()
    if "code=" in texto:
        texto = texto.split("code=")[1].split("&")[0]
    if not texto:
        raise RuntimeError("Autorização da Tray não concluída.")
    tokens = _gerar_com_code(texto)
    print("Tokens da Tray obtidos. Dica: atualize o 'code' no config.json com esse valor.")
    return tokens


def _renovar(tokens):
    try:
        resposta = _requisicao("GET", f"{_api()}/auth", params={"refresh_token": tokens["refresh_token"]})
        return _salvar_tokens(_checar_auth(resposta, "renovar o token"))
    except RuntimeError:
        print("Não consegui renovar o token da Tray (o refresh_token pode ter vencido).")
        return _autenticar_do_zero()


def pegar_access_token(forcar_renovacao=False):
    tokens = _carregar_tokens()
    if tokens is None:
        tokens = _autenticar_do_zero()
    elif forcar_renovacao or time.time() >= tokens["expira_em"]:
        tokens = _renovar(tokens)
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# CHAMADAS
# ---------------------------------------------------------------------------

# Rate limit da Tray: 180 requisições/minuto e 10.000/dia por loja. O app fica abaixo dos dois com folga:
#   - intervalo mínimo de 0,35 s entre chamadas;
#   - janela deslizante de 60 s com no máximo LIMITE_POR_MINUTO chamadas (se encher, espera abrir vaga);
#   - contador diário em tray_uso.json; ao chegar em LIMITE_DIARIO, para de chamar até o dia seguinte;
#   - HTTP 429: respeita o Retry-After (se vier) ou espera 2, 4, 8, 16 s antes de tentar de novo.
LIMITE_POR_MINUTO = 170
LIMITE_DIARIO = 9500
ARQUIVO_USO = os.path.join(pasta_base(), "tray_uso.json")
_janela = deque()


def _uso_de_hoje():
    hoje = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(ARQUIVO_USO, "r", encoding="utf-8") as f:
            uso = json.load(f)
    except (FileNotFoundError, ValueError):
        uso = {}
    return uso if uso.get("dia") == hoje else {"dia": hoje, "chamadas": 0}


def _contar_chamada():
    uso = _uso_de_hoje()
    if uso["chamadas"] >= LIMITE_DIARIO:
        raise RuntimeError(f"Limite diário de {LIMITE_DIARIO} chamadas à Tray atingido; o app volta amanhã.")
    uso["chamadas"] += 1
    with open(ARQUIVO_USO + ".tmp", "w", encoding="utf-8") as f:
        json.dump(uso, f)
    os.replace(ARQUIVO_USO + ".tmp", ARQUIVO_USO)


def _esperar_vez():
    """Segura a chamada até caber no limite por minuto e no intervalo mínimo."""
    global _ultima_chamada
    agora = time.time()
    while _janela and agora - _janela[0] >= 60:
        _janela.popleft()
    if len(_janela) >= LIMITE_POR_MINUTO:
        time.sleep(60 - (agora - _janela[0]) + 0.05)
        return _esperar_vez()
    espera = INTERVALO_MINIMO - (agora - _ultima_chamada)
    if espera > 0:
        time.sleep(espera)
    _ultima_chamada = time.time()
    _janela.append(_ultima_chamada)
    _contar_chamada()


def _espera_429(resposta, tentativa):
    try:
        return min(float(resposta.headers.get("Retry-After")), 60.0)
    except (TypeError, ValueError):
        return 2.0 * (2 ** tentativa)  # 2, 4, 8, 16 s


def chamar_tray(metodo, caminho, params=None, **kwargs):
    """Chamada autenticada à API da Tray, ex.: chamar_tray('GET', '/orders/12345')."""
    renovou = False
    resposta = None
    for tentativa in range(TENTATIVAS_429 + 1):
        _esperar_vez()
        resposta = _requisicao(metodo, f"{_api()}{caminho}",
                               params={**(params or {}), "access_token": pegar_access_token()}, **kwargs)
        if resposta.status_code == 401 and not renovou:
            renovou = True
            pegar_access_token(forcar_renovacao=True)
            continue
        if resposta.status_code == 429 and tentativa < TENTATIVAS_429:
            time.sleep(_espera_429(resposta, tentativa))
            continue
        break

    if not resposta.ok:
        raise RuntimeError(f"Erro {resposta.status_code} da Tray em {metodo} {caminho}: "
                           f"{_sem_segredos(resposta.text[:300])}")
    return resposta.json() if resposta.text else {}


# ---------------------------------------------------------------------------
# PEDIDOS
# ---------------------------------------------------------------------------

def _sem_acento(texto):
    base = unicodedata.normalize("NFD", str(texto))
    return " ".join("".join(c for c in base if unicodedata.category(c) != "Mn").lower().split())


def obter_pedido(numero):
    return chamar_tray("GET", f"/orders/{numero}").get("Order", {}) or {}


def entrega_prevista(numero):
    """Data de entrega que a própria Tray calculou para o pedido ('aaaa-mm-dd'), ou None (só leitura)."""
    data = str(obter_pedido(numero).get("estimated_delivery_date") or "").strip()
    return data if data and not data.startswith("0000") else None


def pedidos_por_status(nomes_status):
    """Pedidos da loja nos status informados (só leitura): [{'numero', 'data', 'status', 'total', 'entrega'}].
    Os nomes são comparados sem acento/maiúscula com os status que existem na loja; os que não existem são pulados."""
    na_loja = {_sem_acento(s.get("status", "")): s.get("status") for s in listar_status()}
    pedidos = []
    for nome in nomes_status:
        exato = na_loja.get(_sem_acento(nome))
        if not exato:
            continue
        pagina = 1
        while True:
            dados = chamar_tray("GET", "/orders", params={"status": exato, "limit": 50, "page": pagina})
            for item in dados.get("Orders") or []:
                pedido = item.get("Order") or item
                pedidos.append({"numero": str(pedido.get("id")), "data": pedido.get("date"), "status": pedido.get("status"),
                                "total": pedido.get("total"), "entrega": pedido.get("estimated_delivery_date")})
            paginacao = dados.get("paging") or {}
            if pagina * int(paginacao.get("limit") or 50) >= int(paginacao.get("total") or 0):
                break
            pagina += 1
    return pedidos


def pedido_completo(numero):
    """Pedido com cliente, endereços, itens vendidos e imagens (só leitura), para a ficha do pedido."""
    return chamar_tray("GET", f"/orders/{numero}/complete").get("Order", {}) or {}


def detalhes_pedido(numero):
    """Itens vendidos e observação do pedido, numa leitura só (para os cards da tela de Compras)."""
    pedido = chamar_tray("GET", f"/orders/{numero}/complete").get("Order", {}) or {}
    return {"itens": _itens_de(pedido), "observacao": pedido.get(campo_observacao()) or ""}


def itens_vendidos(numero):
    """Itens do pedido como o cliente comprou: [{'nome', 'quantidade', 'referencia'}] (só leitura).
    O nome vem como está na loja, às vezes com HTML da variação (ex.: '<br><strong>Cor</strong> Azul')."""
    return _itens_de(chamar_tray("GET", f"/orders/{numero}/complete").get("Order", {}) or {})


def _itens_de(pedido):
    itens = []
    for vendido in pedido.get("ProductsSold") or []:
        vendido = vendido.get("ProductsSold") or vendido
        itens.append({"nome": vendido.get("name") or "", "quantidade": vendido.get("quantity"),
                      "referencia": str(vendido.get("reference") or "").strip()})
    return itens


def adicionar_observacao(numero, texto):
    """Acrescenta o texto nas observações do pedido, mantendo o que já existe
    (ex.: dados de pagamento). Não grava de novo se o texto já estiver lá.
    Devolve True se gravou, False se já existia."""
    campo = campo_observacao()
    atual = (obter_pedido(numero).get(campo) or "").strip()
    if texto.strip() in atual:
        return False
    novo = f"{atual}\n{texto.strip()}" if atual else texto.strip()
    chamar_tray("PUT", f"/orders/{numero}", json={"Order": {campo: novo}})
    return True


def atualizar_observacao_gerenciada(numero, partes):
    """Atualiza apenas o bloco gerenciado pelo Assistente e preserva qualquer observação externa.

    A segunda leitura evita sobrescrever uma edição feita por outra pessoa entre o GET e o PUT.
    Depois do PUT, a releitura precisa confirmar exatamente o HTML salvo.
    """
    from notas_compras import atualizar_html

    campo = campo_observacao()
    atual = obter_pedido(numero).get(campo) or ""
    novo = atualizar_html(atual, partes)
    if novo == atual:
        return False
    if (obter_pedido(numero).get(campo) or "") != atual:
        raise RuntimeError("Observação mudou; releia antes de atualizar.")
    chamar_tray("PUT", f"/orders/{numero}", json={"Order": {campo: novo}})
    if (obter_pedido(numero).get(campo) or "") != novo:
        raise RuntimeError("Releitura da observação divergente; reconciliar sem recriar OC.")
    return True


def listar_status():
    """[{'id': '1', 'status': 'ENVIADO'}, ...] (todas as páginas, guardado em cache)."""
    global _cache_status
    if _cache_status is None:
        todos, pagina = [], 1
        while True:
            dados = chamar_tray("GET", "/orders/statuses", params={"limit": 50, "page": pagina})
            todos += [s.get("OrderStatus", {}) for s in dados.get("OrderStatuses", [])]
            paginacao = dados.get("paging") or {}
            if pagina * int(paginacao.get("limit") or 50) >= int(paginacao.get("total") or 0):
                break
            pagina += 1
        _cache_status = todos
    return _cache_status


def id_status(nome):
    """Id do status da Tray pelo nome (sem diferenciar acento/maiúscula). None se não achar."""
    alvo = _sem_acento(nome)
    for s in listar_status():
        if _sem_acento(s.get("status", "")) == alvo:
            return s.get("id")
    return None


def mudar_status(numero, nome_status):
    id_ = id_status(nome_status)
    if id_ is None:
        existentes = ", ".join(s.get("status", "") for s in listar_status())
        raise RuntimeError(f"Não achei o status '{nome_status}' na Tray. Os que existem: {existentes}")
    chamar_tray("PUT", f"/orders/{numero}", json={"Order": {"status_id": id_}})


if __name__ == "__main__":
    try:
        if not tray_configurada():
            print("Preencha a seção 'tray' do config.json (veja o config.exemplo.json).")
        elif len(sys.argv) > 1:
            p = obter_pedido(sys.argv[1])
            print(f"Pedido {p.get('id')} | status: {p.get('status')} | "
                  f"{campo_observacao()}: {p.get(campo_observacao())!r}")
        else:
            print("Autenticação OK. Status de pedido existentes na loja:")
            for s in listar_status():
                print(f"  id {s.get('id')} | {s.get('status')}")
    except Exception as erro:
        print("\n=== ERRO ===")
        print(erro)
