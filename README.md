# Assistente do Vendedor

Aplicativo de desktop (Windows) que automatiza a rotina de compras de uma loja de móveis on-line:
do pedido que chega pela **Tray** às ordens de compra no **Bling**, aos cards de produção e logística no **Trello**
e aos lembretes de prazo pelo **WhatsApp**.

> **Projeto de portfólio.** Todos os dados deste repositório são fictícios. A versão de demonstração
> não acessa nenhuma plataforma: Bling, Trello, Tray e WhatsApp são simulados dentro do programa.

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
| **Pedidos para comprar** | Abre mostrando, em cards, os pedidos da Tray que esperam compra, com os itens e alertas: borda vermelha para quem espera há mais de 1 dia útil, âmbar para quem já tem OC ou card. |
| **Compras** | Lê o pedido no Bling pelo número da Tray, calcula os prazos pelo frete da transportadora, desmembra produtos estruturados em componentes, agrupa uma OC por fornecedor, manda personalizações para a OC da fábrica, cria os cards no Trello com **fichas em imagem** do pedido e da OC e atualiza status e observações no Bling e na Tray. |
| **Prazos de frete** | Converte as planilhas das transportadoras (por cidade ou por faixa de CEP) e calcula a **data máxima de embarque** de cada pedido: prazo combinado menos o frete até o endereço do cliente. |
| **Checklist de separação** | Cada card da logística ganha uma checklist com as peças e a OC de cada uma; o assistente confere as OCs no Bling e atualiza o texto (prazo, atraso, recebida) de hora em hora. Cards parados há mais de 2 dias úteis sobem para o topo da lista. |
| **Mensagens do dia** | Régua de lembretes pelo WhatsApp: aos fornecedores (14 e 7 dias úteis antes, no dia e cobrança diária em atraso) e à logística (2 dias úteis antes da data máxima de embarque, no dia e em atraso). Envio automático em horário comercial, com modo teste e histórico exportável para Excel. |
| **Calculadora de descontos** | Valores em 12x, 3x e à vista no Pix, aceitando o formato brasileiro (`1.500,50`). |
| **Descrição em HTML** | Monta a observação padrão do pedido com os itens puxados do Bling e calcula as datas de embarque e entrega em dias úteis. |

### Como ficam os cards no Trello

Exemplo gerado pela demonstração com o pedido fictício 1002 (`py docs/gerar_exemplos.py`; os textos dos cards e
a checklist estão em [`docs/exemplos/cards.md`](docs/exemplos/cards.md)). A ficha anexada substitui os prints manuais.

| Card da logística: ficha do pedido | Card da fábrica: ficha da OC |
|---|---|
| <img src="docs/exemplos/ficha_pedido_1002.png" alt="Ficha do pedido" width="420"> | <img src="docs/exemplos/ficha_OC_5003.png" alt="Ficha da OC" width="420"> |

Regras de negócio que o código aplica:
- cada OC lista **só os itens que ela compra**; a OC da fábrica sempre mostra item + personalização;
- prazos contados da **data da compra** em dias úteis, descontando feriados nacionais (e os extras do `config.json`):
  entrega ao cliente = compra + prazo combinado; **embarque máximo** = entrega − frete da tabela;
  fornecedores entregam até o embarque − 3 dias úteis de logística (data sugerida nas OCs e no card da fábrica);
- destino fora das tabelas de frete: vale a regra anterior (card da logística = prazo combinado − 10 dias úteis);
- pedido com prazo já estourado aparece como **ATRASADO** no título dos cards e nas fichas;
- as observações do pedido na Tray são atualizadas num **bloco gerenciado**, sem apagar o que outras pessoas escreveram;
- a transportadora vem do próprio pedido; o usuário só confirma;
- se algo falha no meio, o programa avisa o que **já foi criado**, para ninguém duplicar OC ou card.

## Como testar (sem conta em nenhuma plataforma)

**Executável:** baixe o `Assistente do Vendedor - DEMO.exe` na aba *Releases* e abra.
Pedidos de exemplo: **1001** (em estoque, frete local), **1002** (mesa estruturada + cadeiras, frete pela tabela)
e **1003** (personalização, destino sem tabela). A lista de separação já começa com dois cards fictícios,
para mostrar a medição de cards parados e os lembretes à logística.
Ao terminar um pedido, a demonstração abre a janela **Cards criados**, com os cards como ficariam no
Trello (lista, data, checklist e a ficha anexada); o botão **Ver cards criados** reabre a janela.

**Pelo código:**

```bash
py -m pip install customtkinter pillow requests
py src/app_demo.py
```

**Testes automáticos** (21 testes; os de demonstração rodam com a internet *bloqueada*):

```bash
py -m unittest discover testes
```

## Arquitetura

```
src/
  app.py                    janela (customtkinter): telas, botões e o painel de perguntas
  ferramentas_internas.py   regras de negócio e fluxo de compras (também roda no terminal)
  BLING.py                  API v3 do Bling: OAuth2, renovação de token, limite de requisições
  TRAY.py                   API da Tray: autenticação, limites de uso, pedidos, observações e status
  fichas.py                 fichas em imagem (PNG) do pedido e da OC, anexadas aos cards
  prazos_frete.py           tabelas de frete das transportadoras (Excel -> JSON) e cálculo do prazo
  notas_compras.py          bloco gerenciado nas observações do pedido (preserva o resto do texto)
  WHATSAPP.py               envio pelo WhatsApp Web (Playwright), com modo teste e limite diário
  demo.py                   Bling, Trello, Tray e WhatsApp simulados, com dados fictícios
  app_demo.py               abre a janela já em modo demonstração
  configuracao.py           leitura do config.json
testes/                     testes automáticos (unittest)
docs/index.html             explicação visual dos processos
docs/exemplos/              fichas e cards de exemplo (gerados por docs/gerar_exemplos.py)
```

O fluxo usa `print()`/`input()`, então funciona no terminal e na janela: a janela troca essas duas funções
por um painel que mostra uma pergunta por vez, com botões para as escolhas.

## Segurança

- Nenhuma credencial no código: chaves ficam num `config.json` local, fora do Git (`.gitignore`).
  O modelo está em [`src/config.exemplo.json`](src/config.exemplo.json).
- Tokens gravados de forma atômica (arquivo temporário + troca), para não corromper se o programa fechar.
- Chave e token do Trello vão no cabeçalho, não na URL, para não aparecerem em mensagens de erro;
  o módulo da Tray também apaga segredos das mensagens.
- O executável de demonstração é gerado **sem** os módulos `BLING.py`, `TRAY.py` e `WHATSAPP.py`.
- Dados de trabalho (pedidos acompanhados, mensagens enviadas, histórico, tabelas de frete, sessão do WhatsApp)
  ficam só no computador e também estão no `.gitignore`; na demonstração vão para uma pasta temporária.
- Antes de gravar observações na Tray, o programa relê o pedido e só grava se ninguém mudou o texto no meio;
  ao criar uma OC, relê e confere o fornecedor antes de seguir.
- O WhatsApp começa em **modo teste**: as mensagens vão para números de teste até a liberação.

## Uso real

1. Copie `src/config.exemplo.json` para `src/config.json` e preencha as credenciais.
2. Rode `py src/app.py` (ou gere o executável com `gerar_exe.bat`).

## Próximos passos

- Levar o fluxo para um servidor central, para funcionar com o computador desligado.
- Quadro de acompanhamento de vendas por vendedor, com alertas de prazo.

## Tecnologias

Python 3 · customtkinter · requests · Pillow · Playwright · PyInstaller · APIs REST (Bling v3, Trello, Tray)

## Licença

[MIT](LICENSE): pode usar, copiar e modificar, desde que mantenha o aviso de copyright.
