"""
Autenticação com a API v3 do Bling (OAuth2) + chamada autenticada.

- client_id e client_secret ficam no config.json (seção "bling").
- Os tokens ficam em bling_tokens.json, na mesma pasta do script/.exe.
- O access_token é renovado sozinho. Se o refresh_token também tiver vencido,
  o script pede um novo "code" em vez de travar.
- Respeita o limite de requisições do Bling e tenta de novo em caso de erro 429.

Teste rápido:  python BLING.py
"""

import base64
import json
import os
import secrets
import shutil
import time
import webbrowser
from urllib.parse import parse_qs, urlparse

import requests

from configuracao import carregar_config, pasta_base

BLING_API_URL = "https://api.bling.com.br/Api/v3"
# Endereços possíveis do endpoint de token (tenta um, depois o outro).
BLING_TOKEN_URLS = [
    "https://www.bling.com.br/Api/v3/oauth/token",
    f"{BLING_API_URL}/oauth/token",
]
BLING_AUTORIZAR_URL = "https://www.bling.com.br/Api/v3/oauth/authorize"
ARQUIVO_TOKENS = os.path.join(pasta_base(), "bling_tokens.json")
TENTATIVAS_CODE = 3

INTERVALO_MINIMO = 0.35  # segundos entre chamadas (o Bling aceita ~3 por segundo)
TENTATIVAS_429 = 4

_ultima_chamada = 0.0


# ---------------------------------------------------------------------------
# TOKENS
# ---------------------------------------------------------------------------

def _credenciais():
    bling = carregar_config().get("bling", {})
    client_id, secret = bling.get("client_id"), bling.get("client_secret")
    if not client_id or not secret:
        raise RuntimeError("Preencha bling.client_id e bling.client_secret no config.json.")
    return client_id, secret


def _cabecalho_basic():
    client_id, secret = _credenciais()
    return base64.b64encode(f"{client_id}:{secret}".encode("utf-8")).decode("utf-8")


def _pedir_tokens(dados):
    """POST no endpoint de token. Devolve o JSON ou levanta RuntimeError."""
    ultima = None
    for url in BLING_TOKEN_URLS:
        resposta = requests.post(
            url,
            headers={
                "Authorization": f"Basic {_cabecalho_basic()}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "1.0",
                "enable-jwt": "1",
            },
            data=dados,
            timeout=30,
        )
        if resposta.status_code == 200:
            return resposta.json()
        ultima = resposta
        print(f"\n[!] {url} respondeu com erro {resposta.status_code}")
        print("    Resposta do Bling:", resposta.text[:300])
    raise RuntimeError(f"Não foi possível obter o token (último erro {ultima.status_code}).")


def _salvar_tokens(resposta_token):
    dados = {
        "access_token": resposta_token["access_token"],
        "refresh_token": resposta_token["refresh_token"],
        "expira_em": time.time() + int(resposta_token.get("expires_in", 21600)) - 60,
    }
    # Grava num temporário e troca de uma vez: se o programa fechar no meio,
    # o arquivo antigo continua inteiro (o refresh_token não se perde).
    temporario = ARQUIVO_TOKENS + ".tmp"
    with open(temporario, "w", encoding="utf-8") as f:
        json.dump(dados, f)
    os.replace(temporario, ARQUIVO_TOKENS)
    return dados


def _carregar_tokens():
    """Lê o bling_tokens.json da pasta do script. Se não existir ali, procura na pasta
    de onde o programa foi aberto e copia para cá."""
    if not os.path.isfile(ARQUIVO_TOKENS):
        candidatos = [os.path.join(os.getcwd(), "bling_tokens.json")]
        achado = next((c for c in candidatos
                       if os.path.isfile(c) and os.path.abspath(c) != os.path.abspath(ARQUIVO_TOKENS)), None)
        if achado is None:
            print(f"\nNão encontrei o bling_tokens.json em: {pasta_base()}")
            return None
        shutil.copy2(achado, ARQUIVO_TOKENS)
        print(f"Tokens encontrados em {achado} e copiados para {ARQUIVO_TOKENS}.")
    with open(ARQUIVO_TOKENS, "r", encoding="utf-8") as f:
        return json.load(f)


def _link_autorizacao():
    client_id, _ = _credenciais()
    return f"{BLING_AUTORIZAR_URL}?response_type=code&client_id={client_id}&state={secrets.token_hex(8)}"


def _extrair_code(texto):
    texto = texto.strip()
    if "code=" in texto:
        return parse_qs(urlparse(texto).query).get("code", [texto.split("code=")[1].split("&")[0]])[0]
    return texto


def _autenticar_do_zero():
    """Abre o link de autorização do Bling e troca o code pelos tokens (até 3 tentativas)."""
    print("\n=== Autorização do Bling ===")
    print("1. Vou abrir o link de autorização no navegador (se não abrir, copie o link abaixo).")
    print("2. Clique em 'Autorizar'. Você será levado para a URL de retorno.")
    print("3. Copie a URL INTEIRA da barra de endereço e cole aqui RÁPIDO (o code vence em ~1 minuto).")
    for tentativa in range(1, TENTATIVAS_CODE + 1):
        link = _link_autorizacao()
        print(f"\nLink: {link}")
        try:
            webbrowser.open(link)
        except Exception:
            pass
        code = _extrair_code(input("Cole aqui a URL de retorno (ou só o code). Enter cancela: "))
        if not code:
            break
        try:
            tokens = _salvar_tokens(_pedir_tokens({"grant_type": "authorization_code", "code": code}))
            print("Tokens obtidos e salvos em", ARQUIVO_TOKENS)
            return tokens
        except RuntimeError:
            if tentativa < TENTATIVAS_CODE:
                print("Esse code não foi aceito (provavelmente venceu). Vamos gerar um novo.")
    raise RuntimeError("Autorização do Bling não concluída.")


def _renovar(tokens):
    try:
        return _salvar_tokens(
            _pedir_tokens({"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
        )
    except RuntimeError:
        print("Não consegui renovar o token (o refresh_token pode ter vencido).")
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

def _esperar_vez():
    global _ultima_chamada
    espera = INTERVALO_MINIMO - (time.time() - _ultima_chamada)
    if espera > 0:
        time.sleep(espera)
    _ultima_chamada = time.time()


def chamar_bling(metodo, caminho, **kwargs):
    """Chamada autenticada à API do Bling, ex.: chamar_bling('GET', '/pedidos/vendas')."""
    renovou = False
    resposta = None
    for tentativa in range(TENTATIVAS_429 + 1):
        _esperar_vez()
        resposta = requests.request(
            metodo,
            f"{BLING_API_URL}{caminho}",
            headers={
                "Authorization": f"Bearer {pegar_access_token()}",
                "Accept": "application/json",
            },
            timeout=30,
            **kwargs,
        )
        if resposta.status_code == 401 and not renovou:
            renovou = True
            pegar_access_token(forcar_renovacao=True)
            continue
        if resposta.status_code == 429 and tentativa < TENTATIVAS_429:
            time.sleep(1.5 * (tentativa + 1))
            continue
        break

    if not resposta.ok:
        print(f"Erro {resposta.status_code} em {metodo} {caminho}:")
        print(resposta.text[:500])
        resposta.raise_for_status()
    return resposta.json() if resposta.text else {}


def teste_listar_pedidos():
    pedidos = chamar_bling("GET", "/pedidos/vendas", params={"limite": 5}).get("data", [])
    if not pedidos:
        print("Autenticou, mas nenhum pedido foi retornado.")
        return
    print("\nAutenticação OK! Últimos pedidos de venda:\n")
    for p in pedidos:
        print(f"  ID {p.get('id')} | Nº {p.get('numero')} | {p.get('data')} | "
              f"situação id: {(p.get('situacao') or {}).get('id')}")


if __name__ == "__main__":
    try:
        teste_listar_pedidos()
    except Exception as erro:
        print("\n=== ERRO ===")
        print(erro)
