"""Sincroniza os preços dos kits da Tray com os preços atuais das variações.

O kit da Tray guarda uma tabela própria (ProductVariantKit: variação -> preço) que NÃO se atualiza
quando o preço do produto muda (por exemplo, pelo Bling). Este script é o "reset": recalcula e regrava.

Regra do preço de cada variação dentro do kit:
    preço da variação x quantidade do item;  se price_rule = 2 e desconto em %, aplica o desconto.

Uso:
    python sincronizar_kits.py                 -> só mostra o que está diferente (não grava nada)
    python sincronizar_kits.py --kit 900        -> mostra só esse kit (com --gravar, grava só ele)
    python sincronizar_kits.py --gravar        -> grava todos os kits com diferença
    --incluir-faltantes                        -> também inclui variações que não estão no kit (cuidado:
                                                  kits feitos para uma medida só passariam a oferecer todas)
Antes de gravar, salva uma cópia de cada kit em backups_kits/ para poder desfazer.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import TRAY  # noqa: E402

PASTA_BACKUP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups_kits")


def _todas_paginas(caminho, chave, params=None):
    itens, pagina = [], 1
    while True:
        d = TRAY.chamar_tray("GET", caminho, {**(params or {}), "limit": 50, "page": pagina})
        itens += d.get(chave, [])
        if pagina * 50 >= int(d["paging"]["total"]):
            return itens
        pagina += 1


_cache_variacoes = {}


def variacoes(produto_id):
    if produto_id not in _cache_variacoes:
        vs = _todas_paginas("/products/variants/", "Variants", {"product_id": produto_id})
        _cache_variacoes[produto_id] = {v["Variant"]["id"]: preco_vigente(v["Variant"]) for v in vs}
    return _cache_variacoes[produto_id]


def preco_vigente(v):
    """A Tray usa no kit o preço promocional quando a promoção está ativa hoje (conferido na própria loja)."""
    hoje = datetime.date.today().isoformat()
    promo = float(v.get("promotional_price") or 0)
    ini, fim = v.get("start_promotion") or "", v.get("end_promotion") or ""
    if promo > 0 and ini[:10] <= hoje and (not fim or fim.startswith("0000") or hoje <= fim[:10]):
        return promo
    return float(v["price"])


def preco_no_kit(preco_unitario, item):
    total = preco_unitario * float(item["quantity"])
    if str(item["price_rule"]) == "2":
        valor = float(item["discount_value"] or 0)
        if item["discount_type"] == "%":
            total *= (1 - valor / 100)
        else:
            raise ValueError(f"desconto em R$ no item {item['id']}: regra não confirmada, não mexo")
    return round(total + 1e-9, 2)


def kits_atuais():
    kits = {}
    for x in _todas_paginas("/products/kits/", "ProductKits"):
        k = x["ProductKit"]
        kits.setdefault(k["product_parent_id"], []).append(k)
    return kits


def planejar(itens, incluir_faltantes=False):
    """Devolve (payload, mudancas, faltantes) para um kit."""
    payload, mudancas, faltantes = [], [], []
    for item in itens:
        reais = variacoes(item["product_id"])
        novas = []
        for pv in item["ProductVariantKit"]:
            vid = pv["variant_id"]
            if vid not in reais:          # variação apagada do produto: deixa como está
                novas.append({"variant_id": vid, "product_kit_id": pv["product_kit_id"], "price": pv["price"]})
                continue
            certo = preco_no_kit(reais[vid], item)
            if abs(certo - float(pv["price"])) > 0.009:
                mudancas.append((item["product_id"], vid, float(pv["price"]), certo))
            novas.append({"variant_id": vid, "product_kit_id": pv["product_kit_id"], "price": f"{certo:.2f}"})
        ja = {pv["variant_id"] for pv in item["ProductVariantKit"]}
        for vid, preco in reais.items():
            if vid not in ja:
                faltantes.append((item["product_id"], vid, preco_no_kit(preco, item)))
                if incluir_faltantes and item["ProductVariantKit"]:
                    novas.append({"variant_id": vid, "product_kit_id": item["ProductVariantKit"][0]["product_kit_id"],
                                  "price": f"{preco_no_kit(preco, item):.2f}"})
        linha = {"product_parent_id": item["product_parent_id"], "product_id": item["product_id"],
                 "quantity": item["quantity"], "price_rule": item["price_rule"],
                 "discount_type": item["discount_type"], "discount_value": item["discount_value"]}
        if novas:
            linha["ProductVariantKit"] = novas
        payload.append(linha)
    return payload, mudancas, faltantes


def gravar(kit_id, itens, payload):
    os.makedirs(PASTA_BACKUP, exist_ok=True)
    marca = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    with open(os.path.join(PASTA_BACKUP, f"kit_{kit_id}_{marca}.json"), "w", encoding="utf-8") as f:
        json.dump(itens, f, ensure_ascii=False, indent=1)
    return TRAY.chamar_tray("POST", "/products/kits/", json=payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kit")
    ap.add_argument("--gravar", action="store_true")
    ap.add_argument("--incluir-faltantes", action="store_true")
    a = ap.parse_args()

    kits = kits_atuais()
    alvo = [a.kit] if a.kit else sorted(kits)
    resumo = []
    for kid in alvo:
        itens = kits[kid]
        try:
            payload, mud, falt = planejar(itens, a.incluir_faltantes)
        except ValueError as e:
            print(f"kit {kid}: PULADO ({e})")
            continue
        resumo.append((kid, len(mud), len(falt)))
        if not mud and not (a.incluir_faltantes and falt):
            continue
        print(f"kit {kid}: {len(mud)} preço(s) errado(s), {len(falt)} variação(ões) fora do kit")
        for pid, vid, antes, depois in mud[:5]:
            print(f"    item {pid} variação {vid}: {antes:.2f} -> {depois:.2f}")
        if a.gravar:
            r = gravar(kid, itens, payload)
            print(f"    gravado: {r}")
    print("total:", len(resumo), "kits;", sum(1 for r in resumo if r[1]), "com preço errado;",
          sum(r[1] for r in resumo), "preços a corrigir;", sum(r[2] for r in resumo), "variações fora dos kits")


if __name__ == "__main__":
    main()
