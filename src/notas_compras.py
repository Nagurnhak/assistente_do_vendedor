"""Bloco HTML gerenciado pelo Assistente; preserva observações externas."""
import re


INICIO = '<!-- assistente-compras:v1 -->'
FIM = '<!-- /assistente-compras:v1 -->'
PARTE = re.compile(r'<!-- parte:([a-z0-9-]+) -->(.*?)<!-- /parte:\1 -->', re.S)


def atualizar_html(atual, partes):
    """Cria ou atualiza seções idempotentes de origem, prazo e OCs. Valor None remove a seção
    (ex.: as linhas soltas das OCs quando elas passam a aparecer ao lado dos produtos no HTML do prazo)."""
    if not partes or any(not re.fullmatch(r'(origem|prazo|oc-[0-9]+)', chave) for chave in partes):
        raise ValueError('Seções de acompanhamento inválidas')
    if any(valor is not None and (not isinstance(valor, str) or '<!--' in valor) for valor in partes.values()):
        raise ValueError('HTML de acompanhamento inválido')

    atual = atual or ''
    if atual.count(INICIO) != atual.count(FIM) or atual.count(INICIO) > 1:
        raise ValueError('Bloco existente ambíguo; conferir antes de alterar')

    preservadas = {}
    if INICIO in atual:
        inicio, fim = atual.index(INICIO), atual.index(FIM)
        if fim < inicio:
            raise ValueError('Bloco existente inválido')
        corpo = atual[inicio + len(INICIO):fim]
        matches = list(PARTE.finditer(corpo))
        if PARTE.sub('', corpo).strip():
            raise ValueError('Conteúdo inesperado no bloco gerenciado')
        for match in matches:
            if match[1] in preservadas:
                raise ValueError('Seção duplicada; reconciliar antes de alterar')
            preservadas[match[1]] = match[2]
        antes, depois = atual[:inicio], atual[fim + len(FIM):]
    else:
        antes, depois = (atual + '\n' if atual else ''), ''

    preservadas.update(partes)
    preservadas = {chave: valor for chave, valor in preservadas.items() if valor is not None}
    ordem = sorted(
        preservadas,
        key=lambda chave: (0 if chave == 'origem' else 2 if chave == 'prazo' else 1, chave),
    )
    bloco = INICIO + ''.join(
        f'<!-- parte:{chave} -->{preservadas[chave]}<!-- /parte:{chave} -->'
        for chave in ordem
    ) + FIM
    return antes + bloco + depois
