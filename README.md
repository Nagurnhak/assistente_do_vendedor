# Assistente do Vendedor

Aplicativo de desktop (Windows) que automatiza a rotina de compras de uma loja de móveis on-line:
do pedido que chega pela **Tray** às ordens de compra no **Bling** e aos cards de produção e logística no **Trello**.

> **Projeto de portfólio.** Todos os dados deste repositório são fictícios. A versão de demonstração
> não acessa nenhuma plataforma: Bling, Trello e Tray são simulados dentro do programa.

📄 **Explicação visual dos processos:** [abrir a página](https://nagurnhak.github.io/assistente_do_vendedor/)

---

## O problema

Cada venda exigia vários passos manuais entre três sistemas: conferir o pedido, descobrir o fornecedor
de cada item (inclusive das peças de produtos montados, como mesa = tampo + base), emitir uma ordem de
compra por fornecedor, abrir cards para a fábrica e a logística com prints e prazos, e atualizar o status
do pedido. Era lento e fácil de errar.
## O Resultado

- **Medido:** em 1 semana de uso pelos vendedores, o tempo gasto com compras caiu **80%**.
- **Esperado com a integração da Tray:** cada pedido deve passar de cerca de **5 minutos para 30 segundos** (10 vezes mais rápido).

## O que o assistente faz


<img width="1471" height="870" alt="image" src="https://github.com/user-attachments/assets/4b84c360-9565-4ff7-9b4e-e4a61a283b11" />



| Ferramenta | O que resolve |
|---|---|
| **Compras** | Lê o pedido no Bling pelo número da Tray, desmembra produtos estruturados em componentes, agrupa uma OC por fornecedor, manda personalizações para a OC da fábrica, cria os cards no Trello (com prints) e atualiza o status no Bling e na Tray. |
| **Calculadora de descontos** | Valores em 12x, 3x e à vista no Pix, aceitando o formato brasileiro (`1.500,50`). |
| **Descrição em HTML** | Monta a observação padrão do pedido com os itens puxados do Bling e calcula as datas de embarque e entrega em dias úteis. |

Regras de negócio que o código aplica:
- cada OC lista **só os itens que ela compra**; a OC da fábrica sempre mostra item + personalização;
- prazo do card de logística = prazo combinado **menos 10 dias úteis** (até 10, mantém);
- a transportadora vem do próprio pedido; o usuário só confirma;
- se algo falha no meio, o programa avisa o que **já foi criado**, para ninguém duplicar OC ou card.

## Como testar (sem conta em nenhuma plataforma)

**Executável:** baixe o `Assistente do Vendedor - DEMO.exe` na aba *Releases* e abra.
Pedidos de exemplo: **1001** (em estoque), **1002** (mesa estruturada + cadeiras) e **1003** (personalização).

**Pelo código:**

```bash
py -m pip install customtkinter pillow requests
py src/app_demo.py
```

**Testes automáticos** (15 testes; os de demonstração rodam com a internet *bloqueada*):

```bash
py -m unittest discover testes
```

## Arquitetura

```
src/
  app.py                    janela (customtkinter): telas, botões e o painel de perguntas
  ferramentas_internas.py   regras de negócio e fluxo de compras (também roda no terminal)
  BLING.py                  API v3 do Bling: OAuth2, renovação de token, limite de requisições
  TRAY.py                   API da Tray: autenticação, observações e status do pedido
  demo.py                   Bling, Trello e Tray simulados, com dados fictícios
  app_demo.py               abre a janela já em modo demonstração
  configuracao.py           leitura do config.json
testes/                     testes automáticos (unittest)
docs/index.html             explicação visual dos processos
```

O fluxo usa `print()`/`input()`, então funciona no terminal e na janela: a janela troca essas duas funções
por um painel que mostra uma pergunta por vez, com botões para as escolhas.

## Segurança

- Nenhuma credencial no código: chaves ficam num `config.json` local, fora do Git (`.gitignore`).
  O modelo está em [`src/config.exemplo.json`](src/config.exemplo.json).
- Tokens gravados de forma atômica (arquivo temporário + troca), para não corromper se o programa fechar.
- Chave e token do Trello vão no cabeçalho, não na URL, para não aparecerem em mensagens de erro;
  o módulo da Tray também apaga segredos das mensagens.
- O executável de demonstração é gerado **sem** os módulos `BLING.py` e `TRAY.py`.

## Uso real

1. Copie `src/config.exemplo.json` para `src/config.json` e preencha as credenciais.
2. Rode `py src/app.py` (ou gere o executável com `gerar_exe.bat`).

## Próximos passos

- Liberar a integração com a Tray na loja real (já validada no ambiente de testes).
- Quadro de acompanhamento de vendas por vendedor, com alertas de prazo.

## Tecnologias

Python 3 · customtkinter · requests · Pillow · PyInstaller · APIs REST (Bling v3, Trello, Tray)

## Licença

[MIT](LICENSE): pode usar, copiar e modificar, desde que mantenha o aviso de copyright.
