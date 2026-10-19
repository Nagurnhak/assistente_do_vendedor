"""
Assistente do Vendedor - versão de DEMONSTRAÇÃO.

Liga o modo demonstração ANTES de abrir a janela: Bling, Trello e Tray passam a ser
simulados pelo demo.py, com dados fictícios. Não lê config.json nem tokens e não acessa
a internet, então pode ser testado por qualquer pessoa sem risco.

Rode:  py app_demo.py
"""

import ferramentas_internas as fi

fi.MODO_DEMO = True

import app  # noqa: E402  (precisa vir depois de ligar o modo demonstração)

if __name__ == "__main__":
    app.App().mainloop()
