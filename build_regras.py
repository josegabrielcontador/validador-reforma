#!/usr/bin/env python3
"""
Gera regras.json para o Validador Reforma Smartcontax.

Fonte: pacote npm @sinete/ibs-cbs-dados (dados extraidos da Calculadora offline da RFB
e do IT 2025.002), mais um arquivo opcional novidades.json com o boletim legislativo.

Uso:
  npm pack @sinete/ibs-cbs-dados && tar xzf sinete-ibs-cbs-dados-*.tgz
  python3 build_regras.py --dados package/src/data --novidades novidades.json --saida regras.json
"""
import argparse, json, datetime, os

# Codigos de bens por NCM aplicaveis em qualquer venda (sem condicao do adquirente)
PADRAO_ZERO = ["200003", "200014", "200004", "200007", "200013", "200053", "200009"]
PADRAO_60 = ["200034", "200030", "200031", "200033", "200035", "200038", "200032"]
# Codigos validos so com condicao especifica (adquirente, regime, regiao)
CONDICIONAIS = {
    "200002": "Fornecimento para produtor rural não contribuinte ou TAC",
    "200005": "Somente vendas a órgãos públicos e entidades de saúde imunes",
    "200006": "Somente em emergência de saúde pública reconhecida",
    "200008": "Somente vendas a órgãos públicos",
    "200010": "Somente vendas a órgãos públicos",
    "200011": "Somente vendas a órgãos públicos",
    "200012": "Somente em emergência de saúde pública reconhecida",
    "200015": "Somente vendas a taxistas/PcD com requisitos legais",
    "200020": "Somente cooperativas optantes pelo regime específico",
    "200022": "Somente destino Zona Franca de Manaus",
    "200023": "Somente indústria incentivada da ZFM",
    "200024": "Somente destino Áreas de Livre Comércio",
    "200036": "Somente produtor rural/extrativista (in natura)",
    "200039": "Somente produções artísticas/culturais com requisitos legais",
    "200043": "Somente vendas à administração pública (soberania)",
    "200054": "Somente cooperativa agropecuaria a associado",
    "515001": "Operação com diferimento (insumos agropecuários)",
}
# Heuristicas para codigos sem lista de NCM na base oficial
HEURISTICAS = [
    {"prefixos": ["3001", "3002", "3003", "3004", "3005", "3006"], "cClassTrib": "200032",
     "msg": "Possível medicamento: redução de 60% se registrado na Anvisa. Se constar do Anexo XIV, alíquota zero (200009). Confirmar registro."},
    {"prefixos": ["96190000"], "cClassTrib": "200013",
     "msg": "Absorventes e tampões higiênicos: alíquota zero (200013). Fraldas seguem a redução de 60% (200035). Confirmar o produto."},
]


# Ramos de atuação: limitam os enquadramentos possíveis por empresa (como a aba "Atividade" da e-Auditoria).
# tipo: "comercio" (NF-e, por NCM) ou "servico" (NFS-e, por NBS).
RAMOS = [
    {"id": "supermercado", "tipo": "comercio", "nome": "Supermercado, mercearia, padaria, açougue, hortifruti",
     "codigos": ["200003", "200014", "200034", "200035", "200013"]},
    {"id": "alimentos_ind", "tipo": "comercio", "nome": "Indústria ou distribuidora de alimentos",
     "codigos": ["200003", "200014", "200034"]},
    {"id": "restaurante", "tipo": "comercio", "nome": "Bar, restaurante, lanchonete (regime específico, redução de 40%)",
     "codigos": ["200047"], "especial": "restaurante"},
    {"id": "farmacia", "tipo": "comercio", "nome": "Farmácia, drogaria, manipulação",
     "codigos": ["200009", "200032", "200053", "200035", "200013", "200033", "200003", "200034"]},
    {"id": "higiene", "tipo": "comercio", "nome": "Higiene pessoal e limpeza (fabricante ou distribuidor)",
     "codigos": ["200035", "200013"]},
    {"id": "disp_medicos", "tipo": "comercio", "nome": "Dispositivos médicos, hospitalares e odontológicos, ortopedia",
     "codigos": ["200030", "200004"]},
    {"id": "acessibilidade", "tipo": "comercio", "nome": "Dispositivos de acessibilidade para pessoas com deficiência",
     "codigos": ["200031", "200007"]},
    {"id": "nutricao", "tipo": "comercio", "nome": "Nutrição clínica (enteral e parenteral)",
     "codigos": ["200033"]},
    {"id": "agro", "tipo": "comercio", "nome": "Agropecuário: insumos, ração, sementes, produtor rural",
     "codigos": ["200038", "515001", "200036", "200014", "200003"]},
    {"id": "editorial", "tipo": "comercio", "nome": "Livraria, editora, banca (imunidade de livros)",
     "codigos": ["410008"]},
    {"id": "cultura", "tipo": "comercio", "nome": "Produção artística, cultural e de eventos",
     "codigos": ["200039"]},
    {"id": "veiculos", "tipo": "comercio", "nome": "Concessionária: venda a taxistas e PcD",
     "codigos": ["200015"]},
    {"id": "saude", "tipo": "servico", "nome": "Serviços de saúde humana (clínicas, consultórios, laboratórios)",
     "codigos": ["200029"]},
    {"id": "educacao", "tipo": "servico", "nome": "Serviços de educação", "codigos": ["200028", "200025"]},
    {"id": "intelectuais", "tipo": "servico", "nome": "Profissões intelectuais regulamentadas (advocacia, contabilidade, engenharia etc.)",
     "codigos": ["200052"]},
    {"id": "planos_saude", "tipo": "servico", "nome": "Planos de assistência à saúde", "codigos": ["011002", "011003"]},
    {"id": "planos_pet", "tipo": "servico", "nome": "Planos de saúde para animais domésticos", "codigos": ["011005"]},
    {"id": "hotelaria", "tipo": "servico", "nome": "Hotelaria, parques e agências de turismo", "codigos": ["200048", "200051"]},
    {"id": "transporte", "tipo": "servico", "nome": "Transporte coletivo de passageiros", "codigos": ["200049", "200050", "400001", "400002"]},
    {"id": "imoveis", "tipo": "servico", "nome": "Locação e operações com imóveis", "codigos": ["200027", "200046", "200026"]},
    {"id": "seg_info", "tipo": "servico", "nome": "Segurança da informação e cibernética", "codigos": ["200044"]},
    {"id": "esporte", "tipo": "servico", "nome": "Educação desportiva e gestão do desporto", "codigos": ["200041", "200042"]},
]
# Códigos exclusivos de vendas a órgãos públicos (liberados pela opção "vende para órgãos públicos")
# Códigos de serviço que dependem de quem presta (não basta o NBS); só valem com o ramo marcado no perfil
COND_SERVICO = ["200052", "200025", "200044", "200040", "200041", "200042", "200016", "200045"]
GOVERNO = ["200005", "200008", "200010", "200011", "200043", "200006", "200012"]


def vig(v, hoje):
    return v["inicio"] <= hoje and (v["fim"] is None or v["fim"] >= hoje)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dados", required=True)
    ap.add_argument("--novidades", default=None)
    ap.add_argument("--saida", default="regras.json")
    ap.add_argument("--versao-pacote", default="")
    a = ap.parse_args()
    hoje = datetime.date.today().isoformat()
    L = lambda n: json.load(open(os.path.join(a.dados, n + ".json"), encoding="utf-8"))
    manifest, ct, apl, anexos = L("manifest"), L("classTrib"), L("aplicabilidadeNcm"), L("anexos")

    classes = {}
    for x in ct:
        if x["familia"] != "CBS_IBS" or not vig(x["vigencia"], hoje):
            continue
        nfe = any(d["modelo"] in (55, 65) and vig(d["vigencia"], hoje) for d in x["dfe"])
        red = {r["tributo"]: float(r["pRed"]) for r in x.get("reducoes", []) if vig(r["vigencia"], hoje)}
        classes[x["codigo"]] = {
            "cst": x["cst"], "nome": x.get("nome") or x["descricao"], "nfe": nfe,
            "rCBS": red.get("CBS", 0.0), "rIBS": red.get("IBSUF", 0.0),
            "lc": (x.get("legal") or {}).get("lc214") or "",
            "url": (x.get("legal") or {}).get("url") or "",
            "cond": CONDICIONAIS.get(x["codigo"], ""),
            "credito": bool((x.get("credito") or {}).get("adquirenteCbs")),
        }

    vinc = []
    itens_usados = set()
    for v in apl:
        if v["familia"] != "CBS_IBS" or not vig(v["vigencia"], hoje) or v["cClassTrib"] not in classes:
            continue
        ex = [e["prefixo"] for e in v["excecoes"] if vig(e["vigencia"], hoje)]
        vinc.append({"c": v["cClassTrib"], "p": v["prefixo"], "x": ex, "i": v.get("itemDoAnexo") or ""})
        if v.get("itemDoAnexo"):
            itens_usados.add(v["itemDoAnexo"])

    # NFS-e: combinações permitidas de NBS + item da LC 116 + indicador de operação (cIndOp) -> cClassTrib
    nfse = []
    try:
        for x in L("nfseNbs"):
            v = x["vigencia"]
            if v["fim"] is not None and v["fim"] < hoje[:4] + "-01-01":
                continue
            if x["cClassTrib"] not in classes or x.get("adquirenteExterior"):
                continue
            nfse.append([x["nbs"], x["itemLc116"], x["cIndOp"], x["cClassTrib"], v["inicio"], v["fim"] or ""])
    except FileNotFoundError:
        pass

    itens = {}
    for an in anexos:
        k = f'{an["anexo"]}/{an["item"]}'
        if k in itens_usados and vig(an["vigencia"], hoje):
            itens[k] = an["texto"]

    fontes = [{"titulo": f["titulo"], "versao": f.get("versao", ""), "data": f.get("data", ""), "url": f.get("url", "")}
              for f in manifest["fontes"]]
    novidades = json.load(open(a.novidades, encoding="utf-8")) if a.novidades and os.path.exists(a.novidades) else {}

    out = {
        "meta": {
            "geradoEm": hoje,
            "baseConhecidaEm": manifest.get("conhecidoEm"),
            "versaoPacote": a.versao_pacote,
            "hashDataset": manifest.get("sha256DoDataset", "")[:12],
            "fontes": fontes,
        },
        "aliquotas": novidades.get("aliquotas") or {
            "vigente": {"ano": 2026, "cbs": 0.9, "ibsUF": 0.1, "ibsMun": 0.0, "base": "LC 214/2025, arts. 343 e 346"},
            "cenarios": [
                {"id": "2027", "nome": "2027 (CBS cheia)", "cbs": 9.11, "ibs": 0.1,
                 "nota": "CBS 2027: estimativa CGIBS de 9,21% menos 0,1 p.p. (art. 347), até a resolução do Senado."},
                {"id": "pleno", "nome": "Regime pleno (2033)", "cbs": 9.21, "ibs": 18.7,
                 "nota": "Regime pleno: estimativa CGIBS (Res. 14/2026) de 27,91% somados, ainda não oficial."},
            ],
        },
        "obrigatoriedade": {"regimeNormal": "2026-08-03", "simples": "2027-01-04"},
        "padraoZero": [c for c in PADRAO_ZERO if c in classes],
        "padrao60": [c for c in PADRAO_60 if c in classes],
        "classes": classes,
        "vinculos": vinc,
        "itensAnexo": itens,
        "heuristicas": HEURISTICAS,
        "nfse": nfse,
        "condServico": [c for c in COND_SERVICO if c in classes],
        "ramos": [dict(r, codigos=[c for c in r["codigos"] if c in classes]) for r in RAMOS],
        "governo": [c for c in GOVERNO if c in classes],
        "novidades": novidades.get("itens", []),
        "verificacao": novidades.get("verificacao", {}),
    }
    with open(a.saida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK {a.saida}: {len(classes)} cClassTrib, {len(vinc)} vinculos NCM, {len(itens)} itens de anexo")


if __name__ == "__main__":
    main()
