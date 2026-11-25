"""O que tem em volta de cada bairro: pontos do OpenStreetMap por cidade.

Em vez de consultar o Overpass (que vive sobrecarregado), baixa o recorte regional do Brasil no
Geofabrik (.osm.pbf), filtra só as etiquetas que interessam com o osmium e separa os pontos de cada
cidade pela área coberta pelos contornos dos bairros (data/mapas/<cidade>.json).

Salva em data/entorno/<cidade>.json as coordenadas de cada categoria e os pontos com nome de bairro
(place=suburb/neighbourhood/quarter), usados como centro dos bairros sem contorno (caso de São Paulo).
Baixa de novo quando o arquivo tem mais de 60 dias ou com FORCAR=1. © colaboradores do OpenStreetMap (ODbL).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atualizar import log  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "data" / "entorno"
MAPAS = RAIZ / "data" / "mapas"
TMP = Path(os.environ.get("RUNNER_TEMP", "/tmp"))
REGIAO = {"sao-paulo": "sudeste", "rio-de-janeiro": "sudeste", "belo-horizonte": "sudeste",
          "fortaleza": "nordeste", "recife": "nordeste", "porto-alegre": "sul"}
URL = "https://download.geofabrik.de/south-america/brazil/{}-latest.osm.pbf"
FILTRO = [
    "nwr/amenity=school,kindergarten,hospital,clinic,pharmacy,restaurant,cafe,bar,pub,fast_food,bus_station",
    "nwr/healthcare=centre", "nwr/shop=supermarket,wholesale,mall", "nwr/leisure=park",
    "nwr/railway=station,halt", "nwr/public_transport=station", "n/highway=bus_stop",
    "n/place=suburb,neighbourhood,quarter",
]
CATS = ["escolas", "saude", "mercados", "farmacias", "shoppings", "parques", "restaurantes", "estacoes", "onibus"]


def categoria(t: dict) -> str | None:
    a, sh = t.get("amenity"), t.get("shop")
    if a in ("school", "kindergarten"):
        return "escolas"
    if a in ("hospital", "clinic") or t.get("healthcare") == "centre":
        return "saude"
    if sh in ("supermarket", "wholesale"):
        return "mercados"
    if a == "pharmacy":
        return "farmacias"
    if sh == "mall":
        return "shoppings"
    if t.get("leisure") == "park":
        return "parques"
    if a in ("restaurant", "cafe", "bar", "pub", "fast_food"):
        return "restaurantes"
    # metrô, trem, VLT e estações de BRT; rodoviárias e terminais de ônibus comuns ficam de fora
    if (t.get("railway") in ("station", "halt") and t.get("station") != "funicular") \
            or (t.get("public_transport") == "station" and t.get("bus") == "yes" and a != "bus_station"
                and ("brt" in (t.get("name", "") + t.get("network", "")).lower() or t.get("highway") == "bus_stop"
                     or "move" in t.get("network", "").lower())):
        return "estacoes"
    if t.get("highway") == "bus_stop":
        return "onibus"
    return None


def baixar(regiao: str) -> Path:
    destino = TMP / f"{regiao}.osm.pbf"
    if destino.exists():
        return destino
    log(f"  {time.strftime('%H:%M:%S')} baixando {regiao}")
    with requests.get(URL.format(regiao), stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(destino, "wb") as f:
            for parte in r.iter_content(1 << 20):
                f.write(parte)
    log(f"  {time.strftime('%H:%M:%S')} {destino.stat().st_size / 1e6:.0f} MB")
    return destino


def pontos_da_regiao(regiao: str):
    pbf = baixar(regiao)
    filt = TMP / f"{regiao}-filtrado.osm.pbf"
    seq = TMP / f"{regiao}.geojsonseq"
    subprocess.run(["osmium", "tags-filter", str(pbf), *FILTRO, "-o", str(filt), "--overwrite"], check=True)
    subprocess.run(["osmium", "export", str(filt), "-f", "geojsonseq", "-o", str(seq), "--overwrite"], check=True)
    log(f"  {time.strftime('%H:%M:%S')} filtrado e exportado")
    out = []
    with open(seq, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip().lstrip("\x1e")
            if not linha:
                continue
            ft = json.loads(linha)
            t = ft.get("properties") or {}
            try:
                g = ft["geometry"]
                if g["type"] == "Point":
                    x, y = g["coordinates"]
                else:
                    p = shape(g).representative_point()
                    x, y = p.x, p.y
            except Exception:  # noqa: BLE001
                continue
            out.append((x, y, t))
    return out


def caixa(slug):
    mp = json.loads((MAPAS / f"{slug}.json").read_text(encoding="utf-8"))
    xs = [x for b in mp["bairros"] for a in b["p"] for x, _ in a]
    ys = [y for b in mp["bairros"] for a in b["p"] for _, y in a]
    m = 0.02
    return min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    forcar = os.environ.get("FORCAR") == "1"
    pendentes = []
    for slug in REGIAO:
        arq = PASTA / f"{slug}.json"
        if not (MAPAS / f"{slug}.json").exists():
            continue
        if arq.exists() and not forcar:
            ant = json.loads(arq.read_text(encoding="utf-8"))
            idade = (dt.date.today() - dt.date.fromisoformat(ant.get("baixado_em", "2000-01-01"))).days
            if idade < 60 and all(c in ant.get("cat", {}) for c in CATS) and ant.get("lugares"):
                continue
        pendentes.append(slug)
    for regiao in sorted({REGIAO[s] for s in pendentes}):
        log(f"== {regiao}")
        pts = pontos_da_regiao(regiao)
        log(f"  {len(pts)} pontos na região")
        for slug in [s for s in pendentes if REGIAO[s] == regiao]:
            x0, y0, x1, y1 = caixa(slug)
            res = {"fonte": "OpenStreetMap (Geofabrik)", "baixado_em": dt.date.today().isoformat(),
                   "cat": {c: [] for c in CATS}, "lugares": []}
            for x, y, t in pts:
                if not (x0 <= x <= x1 and y0 <= y <= y1):
                    continue
                if t.get("place") in ("suburb", "neighbourhood", "quarter") and t.get("name"):
                    res["lugares"].append([round(x, 5), round(y, 5), t["name"]])
                    continue
                c = categoria(t)
                if c:
                    p = [round(x, 5), round(y, 5)]
                    if c in ("estacoes", "shoppings"):
                        p.append(t.get("name", ""))
                    res["cat"][c].append(p)
            (PASTA / f"{slug}.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            log(f"  {slug}: " + ", ".join(f"{c} {len(v)}" for c, v in res["cat"].items()) + f", lugares {len(res['lugares'])}")


if __name__ == "__main__":
    main()
