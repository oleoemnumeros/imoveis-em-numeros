"""Sondagem, segunda rodada: São Paulo (403 na primeira), Rio (dados agregados da Fazenda)
e detalhes de cobertura de BH, Recife, Fortaleza e Porto Alegre. Saída: data/sondagem2.json."""
from __future__ import annotations

import csv
import io
import json
import re
import time
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urljoin

import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "sondagem2.json"
NAV = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def log(*a):
    print(*a, flush=True)


def get(url, timeout=180, **kw):
    for t in range(3):
        try:
            return requests.get(url, headers=NAV, timeout=timeout, **kw)
        except requests.RequestException as e:
            log("  erro", e)
            time.sleep(5 * (t + 1))
    return None


def ler_csv(conteudo: bytes):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(txt[:5000], delimiters=";,|\t").delimiter
    except csv.Error:
        sep = ";"
    return list(csv.DictReader(io.StringIO(txt), delimiter=sep))


def contagem(linhas, campo, f=lambda x: x, n=40):
    return Counter(f((r.get(campo) or "").strip()) for r in linhas).most_common(n)


def main():
    res = {"gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

    # ---------- São Paulo ----------
    sp = []
    for u in [
        "https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501",
        "https://prefeitura.sp.gov.br/fazenda/w/acesso_a_informacao/31501",
        "https://capital.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501",
        "https://www.prefeitura.sp.gov.br/cidade/secretarias/fazenda/acesso_a_informacao/index.php?p=31501",
        "http://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501",
    ]:
        r = get(u)
        t = {"url": u, "status": r.status_code if r is not None else None}
        if r is not None:
            t["final"] = r.url
            t["server"] = r.headers.get("server")
            links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|ods|zip|csv)[^"]*)"', r.text, flags=re.I)))
            t["links"] = [urljoin(r.url, l.replace("&amp;", "&")) for l in links][:60]
            if not links:
                t["inicio"] = r.text[:600]
        sp.append(t)
        log("SP", t["url"], t["status"], len(t.get("links", [])))
    res["sao_paulo"] = sp
    links = next((t["links"] for t in sp if t.get("links")), [])
    alvo = [l for l in links if "2026" in l and ".xlsx" in l.lower()]
    if alvo:
        r = get(alvo[0], timeout=600)
        info = {"url": alvo[0], "status": r.status_code if r is not None else None,
                "bytes": len(r.content) if r is not None else 0}
        if r is not None and r.ok:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True, data_only=True)
            abas = {}
            for ws in wb.worksheets:
                prim = []
                n = 0
                for row in ws.iter_rows(values_only=True):
                    n += 1
                    if len(prim) < 4:
                        prim.append([None if v is None else str(v)[:50] for v in row[:45]])
                abas[ws.title] = {"linhas": n, "primeiras": prim}
            info["abas"] = abas
        res["sao_paulo_arquivo"] = info

    # ---------- Rio ----------
    rio = {}
    r = get("https://www.data.rio/api/search/v1/collections/all/items?q=ITBI&limit=50")
    if r is not None and r.ok:
        itens = []
        for f in r.json().get("features", []):
            p = f.get("properties", {})
            itens.append({"id": f.get("id"), "titulo": p.get("title"), "tipo": p.get("type"),
                          "url": p.get("url"), "resumo": (p.get("snippet") or "")[:200],
                          "modificado": p.get("modified")})
        rio["itens_hub"] = itens
    pg = get("https://fazenda.prefeitura.rio/itbi-valores-medios-por-m2-de-transacoes-imobiliarias-por-trecho-de-logradouro")
    if pg is not None:
        rio["pagina_smf_status"] = pg.status_code
        rio["pagina_smf_links"] = sorted(set(urljoin(pg.url, l) for l in re.findall(
            r'href="([^"]+)"', pg.text) if re.search(r"\.(xlsx|xls|csv|zip|ods|pdf)|download|arquivo|itbi", l, re.I)))[:80]
        rio["pagina_smf_texto"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", pg.text))[:3000]
    # serviços ArcGIS: pega o primeiro registro de cada camada citada no hub
    servicos = []
    for it in rio.get("itens_hub", []):
        u = it.get("url") or ""
        if "FeatureServer" in u or "MapServer" in u:
            q = u.rstrip("/")
            if not re.search(r"/\d+$", q):
                q += "/0"
            rr = get(q + "/query?where=1%3D1&outFields=*&resultRecordCount=3&f=json")
            cnt = get(q + "/query?where=1%3D1&returnCountOnly=true&f=json")
            servicos.append({"url": q, "titulo": it["titulo"],
                             "amostra": (rr.text[:3000] if rr is not None else None),
                             "contagem": (cnt.text[:200] if cnt is not None else None)})
    rio["servicos"] = servicos
    res["rio"] = rio

    # ---------- BH: lista de arquivos mensais ----------
    r = get("https://dados.pbh.gov.br/api/3/action/package_show?id=itbi-relatorios")
    if r is not None and r.ok:
        res["bh_recursos"] = [(x.get("name"), x.get("url")) for x in r.json()["result"]["resources"]]
    # ---------- Recife: anos ----------
    r = get("https://dados.recife.pe.gov.br/api/3/action/package_show?id=imposto-sobre-transmissao-de-bens-imoveis-itbi")
    if r is not None and r.ok:
        recs = r.json()["result"]["resources"]
        res["recife_recursos"] = [(x.get("name"), x.get("url"), x.get("last_modified")) for x in recs]
        dic = [x for x in recs if "dicion" in (x.get("name") or "").lower() or x["url"].endswith(".json")]
        if dic:
            d = get(dic[0]["url"])
            res["recife_dicionario"] = d.text[:6000] if d is not None else None
        a25 = [x for x in recs if "2025" in (x.get("name") or "") + x["url"]]
        if a25:
            d = get(a25[0]["url"], timeout=300)
            if d is not None and d.ok:
                L = ler_csv(d.content)
                res["recife_2025"] = {"linhas": len(L), "tipo_imovel": contagem(L, "tipo_imovel"),
                                      "mes": contagem(L, "data_transacao", lambda x: x[:7]),
                                      "tipo_ocupacao": contagem(L, "tipo_ocupacao")}
    # ---------- Fortaleza: cobertura ----------
    r = get("https://dados.fortaleza.ce.gov.br/dataset/32608ed2-e4ad-4cd2-b7bc-deea35dd189f/resource/"
            "46324d49-9809-4d32-8e5c-b4b570f067ce/download/dados_abertos_itbi_transacoes_imobiliarias.csv", timeout=600)
    if r is not None and r.ok:
        L = ler_csv(r.content)
        res["fortaleza"] = {"linhas": len(L), "exercicio": contagem(L, "EXERCICIO"),
                            "ano_mes": sorted(contagem(L, "ANO_MES_DEBITO", n=200)),
                            "tipo_uso": contagem(L, "TIPO_USO_IMOVEL"), "padrao": contagem(L, "PADRAO_CONSTRUCAO"),
                            "data_transacao_vazia": sum(1 for x in L if not (x.get("DATA_DA_TRANSACAO_ITBI") or "").strip()),
                            "versao": contagem(L, "VERSAO"), "bairros": len({x.get("BAIRRO") for x in L})}
    # ---------- Porto Alegre ----------
    r = get("https://dadosabertos.poa.br/api/3/action/package_show?id=itbi")
    if r is not None and r.ok:
        recs = r.json()["result"]["resources"]
        res["poa_recursos"] = [(x.get("name"), x.get("url"), x.get("last_modified")) for x in recs]
        z26 = [x for x in recs if "2026" in x["url"]]
        if z26:
            d = get(z26[0]["url"], timeout=300)
            z = zipfile.ZipFile(io.BytesIO(d.content))
            L = ler_csv(z.read(z.namelist()[0]))
            res["poa_2026"] = {"linhas": len(L), "situacao": contagem(L, "situacao"),
                               "finalidade": contagem(L, "finalidade_construcao"),
                               "mes_estimativa": sorted(contagem(L, "data_estimativa", lambda x: x[:7], n=100)),
                               "mes_pagamento": sorted(contagem(L, "data_pagamento", lambda x: x[:7], n=100)),
                               "perc": contagem(L, "perc_transmitido", n=10)}

    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log("ok")


if __name__ == "__main__":
    main()
