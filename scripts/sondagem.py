"""Sondagem das bases de ITBI (Imóveis em Números).

Roda no GitHub Actions (de lá dá para baixar dos portais das prefeituras).
Para cada cidade: descobre os arquivos publicados, baixa o mais recente,
lê o cabeçalho, conta as linhas e guarda 3 linhas de exemplo.
Resultado em data/sondagem.json, para decidirmos o que entra no site.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "sondagem.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; ImoveisEmNumeros/1.0; +https://imoveisemnumeros.com.br)"}

CKAN = {
    "belo-horizonte": ("https://dados.pbh.gov.br", ["itbi-relatorios"], "itbi"),
    "recife": ("https://dados.recife.pe.gov.br", ["imposto-sobre-transmissao-de-bens-imoveis-itbi"], "itbi"),
    "fortaleza": ("https://dados.fortaleza.ce.gov.br", ["dados_abertos_itbi_transacoes_imobiliarias"], "itbi"),
    "porto-alegre": ("https://dadosabertos.poa.br", [], "itbi"),
    "vitoria": ("https://dados.vitoria.es.gov.br", [], "itbi"),
    "rio-de-janeiro-ckan": ("https://www.data.rio", [], "itbi"),
}
SP_PAGINA = "https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501"
RIO_HUB = [
    "https://www.data.rio/api/search/v1/collections/all/items?q=ITBI&limit=50",
    "https://www.data.rio/api/v3/datasets?q=ITBI",
    "https://hub.arcgis.com/api/v3/datasets?q=ITBI%20Rio%20de%20Janeiro",
]
VITORIA_EXTRA = [
    "https://transparencia.vitoria.es.gov.br",
    "https://dadosabertos.vitoria.es.gov.br/api/3/action/package_search?q=itbi",
]


def log(*a):
    print(*a, flush=True)


def get(url, timeout=120, **kw):
    ult = None
    for t in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=timeout, **kw)
            return r
        except requests.RequestException as e:
            ult = e
            time.sleep(5 * (t + 1))
    raise ult


def ckan(base, ids, busca):
    pacotes = []
    for i in ids:
        r = get(f"{base}/api/3/action/package_show?id={i}")
        if r.ok and r.json().get("success"):
            pacotes.append(r.json()["result"])
    if not pacotes:
        r = get(f"{base}/api/3/action/package_search?q={busca}&rows=20")
        r.raise_for_status()
        pacotes = r.json()["result"]["results"]
    out = []
    for p in pacotes:
        recs = []
        for x in p.get("resources", []):
            recs.append({
                "nome": x.get("name"), "formato": x.get("format"), "url": x.get("url"),
                "criado": x.get("created"), "modificado": x.get("last_modified") or x.get("metadata_modified"),
                "tamanho": x.get("size"),
            })
        out.append({"pacote": p.get("name"), "titulo": p.get("title"),
                    "modificado": p.get("metadata_modified"), "recursos": recs})
    return out


def amostra(conteudo: bytes, nome: str):
    """Cabeçalho, nº de linhas e 3 linhas de exemplo de um CSV/XLSX/ZIP."""
    nome = nome.lower()
    if conteudo[:2] == b"PK" and not nome.endswith((".xlsx", ".ods")):
        z = zipfile.ZipFile(io.BytesIO(conteudo))
        nomes = z.namelist()
        dentro = [n for n in nomes if n.lower().endswith((".csv", ".xlsx", ".txt"))]
        if not dentro:
            return {"zip": nomes}
        res = amostra(z.read(dentro[0]), dentro[0])
        res["zip"] = nomes
        return res
    if nome.endswith(".xlsx") or (conteudo[:2] == b"PK"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        abas = {}
        for ws in wb.worksheets[:15]:
            linhas = []
            n = 0
            for row in ws.iter_rows(values_only=True):
                n += 1
                if len(linhas) < 6:
                    linhas.append([None if v is None else str(v)[:60] for v in row[:40]])
            abas[ws.title] = {"linhas": n, "primeiras": linhas}
        return {"tipo": "xlsx", "abas": abas}
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = conteudo.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    amostra_txt = txt[:5000]
    try:
        dial = csv.Sniffer().sniff(amostra_txt, delimiters=";,|\t")
        sep = dial.delimiter
    except csv.Error:
        sep = ";"
    leitor = csv.reader(io.StringIO(txt), delimiter=sep)
    cab = next(leitor, [])
    ex = []
    n = 0
    for row in leitor:
        n += 1
        if len(ex) < 3:
            ex.append([c[:60] for c in row])
    return {"tipo": "csv", "encoding": enc, "separador": sep, "colunas": cab, "linhas": n, "exemplos": ex}


def baixar_amostra(url, nome=""):
    r = get(url, timeout=300)
    info = {"url": url, "status": r.status_code, "bytes": len(r.content),
            "content_type": r.headers.get("content-type")}
    if r.ok and len(r.content) > 200:
        try:
            info.update(amostra(r.content, nome or url))
        except Exception as e:  # noqa: BLE001
            info["erro_leitura"] = repr(e)[:300]
            info["inicio"] = r.content[:300].decode("latin-1", "replace")
    else:
        info["inicio"] = r.content[:300].decode("latin-1", "replace")
    return info


def mais_recente(recs):
    dados = [x for x in recs if (x.get("formato") or "").upper() in ("CSV", "XLSX", "XLS", "ZIP", "")
             and x.get("url") and not (x.get("url") or "").lower().endswith(".pdf")]
    if not dados:
        return None

    def chave(x):
        return (x.get("modificado") or x.get("criado") or "", x.get("nome") or "")
    return sorted(dados, key=chave)[-1]


def main():
    res = {"gerado_em": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cidades": {}}

    for cidade, (base, ids, busca) in CKAN.items():
        log(f"== {cidade}")
        c = {"base": base}
        try:
            pac = ckan(base, ids, busca)
            c["pacotes"] = [{k: v for k, v in p.items() if k != "recursos"} | {"n_recursos": len(p["recursos"]),
                            "recursos": p["recursos"][-60:]} for p in pac]
            itbi = [p for p in pac if "itbi" in ((p.get("pacote") or "") + (p.get("titulo") or "")).lower()]
            alvo = itbi[0] if itbi else (pac[0] if pac else None)
            if alvo:
                r = mais_recente(alvo["recursos"])
                if r:
                    log("   baixando", r["url"])
                    c["amostra_recente"] = baixar_amostra(r["url"], r.get("nome") or "")
                # um arquivo antigo também, para ver se as colunas mudaram
                antigos = [x for x in alvo["recursos"] if x is not r and x.get("url")
                           and not x["url"].lower().endswith(".pdf")]
                if antigos:
                    a = sorted(antigos, key=lambda x: x.get("modificado") or "")[0]
                    log("   baixando antigo", a["url"])
                    c["amostra_antiga"] = baixar_amostra(a["url"], a.get("nome") or "")
        except Exception as e:  # noqa: BLE001
            c["erro"] = repr(e)[:400]
        res["cidades"][cidade] = c

    log("== sao-paulo")
    c = {"pagina": SP_PAGINA}
    try:
        r = get(SP_PAGINA)
        c["status_pagina"] = r.status_code
        links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|ods|zip|csv)[^"]*)"', r.text, flags=re.I)))
        links = [urljoin(SP_PAGINA, l.replace("&amp;", "&")) for l in links]
        c["links"] = links
        x26 = [l for l in links if "2026" in l and "xlsx" in l.lower()] or [l for l in links if "xlsx" in l.lower()]
        if x26:
            log("   baixando", x26[0])
            c["amostra_recente"] = baixar_amostra(x26[0], "a.xlsx")
    except Exception as e:  # noqa: BLE001
        c["erro"] = repr(e)[:400]
    res["cidades"]["sao-paulo"] = c

    log("== rio-de-janeiro (hub)")
    c = {"tentativas": []}
    for u in RIO_HUB:
        try:
            r = get(u)
            t = {"url": u, "status": r.status_code}
            try:
                j = r.json()
                t["resposta"] = json.dumps(j, ensure_ascii=False)[:6000]
            except ValueError:
                t["inicio"] = r.text[:800]
            c["tentativas"].append(t)
        except Exception as e:  # noqa: BLE001
            c["tentativas"].append({"url": u, "erro": repr(e)[:300]})
    res["cidades"]["rio-de-janeiro-hub"] = c

    log("== vitoria (extra)")
    c = {"tentativas": []}
    for u in VITORIA_EXTRA:
        try:
            r = get(u)
            c["tentativas"].append({"url": u, "status": r.status_code, "inicio": r.text[:1500]})
        except Exception as e:  # noqa: BLE001
            c["tentativas"].append({"url": u, "erro": repr(e)[:300]})
    res["cidades"]["vitoria-extra"] = c

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    log("ok ->", SAIDA)


if __name__ == "__main__":
    sys.exit(main())
