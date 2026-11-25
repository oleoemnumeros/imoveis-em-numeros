"""Contornos dos bairros de cada cidade, do OpenStreetMap (via Overpass), para os mapas do site.

Baixa os limites administrativos de nível 9 e 10 dentro do município (pelo código Wikidata),
escolhe o nível que mais combina com os nomes de bairro das bases do ITBI, simplifica os
polígonos e salva em data/mapas/<cidade>.json. Só baixa de novo se o arquivo não existir
(ou com FORCAR=1). Dados do mapa: © colaboradores do OpenStreetMap (ODbL).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from atualizar import chave_bairro, log  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "data" / "mapas"
DADOS = RAIZ / "data" / "cidades"
WIKIDATA = {"sao-paulo": "Q174", "rio-de-janeiro": "Q8678", "belo-horizonte": "Q42800",
            "fortaleza": "Q43463", "recife": "Q48344", "porto-alegre": "Q40269"}
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
UA = {"User-Agent": "ImoveisEmNumeros/1.0 (+https://imoveisemnumeros.com.br)"}


def overpass(q: str) -> dict:
    ult = None
    for t in range(4):
        url = OVERPASS[t % len(OVERPASS)]
        log(f"  {time.strftime('%H:%M:%S')} consultando {url}")
        try:
            r = requests.post(url, data={"data": q}, headers=UA, timeout=200)
            log(f"  {time.strftime('%H:%M:%S')} HTTP {r.status_code}, {len(r.content)} bytes")
            if r.status_code == 200:
                return r.json()
            ult = RuntimeError(f"{url} HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException as e:
            ult = e
        log(f"  overpass falhou ({ult}); nova tentativa")
        time.sleep(15)
    raise ult


def poligonos(elementos):
    """Relações de fronteira com geometria (out geom) -> {nome: shapely}."""
    import osm2geojson
    gj = osm2geojson.json2geojson({"elements": elementos})
    out = {}
    for f in gj["features"]:
        p = f.get("properties", {})
        tags = p.get("tags", {})
        nome = tags.get("name")
        if not nome or p.get("type") != "relation":
            continue
        try:
            g = shape(f["geometry"])
            if not g.is_valid:
                g = g.buffer(0)
        except Exception:  # noqa: BLE001
            continue
        if g.geom_type not in ("Polygon", "MultiPolygon") or g.is_empty:
            continue
        out[nome] = unary_union([out[nome], g]) if nome in out else g
    return out


def anel(coords):
    return [[round(x, 5), round(y, 5)] for x, y in coords]


def main():
    PASTA.mkdir(parents=True, exist_ok=True)
    forcar = os.environ.get("FORCAR") == "1"
    dbg = {}
    for slug, qid in WIKIDATA.items():
        arq = PASTA / f"{slug}.json"
        if arq.exists() and not forcar:
            continue
        log(f"== {slug}")
        try:
            els = []
            for nivel in ("10", "9"):
                q = (f'[out:json][timeout:180];area["wikidata"="{qid}"]->.a;'
                     f'relation(area.a)["boundary"="administrative"]["admin_level"="{nivel}"];out geom;')
                novos = overpass(q)["elements"]
                log(f"  nível {nivel}: {len(novos)} relações")
                els += novos
                if nivel == "10" and len(novos) >= 30:
                    break
            nomes_itbi = set()
            f = DADOS / f"{slug}.json"
            if f.exists():
                nomes_itbi = set(json.loads(f.read_text(encoding="utf-8"))["bairros"].keys())
            por_nivel = {}
            for nivel in ("9", "10"):
                sel = [e for e in els if e.get("tags", {}).get("admin_level") == nivel]
                if sel:
                    por_nivel[nivel] = poligonos(sel)
            info = {}
            melhor, melhor_n = None, -1
            for nivel, pol in por_nivel.items():
                ks = {chave_bairro(n) for n in pol}
                n = len(ks & nomes_itbi)
                info[nivel] = {"poligonos": len(pol), "combinam": n}
                if n > melhor_n or (n == melhor_n and len(pol) > len(por_nivel.get(melhor, {}))):
                    melhor, melhor_n = nivel, n
            if not melhor:
                raise RuntimeError("nenhum limite de bairro no OpenStreetMap")
            pol = por_nivel[melhor]
            saida = []
            for nome, g in pol.items():
                g = g.simplify(0.00025, preserve_topology=True)
                partes = [g] if g.geom_type == "Polygon" else list(g.geoms)
                aneis = [anel(p.exterior.coords) for p in partes if p.area > 1e-7]
                if aneis:
                    c = g.representative_point()
                    saida.append({"nome": nome, "k": chave_bairro(nome), "p": aneis, "c": [round(c.x, 5), round(c.y, 5)]})
            log(f"  {time.strftime('%H:%M:%S')} gravando")
            arq.write_text(json.dumps({"nivel": int(melhor), "fonte": "OpenStreetMap", "bairros": saida},
                                      ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            info["escolhido"] = melhor
            info["sem_par_no_itbi"] = sorted({b["k"] for b in saida} - nomes_itbi)[:80]
            dbg[slug] = info
            log(f"  nível {melhor}: {len(saida)} bairros, {melhor_n} combinam com o ITBI")
        except Exception as e:  # noqa: BLE001
            log(f"  ERRO {slug}: {e!r}")
            dbg[slug] = {"erro": repr(e)[:400]}
        time.sleep(5)
    if dbg:
        (PASTA / "debug.json").write_text(json.dumps(dbg, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
