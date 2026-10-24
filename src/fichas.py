"""
Fichas em imagem (PNG) para os cards do Trello, no lugar dos prints manuais:
- ficha do PEDIDO (card da Logística): cliente e entrega, itens com foto e OC, observações do pedido (HTML),
  frete e pagamento, observação do cliente;
- ficha da OC (card da Fábrica): urgente, prazos, itens com foto (nome da Tray e, embaixo, o do Bling),
  personalização e observações internas.

Só desenha: recebe os dados prontos (montados no ferramentas_internas.py) e devolve os bytes do PNG.
Sem CPF/CNPJ, e-mail ou valores.
"""

from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

LARGURA = 1000
MARGEM = 40
FOTO = 150
LARANJA, ESCURO, SUAVE, LINHA, FUNDO = "#D9631E", "#2A2622", "#6B625B", "#EADFD6", "#FBF4EE"
VERDE, AMBAR, VERMELHO, CREME = "#1E7B4F", "#9A6200", "#B42318", "#FFF1E6"

_FONTES = {}


def fonte(tamanho, negrito=False):
    chave = (tamanho, negrito)
    if chave not in _FONTES:
        nome = "segoeuib.ttf" if negrito else "segoeui.ttf"
        try:
            _FONTES[chave] = ImageFont.truetype(f"C:/Windows/Fonts/{nome}", tamanho)
        except OSError:
            try:
                _FONTES[chave] = ImageFont.truetype("DejaVuSans-Bold.ttf" if negrito else "DejaVuSans.ttf", tamanho)
            except OSError:
                _FONTES[chave] = ImageFont.load_default()
    return _FONTES[chave]


def _quebrar(texto, f, largura):
    """Quebra por largura em pixels (não por letras)."""
    linhas, atual = [], ""
    for palavra in str(texto or "").split():
        tentativa = f"{atual} {palavra}".strip()
        if f.getlength(tentativa) <= largura or not atual:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _foto(conteudo, lado=FOTO, raio=16):
    imagem = Image.open(BytesIO(conteudo)).convert("RGB")
    imagem.thumbnail((lado, lado), Image.LANCZOS)
    fundo = Image.new("RGB", (lado, lado), "white")
    fundo.paste(imagem, ((lado - imagem.width) // 2, (lado - imagem.height) // 2))
    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, lado - 1, lado - 1], radius=raio, fill=255)
    return fundo, mascara


class _Tela:
    def __init__(self, altura_max=8000):
        self.img = Image.new("RGB", (LARGURA, altura_max), "white")
        self.d = ImageDraw.Draw(self.img)
        self.y = 0

    def texto(self, x, y, texto, tam, negrito=False, cor=ESCURO, anchor=None):
        self.d.text((x, y), str(texto), font=fonte(tam, negrito), fill=cor, anchor=anchor)

    def paragrafo(self, x, texto, tam, negrito=False, cor=ESCURO, largura=None, entre=10):
        largura = largura or (LARGURA - MARGEM - x)
        for parte in _quebrar(texto, fonte(tam, negrito), largura):
            self.texto(x, self.y, parte, tam, negrito, cor)
            self.y += tam + entre

    def secao(self, titulo):
        self.texto(MARGEM, self.y, titulo.upper(), 17, True, LARANJA)
        self.y += 30
        self.d.line([MARGEM, self.y, LARGURA - MARGEM, self.y], fill=LINHA, width=2)
        self.y += 14

    def item(self, quantidade, titulo, linhas, foto=None, selo=None, cor_selo=VERDE):
        """Item com foto à esquerda; linhas: [(texto, tamanho, negrito, cor)]."""
        y0 = self.y
        x = MARGEM
        if foto:
            try:
                imagem, mascara = _foto(foto)
                self.d.rounded_rectangle([x - 1, y0 - 1, x + FOTO, y0 + FOTO], radius=16, outline=LINHA, width=2)
                self.img.paste(imagem, (x, y0), mascara)
                x += FOTO + 24
            except Exception:
                pass
        largura = LARGURA - MARGEM - x - (240 if selo else 0)
        self.texto(x, y0, f"{quantidade}x", 30, True, LARANJA)
        self.y = y0 + 44
        self.paragrafo(x, titulo, 24, True, largura=largura)
        for texto, tam, negrito, cor in linhas:
            if texto:
                self.paragrafo(x, texto, tam, negrito, cor, largura=largura, entre=8)
        if selo:
            self.d.rounded_rectangle([LARGURA - 260, y0, LARGURA - MARGEM, y0 + 40], radius=10, fill=FUNDO, outline=LINHA)
            self.texto(LARGURA - 150, y0 + 20, selo, 18, True, cor_selo, anchor="mm")
        self.y = max(self.y, y0 + (FOTO if x > MARGEM else 0)) + 22
        self.d.line([MARGEM, self.y - 11, LARGURA - MARGEM, self.y - 11], fill=LINHA, width=1)

    def caixa_texto(self, texto, tam=21, cor_fundo=FUNDO, borda=None, titulo=None):
        largura = LARGURA - 2 * MARGEM - 40
        linhas = _quebrar(texto, fonte(tam), largura)
        altura = 24 + len(linhas) * (tam + 10) + (36 if titulo else 0)
        self.d.rounded_rectangle([MARGEM, self.y - 4, LARGURA - MARGEM, self.y + altura], radius=10, fill=cor_fundo,
                                 outline=borda, width=2 if borda else 0)
        yy = self.y + 10
        if titulo:
            self.texto(MARGEM + 20, yy, titulo, tam, True, LARANJA)
            yy += 36
        for parte in linhas:
            self.texto(MARGEM + 20, yy, parte, tam)
            yy += tam + 10
        self.y += altura + 22

    def colunas(self, pares):
        """[(rótulo, valor)] lado a lado, até 3 por linha."""
        for i in range(0, len(pares), 3):
            altura = 72
            for j, (rotulo, valor) in enumerate(pares[i:i + 3]):
                x = MARGEM + j * 320
                self.texto(x, self.y, rotulo, 18, cor=SUAVE)
                linhas = _quebrar(valor or "-", fonte(22, True), min(296, LARGURA - MARGEM - x))
                for k, parte in enumerate(linhas[:2]):
                    self.texto(x, self.y + 26 + k * 30, parte + ("…" if k == 1 and len(linhas) > 2 else ""), 22, True)
                altura = max(altura, 42 + 30 * min(len(linhas), 2))
            self.y += altura

    def rodape(self, origem, aviso=None):
        self.d.line([MARGEM, self.y, LARGURA - MARGEM, self.y], fill=LINHA, width=1)
        self.texto(MARGEM, self.y + 12, f"Gerado pelo Assistente do Vendedor a partir {origem} · "
                                         f"{datetime.now().strftime('%d/%m/%Y %H:%M')}", 16, cor=SUAVE)
        if aviso:
            self.texto(LARGURA - MARGEM, self.y + 12, aviso, 16, True, AMBAR, anchor="ra")
        self.y += 50

    def linha_cortada(self, x, y, texto, tam, largura, negrito=False, cor=ESCURO):
        """Uma linha só: se não couber, corta com '…'."""
        f = fonte(tam, negrito)
        texto = str(texto or "")
        if f.getlength(texto) > largura:
            while texto and f.getlength(texto + "…") > largura:
                texto = texto[:-1]
            texto = texto.rstrip() + "…"
        self.texto(x, y, texto, tam, negrito, cor)

    def png(self):
        saida = BytesIO()
        self.img.crop((0, 0, LARGURA, self.y)).save(saida, format="PNG", optimize=True)
        return saida.getvalue()


def ficha_pedido(p):
    """p: numero, data, status, entrega, cliente, telefone, endereco[], recebe, itens[{qtd, titulo, variacao, ref,
    ocs, foto}], html[(rotulo, valor, destaque)], frete, transportadora, pagamento, observacao_cliente."""
    t = _Tela()
    d = t.d
    d.rectangle([0, 0, LARGURA, 120], fill=LARANJA)
    t.texto(MARGEM, 22, f"Pedido {p['numero']}", 44, True, "white")
    t.linha_cortada(MARGEM, 80, " · ".join(x for x in ("Tray", p.get("data"), p.get("status")) if x), 22, 680, cor="white")
    pz = p.get("prazos")
    if pz:
        t.texto(LARGURA - MARGEM, 30, "Embarque máximo" + (" · ATRASADO" if pz.get("atrasado") else ""), 18,
                pz.get("atrasado"), "white", anchor="ra")
        t.texto(LARGURA - MARGEM, 56, pz["embarque"], 34, True, "white", anchor="ra")
    elif p.get("entrega"):
        t.texto(LARGURA - MARGEM, 30, "Entrega prevista", 18, cor="white", anchor="ra")
        t.texto(LARGURA - MARGEM, 56, p["entrega"], 34, True, "white", anchor="ra")
    t.y = 150

    t.secao("Cliente e entrega")
    topo = t.y
    t.paragrafo(MARGEM, p.get("cliente") or "-", 24, True, largura=440)
    if p.get("telefone"):
        t.paragrafo(MARGEM, p["telefone"], 20, cor=SUAVE, largura=440)
    fim_esquerda = t.y
    t.y = topo
    for i, linha in enumerate(p.get("endereco") or []):
        t.paragrafo(520, linha, 22, i == 0, largura=440, entre=10)
    if p.get("recebe"):
        t.paragrafo(520, f"Recebe: {p['recebe']}", 18, cor=SUAVE, largura=440)
    t.y = max(fim_esquerda, t.y) + 16

    t.secao(f"Itens ({len(p['itens'])})")
    for item in p["itens"]:
        linhas = [(item.get("variacao"), 20, False, ESCURO), (f"Ref. {item['ref']}" if item.get("ref") else "", 18, False, SUAVE),
                  (item.get("aviso"), 18, True, VERMELHO)]
        t.item(item["qtd"], item["titulo"], linhas, item.get("foto"), item.get("ocs") or None,
               VERDE if "OC" in (item.get("ocs") or "") else AMBAR)

    if p.get("html"):
        t.secao("Observações do pedido")
        html = p["html"]
        metade = (len(html) + 1) // 2
        topo = t.y - 4
        for i, (rotulo, valor, destaque) in enumerate(html):
            x = 60 if i < metade else 520
            yy = t.y + 14 + (i % metade) * 54
            t.texto(x, yy, rotulo, 17, cor=VERMELHO if destaque else SUAVE)
            partes = _quebrar(valor or "-", fonte(21, True), 400)
            valor = partes[0] + ("…" if len(partes) > 1 else "")
            t.texto(x, yy + 22, valor, 21, True)
        altura = metade * 54 + 18
        d.rounded_rectangle([MARGEM, topo, LARGURA - MARGEM, topo + altura], radius=10, outline=LINHA, width=2)
        t.y = topo + altura + 22

    t.secao("Transporte e prazos")  # no fim e enxuto; o embarque máximo já está em destaque no cabeçalho
    if pz:
        t.colunas([("Embarque máximo", pz["embarque"] + (" - ATRASADO" if pz.get("atrasado") else "")),
                   ("Fornecedores até", pz["fornecedores"]), ("Entrega ao cliente", pz["entrega"])])
        t.colunas([("Transportadora", p.get("transportadora")), ("Prazo do frete", pz["frete"].split(": ", 1)[-1]),
                   ("Pagamento", p.get("pagamento"))])
    else:
        t.colunas([("Frete", p.get("frete")), ("Transportadora", p.get("transportadora")), ("Pagamento", p.get("pagamento"))])

    if p.get("observacao_cliente"):
        t.secao("Observação do cliente (na compra)")
        t.caixa_texto(p["observacao_cliente"])
    t.rodape("da Tray")
    return t.png()


def ficha_oc(o):
    """o: numero, fornecedor, pedido, venda_bling, emissao, urgente, data_prevista, embarque, entrega_cliente,
    itens[{qtd, titulo, nome_bling, foto}], personalizacao[(produto, texto)], observacoes."""
    t = _Tela()
    d = t.d
    d.rectangle([0, 0, LARGURA, 120], fill=ESCURO)
    t.texto(MARGEM, 22, f"OC {o['numero']}", 44, True, "white")
    largura_numero = fonte(44, True).getlength(f"OC {o['numero']}")
    x = MARGEM + largura_numero + 40
    for selo, ativo in (("ATRASADO", o.get("atrasado")), ("URGENTE", o.get("urgente"))):
        if ativo:
            largura_selo = fonte(20, True).getlength(selo) + 40
            d.rounded_rectangle([x, 32, x + largura_selo, 72], radius=10, fill=VERMELHO)
            t.texto(x + largura_selo / 2, 52, selo, 20, True, "white", anchor="mm")
            x += largura_selo + 12
    t.linha_cortada(MARGEM, 80, " · ".join(x for x in (o.get("fornecedor"), f"Pedido Tray {o['pedido']}" if o.get("pedido") else "",
                                                         f"Venda Bling {o['venda_bling']}" if o.get("venda_bling") else "",
                                                         o.get("emissao")) if x), 20, 680, cor=LINHA)
    if o.get("data_prevista"):
        t.texto(LARGURA - MARGEM, 30, "Data prevista da OC", 18, cor=LINHA, anchor="ra")
        t.texto(LARGURA - MARGEM, 56, o["data_prevista"], 34, True, "white", anchor="ra")
    d.rectangle([0, 120, LARGURA, 126], fill=LARANJA)
    t.y = 156

    if o.get("itens"):
        t.secao(f"Itens a fabricar ({len(o['itens'])})")
        for item in o["itens"]:
            t.item(item["qtd"], item["titulo"], [(item.get("nome_bling"), 19, False, SUAVE)], item.get("foto"))

    if o.get("personalizacao"):
        t.secao("Personalização")
        for produto, texto in o["personalizacao"]:
            t.caixa_texto(texto, cor_fundo=CREME, borda=LARANJA, titulo=produto)

    if o.get("observacoes"):
        t.secao("Observações internas")
        t.caixa_texto(o["observacoes"], tam=20)
    t.secao("Prazos")  # no fim e enxuto; a data prevista já está em destaque no cabeçalho
    t.colunas([("Data prevista da OC", o.get("data_prevista")), ("Embarque máximo", o.get("embarque")),
               ("Entrega ao cliente", o.get("entrega_cliente"))])
    t.rodape("do Bling")
    return t.png()
