"""Gera os exemplos de cards (fichas do pedido e da OC) mostrados no README e na página, com a demonstração.

Roda o pedido fictício 1002 (mesa estruturada + cadeiras, tampo personalizado) sem acessar nada fora do
computador e salva em docs/exemplos/: as fichas anexadas aos cards e o texto de cada card (cards.md).

Rode na pasta do projeto:  py docs/gerar_exemplos.py
"""
import builtins
import contextlib
import io
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
SAIDA = os.path.join(RAIZ, "docs", "exemplos")

import ferramentas_internas as fi  # noqa: E402

fi.MODO_DEMO = True
import demo  # noqa: E402

demo.ATRASO = 0
RESPOSTAS = [
    "1002", "2", "", "",                    # pedido, precisa comprar, transportadora e prazo sugeridos
    "s", "s",                               # os dois itens precisam ser comprados
    "n", "s", "pintura preta", "50", "n",   # personalização só no tampo
    "", "", "", "", "s",                    # OC da metalúrgica
    "", "", "", "", "s",                    # OC dos estofados
    "", "", "", "", "", "s",                # OC da fábrica
    "s", "s",                               # OCs enviadas pelo Bling
    "s", "F", "", "",                       # HTML do pedido
    "n", "1", "s",                          # card da fábrica: não urgente, aba 1, confirma
]


def main():
    respostas = iter(RESPOSTAS)
    builtins.input = lambda *_: next(respostas)
    with contextlib.redirect_stdout(io.StringIO()):
        fi.processar_pedido()
    os.makedirs(SAIDA, exist_ok=True)
    linhas = ["# Cards criados pela demonstração (pedido 1002)\n"]
    for card in demo.CARDS[demo._INICIAIS:]:
        for nome, conteudo in (card.get("imagens") or {}).items():
            with open(os.path.join(SAIDA, nome), "wb") as f:
                f.write(conteudo)
        linhas.append(f"## Lista: {card['lista']}\n\n**{card['nome']}**  \nData de entrega do card: {card['prazo']}  \n"
                      f"Anexos: {', '.join(card['anexos'])}\n")
        for checklist in card["checklists"]:
            linhas.append(f"Checklist: {checklist['name']}\n")
            linhas += [f"- [ ] {item['name']}" for item in checklist["checkItems"]]
            linhas.append("")
    with open(os.path.join(SAIDA, "cards.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))
    print("Exemplos salvos em", SAIDA)
    for nome in sorted(os.listdir(SAIDA)):
        print("  ", nome)


if __name__ == "__main__":
    main()
