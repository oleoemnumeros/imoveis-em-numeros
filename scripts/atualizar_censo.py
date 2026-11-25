"""Censo 2022 (IBGE) por setor censitário, só para as cidades do site: moradores, domicílios e renda
dos responsáveis pelo domicílio (divulgada em 2025/2026), com um ponto (lon, lat) de cada setor para
somar os setores dentro de cada bairro.

Saída: data/censo/<slug>.json
  {"fonte": ..., "baixado_em": ..., "campos": [...], "setores": [[lon, lat, pessoas, domicilios,
   responsaveis_com_renda, renda_media, renda_mediana], ...]}
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "censo"
H = {"User-Agent": "Mozilla/5.0 (compatible; ImoveisEmNumeros/1.0)"}
F = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
G = ("https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
     "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/setores/gpkg/UF/")
RENDA = F + "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip"
BASICO = F + "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/Agregados_por_setores_basico_BR_20260520.zip"

CIDADES = {  # slug: (código IBGE do município, UF)
    "sao-paulo": ("3550308", "SP"),
    "rio-de-janeiro": ("3304557", "RJ"),
    "belo-horizonte": ("3106200", "MG"),
    "fortaleza": ("2304400", "CE"),
    "recife": ("2611606", "PE"),
    "porto-alegre": ("4314902", "RS"),
}


def num(s):
    s = (s or "").strip().replace('"', "")
    if s in ("", ".", "X", "-"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def ler_zip_csv(url, filtro):
    print("baixando", url.rsplit("/", 1)[-1], flush=True)
    r = requests.get(url, headers=H, timeout=900)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    nome = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
    with z.open(nome) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, encoding="latin-1"), delimiter=";")
        cab = [c.strip().upper() for c in next(rd)]
        for ln in rd:
            if ln and filtro(ln[0]):
                yield dict(zip(cab, ln))


def pontos_setores(uf, mun):
    """Ponto representativo de cada setor do município (lon, lat)."""
    import pyogrio
    url = f"{G}{uf}/{uf}_setores_CD2022.gpkg"
    print("baixando malha", uf, flush=True)
    with tempfile.NamedTemporaryFile(suffix=".gpkg", delete=False) as tmp:
        with requests.get(url, headers=H, timeout=1800, stream=True) as r:
            r.raise_for_status()
            for bloco in r.iter_content(1 << 20):
                tmp.write(bloco)
        caminho = tmp.name
    info = pyogrio.read_info(caminho)
    campos = list(info["fields"])
    cs = next(c for c in campos if c.upper() == "CD_SETOR")
    gdf = pyogrio.read_dataframe(caminho, columns=[cs], where=f"{cs} LIKE '{mun}%'")
    gdf = gdf.to_crs(4326) if gdf.crs and gdf.crs.to_epsg() != 4326 else gdf
    pts = gdf.geometry.representative_point()
    Path(caminho).unlink()
    return {str(c): (round(p.x, 5), round(p.y, 5)) for c, p in zip(gdf[cs], pts)}


def main():
    alvo = [a for a in sys.argv[1:] if a in CIDADES] or list(CIDADES)
    muns = {CIDADES[s][0]: s for s in alvo}
    filtro = lambda cd: cd.strip('"')[:7] in muns
    renda = {}
    for d in ler_zip_csv(RENDA, filtro):
        renda[d["CD_SETOR"].strip('"')] = (num(d.get("V06001")), num(d.get("V06004")), num(d.get("V06006")))
    print("setores com renda:", len(renda), flush=True)
    basico = {}
    for d in ler_zip_csv(BASICO, filtro):
        basico[d["CD_SETOR"].strip('"')] = (num(d.get("V0001")), num(d.get("V0002")))
    print("setores no básico:", len(basico), flush=True)
    SAIDA.mkdir(parents=True, exist_ok=True)
    for s in alvo:
        mun, uf = CIDADES[s]
        pts = pontos_setores(uf, mun)
        linhas = []
        for cd, (lon, lat) in pts.items():
            pe, dom = basico.get(cd, (None, None))
            rr, rm, rmed = renda.get(cd, (None, None, None))
            if not pe:
                continue
            linhas.append([lon, lat, int(pe), int(dom or 0), int(rr or 0), rm, rmed])
        (SAIDA / f"{s}.json").write_text(json.dumps({
            "fonte": "IBGE, Censo Demográfico 2022: Agregados por Setores Censitários (básico e rendimento do responsável)",
            "baixado_em": dt.date.today().isoformat(),
            "campos": ["lon", "lat", "pessoas", "domicilios", "responsaveis_com_renda", "renda_media", "renda_mediana"],
            "setores": linhas}, ensure_ascii=False, separators=(",", ":")))
        print(s, len(pts), "setores na malha,", len(linhas), "com moradores", flush=True)


if __name__ == "__main__":
    main()
