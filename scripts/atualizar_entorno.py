"""O que tem em volta de cada bairro: pontos do OpenStreetMap por cidade (via Overpass).

Salva em data/entorno/<cidade>.json só as coordenadas de cada categoria e os pontos com nome de
bairro (place=suburb/neighbourhood/quarter), usados como centro dos bairros que não têm contorno
(caso de São Paulo, onde o mapa é por distrito). Baixa de novo quando o arquivo tem mais de 60 dias
ou com FORCAR=1. Dados: © colaboradores do OpenStreetMap (ODbL).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atualizar import log  # noqa: E402
from atualizar_mapas import WIKIDATA, overpass  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "data" / "entorno"

# categoria: filtros Overpass (nwr = nó, via ou relação; "out center" dá um ponto para cada)
CATEGORIAS = {
    "escolas": ['nwr["amenity"="school"]', 'nwr["amenity"="kindergarten"]'],
    "saude": ['nwr["amenity"="hospital"]', 'nwr["amenity"="clinic"]', 'nwr["healthcare"="centre"]'],
    "mercados": ['nwr["shop"="supermarket"]', 'nwr["shop"="wholesale"]'],
    "farmacias": ['nwr["amenity"="pharmacy"]'],
    "shoppings": ['nwr["shop"="mall"]'],
    "parques": ['nwr["leisure"="park"]'],
    "restaurantes": ['nwr["amenity"~"^(restaurant|cafe|bar|pub|fast_food)$"]'],
    "estacoes": ['nwr["railway"~"^(station|halt)$"]["station"!="funicular"]',
                 'nwr["public_transport"="station"]["bus"="yes"]', 'nwr["amenity"="bus_station"]'],
    "onibus": ['node["highway"="bus_stop"]'],
}


def pontos(qid: str, filtros: list[str], com_nome=False):
    corpo = "".join(f"{f}(area.a);" for f in filtros)
    q = f'[out:json][timeout:180];area["wikidata"="{qid}"]->.a;({corpo});out center tags;'
    els = overpass(q)["elements"]
    out = []
    for e in els:
        lat = e.get("lat") or (e.get("center") or {}).get("lat")
        lon = e.get("lon") or (e.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        p = [round(lon, 5), round(lat, 5)]
        if com_nome:
            p.append((e.get("tags") or {}).get("name", ""))
        out.append(p)
    return out


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    forcar = os.environ.get("FORCAR") == "1"
    for slug, qid in WIKIDATA.items():
        arq = PASTA / f"{slug}.json"
        if arq.exists() and not forcar:
            antigo = json.loads(arq.read_text(encoding="utf-8"))
            idade = (dt.date.today() - dt.date.fromisoformat(antigo.get("baixado_em", "2000-01-01"))).days
            completo = all(c in antigo.get("cat", {}) for c in CATEGORIAS) and antigo.get("lugares")
            if idade < 60 and completo:
                continue
        log(f"== {slug}")
        res = {"fonte": "OpenStreetMap", "baixado_em": dt.date.today().isoformat(), "cat": {}, "faltam": []}
        if arq.exists():  # aproveita o que já veio numa rodada anterior
            ant = json.loads(arq.read_text(encoding="utf-8"))
            res["cat"] = ant.get("cat", {})
            if ant.get("lugares"):
                res["lugares"] = ant["lugares"]
        for cat, filtros in CATEGORIAS.items():
            if cat in res["cat"] and not forcar:
                continue
            try:
                com_nome = cat in ("estacoes", "shoppings")
                res["cat"][cat] = pontos(qid, filtros, com_nome)
                log(f"  {cat}: {len(res['cat'][cat])}")
                arq.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                log(f"  ERRO {cat}: {e!r}")
                res["faltam"].append(cat)
            time.sleep(3)
        try:
            if res.get("lugares") and not forcar:
                raise StopIteration
            res["lugares"] = pontos(qid, ['node["place"~"^(suburb|neighbourhood|quarter)$"]'], True)
            log(f"  lugares: {len(res['lugares'])}")
        except StopIteration:
            pass
        except Exception as e:  # noqa: BLE001
            log(f"  ERRO lugares: {e!r}")
            res["faltam"].append("lugares")
        arq.write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
