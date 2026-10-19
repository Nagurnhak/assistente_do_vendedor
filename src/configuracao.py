"""
Leitura do config.json (credenciais e IDs), compartilhada pelos outros arquivos.

O config.json fica na MESMA pasta do script (ou do .exe, se gerado com PyInstaller).
Ele NÃO deve ir para o GitHub: use o config.exemplo.json como modelo.
"""

import json
import os
import sys

_CACHE = None


def pasta_base():
    """Pasta do script, ou do executável quando gerado com PyInstaller."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


ARQUIVO_CONFIG = os.path.join(pasta_base(), "config.json")


def carregar_config():
    """Lê o config.json uma única vez e devolve o dicionário."""
    global _CACHE
    if _CACHE is None:
        if not os.path.isfile(ARQUIVO_CONFIG):
            raise RuntimeError(
                f"Não encontrei o config.json em {pasta_base()}.\n"
                "Copie o config.exemplo.json, renomeie para config.json e preencha."
            )
        with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE
