"""Robô do Imóveis em Números.

Baixa as bases de ITBI publicadas pelas prefeituras, filtra as compras de imóveis
residenciais (apartamentos e casas) e guarda só números agregados por bairro e mês em
data/cidades/<cidade>.json. Nenhum endereço fica salvo no repositório.

Cidades e fontes:
  São Paulo       Secretaria da Fazenda, guias de ITBI pagas (xlsx anual, abas mensais)
  Belo Horizonte  Portal de Dados Abertos da PBH, ITBI Relatórios (csv mensal)
  Fortaleza       Portal de Dados Abertos de Fortaleza, ITBI (csv único)
  Porto Alegre    Dados Abertos POA, ITBI (zip anual)
  Recife          Dados Abertos Recife, ITBI (csv anual)
  Rio de Janeiro  Fazenda do Rio via data.rio (já agregado por bairro e mês)
"""
from __future__ import annotations

import csv
import datetime as dt
import itertools
import io
import json
import math
import re
import statistics
import sys
import time
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urljoin

import requests

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "data" / "cidades"
DEBUG = RAIZ / "data" / "debug.json"
ANO_INICIO = 2022
NAV = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}
MESES_PT = {"JAN": 1, "JANEIRO": 1, "FEV": 2, "FEVEREIRO": 2, "MAR": 3, "MARCO": 3, "MARÇO": 3, "ABR": 4,
            "ABRIL": 4, "MAI": 5, "MAIO": 5, "JUN": 6, "JUNHO": 6, "JUL": 7, "JULHO": 7, "AGO": 8, "AGOSTO": 8,
            "SET": 9, "SETEMBRO": 9, "OUT": 10, "OUTUBRO": 10, "NOV": 11, "NOVEMBRO": 11, "DEZ": 12, "DEZEMBRO": 12}

DBG: dict = {}


def log(*a):
    print(*a, flush=True)


def get(url, timeout=300, tentativas=4, **kw):
    ult = None
    for t in range(tentativas):
        try:
            r = requests.get(url, headers=NAV, timeout=timeout, **kw)
            if r.status_code == 200:
                return r
            ult = RuntimeError(f"{url} -> HTTP {r.status_code}")
        except requests.RequestException as e:
            ult = e
        log(f"  falhou ({ult}); nova tentativa")
        time.sleep(8 * (t + 1))
    raise ult


def num(s) -> float | None:
    """Número no formato brasileiro ou americano, como texto ou número."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s) if not (isinstance(s, float) and math.isnan(s)) else None
    s = str(s).strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def chave(s: str) -> str:
    s = sem_acento((s or "").upper())
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


ABREV = {"JD": "JARDIM", "JDM": "JARDIM", "VL": "VILA", "V": "VILA", "PQ": "PARQUE", "PRQ": "PARQUE",
         "CID": "CIDADE", "CJ": "CONJUNTO", "CONJ": "CONJUNTO", "STO": "SANTO", "STA": "SANTA",
         "SAO": "SAO", "N": "NOVA", "RES": "RESIDENCIAL", "CH": "CHACARA", "CHAC": "CHACARA",
         "STA.": "SANTA", "PTE": "PONTE", "LGO": "LARGO", "BPO": "BISPO", "DR": "DOUTOR", "PE": "PADRE",
         "CEL": "CORONEL", "GAL": "GENERAL", "ENG": "ENGENHEIRO", "PROF": "PROFESSOR", "SEN": "SENADOR",
         "HAB": "HABITACIONAL", "LOT": "LOTEAMENTO", "ALT": "ALTO", "IND": "INDUSTRIAL"}


NAO_BAIRRO = re.compile(r"^(TORRE|TORRES|BLOCO|BL|ED|EDIF|EDIFICIO|COND|CONDOMINIO|CD|RESIDENCIAL|RES|APTO|APT|AP|CASA|SALA|"
                        r"LOTE|QUADRA|QD|TERREO|UNIDADE|UNID|VAGA|LOJA|CONJUNTO RESIDENCIAL|SEM BAIRRO|NAO INFORMADO)\b")


def chave_bairro(s: str) -> str:
    k = chave(s)
    if not k:
        return ""
    partes = k.split(" ")
    if partes and partes[0] in ABREV:
        partes[0] = ABREV[partes[0]]
    return " ".join(partes)


def mes_de(s) -> str | None:
    """'2026-03-20', '20/03/2026', datetime -> '2026-03'."""
    if s is None:
        return None
    if isinstance(s, (dt.date, dt.datetime)):
        return f"{s.year:04d}-{s.month:02d}"
    s = str(s).strip()
    m = re.match(r"(\d{4})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}"
    return None


# ------------------------------------------------------------------ pontos das vendas (mapa de calor dentro do bairro)
# Só Recife (latitude/longitude) e Fortaleza (coordenadas SIRGAS 2000) publicam onde fica cada imóvel. As vendas são
# juntadas em hexágonos de CALOR_LADO metros, e só vai para o site o hexágono com pelo menos CALOR_MIN vendas em 12 meses:
# nenhum ponto, endereço ou venda individual fica salvo.
CALOR_LADO = 110      # metros, do centro ao vértice (o hexágono tem ~190 m de largura)
CALOR_MIN = 5
CAIXA = {  # (lat mín, lat máx, lon mín, lon máx): ponto fora disso é erro de digitação ou de coordenada
    "recife": (-8.16, -7.92, -35.02, -34.85),
    "fortaleza": (-3.90, -3.68, -38.66, -38.38),
}


def utm_sul_para_latlon(x, y, zona):
    """UTM (SIRGAS 2000 = GRS80, hemisfério sul) para latitude e longitude em graus (fórmulas de Snyder)."""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    x -= 500000.0
    y -= 10000000.0
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    c1 = ep2 * math.cos(p1) ** 2
    t1 = math.tan(p1) ** 2
    n1 = a / math.sqrt(1 - e2 * math.sin(p1) ** 2)
    r1 = a * (1 - e2) / (1 - e2 * math.sin(p1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = p1 - (n1 * math.tan(p1) / r1) * (d ** 2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
                                          + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120) / math.cos(p1)
    return math.degrees(lat), (zona - 1) * 6 - 180 + 3 + math.degrees(lon)


def ponto(slug, lat, lon):
    """(lat, lon) se estiver dentro da cidade; None se faltar ou estiver fora."""
    cx = CAIXA.get(slug)
    if cx is None or lat is None or lon is None:
        return None
    if cx[0] <= lat <= cx[1] and cx[2] <= lon <= cx[3]:
        return round(lat, 6), round(lon, 6)
    return None


def hexagono(lat, lon, lat0, lon0, lado=CALOR_LADO):
    """Hexágono (pontudo em cima, coordenadas axiais q, r) que contém o ponto, numa projeção plana local em metros."""
    x = (lon - lon0) * 111320.0 * math.cos(math.radians(lat0))
    y = (lat - lat0) * 110540.0
    q = (math.sqrt(3) / 3 * x - y / 3) / lado
    r = (2 / 3 * y) / lado
    # arredondamento cúbico
    cx, cz = q, r
    cy = -cx - cz
    rx, ry, rz = round(cx), round(cy), round(cz)
    dx, dy, dz = abs(rx - cx), abs(ry - cy), abs(rz - cz)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy <= dz:
        rz = -rx - ry
    return int(rx), int(rz)


def centro_hex(q, r, lat0, lon0, lado=CALOR_LADO):
    x = lado * math.sqrt(3) * (q + r / 2)
    y = lado * 1.5 * r
    return lat0 + y / 110540.0, lon0 + x / (111320.0 * math.cos(math.radians(lat0)))


def calor(vendas, doze) -> dict | None:
    """Hexágonos dos últimos 12 meses com pelo menos CALOR_MIN vendas: [lat, lon, vendas, m² mediano, bairro]."""
    pts = [v for v in vendas if v[2] in doze and v[6].get("pt")]
    if len(pts) < 50:
        return None
    lat0 = round(statistics.median(v[6]["pt"][0] for v in pts), 4)
    lon0 = round(statistics.median(v[6]["pt"][1] for v in pts), 4)
    grupos = defaultdict(list)
    for v in pts:
        grupos[hexagono(*v[6]["pt"], lat0, lon0)].append(v)
    cel = []
    for (q, r), lista in grupos.items():
        if len(lista) < CALOR_MIN:
            continue
        la, lo = centro_hex(q, r, lat0, lon0)
        bairro = Counter(v[0] for v in lista if v[0]).most_common(1)
        cel.append([round(la, 5), round(lo, 5), len(lista), r0(statistics.median(v[3] / v[4] for v in lista)), bairro[0][0] if bairro else ""])
    return {"lado_m": CALOR_LADO, "min": CALOR_MIN, "n_pontos": len(pts), "cel": sorted(cel, key=lambda c: (c[4], c[0], c[1]))}


class Base:
    """Acumula as vendas de uma cidade: (bairro, mês, valor, área, tipo, extras)."""

    def __init__(self, slug):
        self.slug = slug
        self.v = []  # tuplas (chave_bairro, nome_bairro, mes, valor, area, tipo, extras)
        self.dbg = Counter()
        self.valores = defaultdict(Counter)

    def add(self, bairro, mes, valor, area, tipo, **ex):
        if not mes or mes < f"{ANO_INICIO}-01":
            self.dbg["fora_do_periodo"] += 1
            return
        if valor is None or valor < 20000:
            self.dbg["valor_baixo_ou_vazio"] += 1
            return
        if area is None or area < 15 or area > 3000:
            self.dbg["area_fora"] += 1
            return
        self.dbg["ok"] += 1
        bairro = "" if bairro is None else str(bairro).strip()
        self.v.append((chave_bairro(bairro), bairro, mes, valor, area, tipo, ex))

    def conta(self, campo, valor):
        self.valores[campo][str(valor)[:60]] += 1


# ------------------------------------------------------------------ São Paulo
SP_PAGINA = "https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501"


def sao_paulo() -> Base:
    import openpyxl
    b = Base("sao-paulo")
    r = get(SP_PAGINA, timeout=120)
    links = sorted(set(re.findall(r'href="([^"]+\.xlsx[^"]*)"', r.text, flags=re.I)))
    links = [urljoin(r.url, l.replace("&amp;", "&")) for l in links]
    vistos = set()
    cab_ant = None
    for url in links:
        anos = re.findall(r"20\d\d", url.replace("%28", "(").replace("%29", ")"))
        # os nomes antigos trazem o ano; os novos trazem a data da publicação (ddmmaaaa)
        if anos and all(int(a) < ANO_INICIO for a in anos) and not re.search(r"\(\d{8}\)|%28\d{8}%29", url):
            continue
        log("  SP baixando", url)
        try:
            cont = get(url, timeout=900).content
        except Exception as e:  # noqa: BLE001
            log("  SP falhou", e)
            b.dbg["arquivo_falhou"] += 1
            continue
        wb = openpyxl.load_workbook(io.BytesIO(cont), read_only=True, data_only=True)
        for ws in wb.worksheets:
            m = re.match(r"([A-ZÇ]{3})[A-Z]*[-_ /]*(\d{4})", sem_acento(ws.title.upper()).strip())
            if not m or m.group(1)[:3] not in MESES_PT:
                continue
            mes = f"{int(m.group(2)):04d}-{MESES_PT[m.group(1)[:3]]:02d}"
            if mes < f"{ANO_INICIO}-01" or mes in vistos:
                continue
            vistos.add(mes)
            it = ws.iter_rows(values_only=True)
            cab = []
            primeira = None
            for _ in range(6):  # algumas abas têm título antes do cabeçalho
                linha = next(it, None) or []
                cab = [chave(str(c or "")) for c in linha]
                if any(c.startswith("NATUREZA") for c in cab):
                    break
                if primeira is None and linha and (isinstance(linha[0], (int, float))
                                                   or re.fullmatch(r"\d+(\.0)?", str(linha[0] or "").strip())):
                    primeira = linha  # aba sem cabeçalho: os dados começam na 1ª linha
                    break
            if primeira is not None and cab_ant:
                cab = cab_ant
                it = itertools.chain([primeira], it)
                b.dbg["aba_sem_cabecalho_reaproveitado"] += 1
            elif any(c.startswith("NATUREZA") for c in cab):
                cab_ant = cab

            def col(*nomes):
                for n in nomes:
                    for i, c in enumerate(cab):
                        if c.startswith(n):
                            return i
                return None
            i_bairro = col("BAIRRO")
            i_cep = col("CEP")
            i_nat = col("NATUREZA DE TRANSACAO")
            i_val = col("VALOR DE TRANSACAO")
            i_venal = col("VALOR VENAL DE REFERENCIA PROPORCIONAL")
            i_prop = col("PROPORCAO TRANSMITIDA")
            i_base = col("BASE DE CALCULO")
            i_fin = col("TIPO DE FINANCIAMENTO")
            i_area = col("AREA CONSTRUIDA")
            i_uso = col("DESCRICAO DO USO")
            i_acc = col("ACC")
            i_pad = col("DESCRICAO DO PADRAO", "DESCRICAO DO PARDAO")
            faltam = [nm for nm, i in (("valor", i_val), ("natureza", i_nat), ("area", i_area), ("uso", i_uso)) if i is None]
            if faltam:
                b.conta("aba_sem_coluna", f"{ws.title}: {faltam} | {' / '.join(cab[:30])}")
                log(f"    {ws.title}: faltam colunas {faltam}; cabeçalho {cab}")
                continue
            n = 0
            for row in it:
                if not row or row[i_val] is None:
                    continue
                n += 1
                nat = str(row[i_nat] or "")
                b.conta("natureza", nat)
                if not nat.strip().startswith("1."):
                    b.dbg["nao_e_compra_e_venda"] += 1
                    continue
                prop = num(row[i_prop]) if i_prop is not None else 100
                if prop is not None and prop < 99.9:
                    b.dbg["parte_do_imovel"] += 1
                    continue
                uso = chave(str(row[i_uso] or "")) if i_uso is not None else ""
                b.conta("uso", uso)
                if uso.startswith("APARTAMENTO"):
                    tipo = "apto"
                elif uso.startswith("RESIDENCIA"):
                    tipo = "casa"
                else:
                    b.dbg["nao_residencial"] += 1
                    continue
                fin = str(row[i_fin] or "").strip() if i_fin is not None else ""
                b.conta("financiamento", fin)
                bairro = row[i_bairro] if i_bairro is not None else None
                b.dbg["sem_bairro" if not bairro else "com_bairro"] += 1
                b.add(bairro, mes, num(row[i_val]), num(row[i_area]), tipo,
                      base=num(row[i_base]) if i_base is not None else None,
                      venal=num(row[i_venal]) if i_venal is not None else None,
                      fin=fin[:1] if fin else "",
                      cep=re.sub(r"\D", "", str(row[i_cep] or "")).zfill(8) if i_cep is not None and row[i_cep] else "",
                      ano=num(row[i_acc]) if i_acc is not None else None,
                      padrao=str(row[i_pad] or "").strip() if i_pad is not None else "")
            log(f"    {ws.title}: {n} linhas")
        wb.close()
    # o campo "Bairro" de SP é digitado na declaração: vem em branco, com nome de prédio ("TORRE 1",
    # "ED TRIO PERDIZES", "COND ...") ou abreviado. Nesses casos vale o bairro mais comum do mesmo CEP
    # (8 dígitos; se não houver, os 5 primeiros) entre as vendas com bairro válido.
    def valido(k):
        return bool(k) and not NAO_BAIRRO.match(k) and not re.fullmatch(r"[0-9 ]+", k) and len(k) >= 3
    por8, por5, ocorr = defaultdict(Counter), defaultdict(Counter), Counter()
    for k, nome, mes, val, area, tipo, ex in b.v:
        if valido(k):
            ocorr[k] += 1
    for k, nome, mes, val, area, tipo, ex in b.v:
        if valido(k) and ocorr[k] >= 30 and ex.get("cep"):
            por8[ex["cep"]][(k, nome)] += 1
            por5[ex["cep"][:5]][(k, nome)] += 1
    novos = []
    for item in b.v:
        k, nome, mes, val, area, tipo, ex = item
        if not valido(k) or ocorr[k] < 30:
            cep = ex.get("cep") or ""
            alvo = por8.get(cep) or por5.get(cep[:5])
            if alvo:
                (k, nome), _ = alvo.most_common(1)[0]
                b.dbg["bairro_pelo_cep"] += 1
            else:
                k, nome = "", ""
                b.dbg["bairro_desconhecido"] += 1
        novos.append((k, nome, mes, val, area, tipo, ex))
    b.v = novos
    return b


# ------------------------------------------------------------------ CSV comum
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
    leitor = csv.DictReader(io.StringIO(txt), delimiter=sep)
    leitor.fieldnames = [chave(c) for c in leitor.fieldnames]
    return leitor


def ckan_recursos(base, pacote):
    r = get(f"{base}/api/3/action/package_show?id={pacote}", timeout=120)
    return r.json()["result"]["resources"]


# ------------------------------------------------------------------ Belo Horizonte
def belo_horizonte() -> Base:
    b = Base("belo-horizonte")
    recs = ckan_recursos("https://dados.pbh.gov.br", "itbi-relatorios")
    for x in recs:
        url = x.get("url") or ""
        if not url.lower().endswith(".csv"):
            continue
        m = re.findall(r"(20\d{4})", url)
        if m and int(max(m)[:4]) < ANO_INICIO:
            continue
        log("  BH baixando", url)
        for row in ler_csv(get(url, timeout=600).content):
            ocup = row.get("DESCRICAO TIPO OCUPACAO UNIDADE") or row.get("DESCRICAO TIPO OCUPACAO") or ""
            tc = (row.get("TIPO CONSTRUTIVO PREPONDERANTE") or "").strip()
            b.conta("ocupacao", ocup)
            b.conta("tipo_construtivo", tc)
            if chave(ocup) != "RESIDENCIAL":
                b.dbg["nao_residencial"] += 1
                continue
            tipo = "apto" if tc == "AP" else "casa" if tc in ("CA", "CS", "CASA") else None
            if not tipo:
                b.dbg["outro_tipo"] += 1
                continue
            mes = mes_de(row.get("DATA QUITACAO") or row.get("DATA QUITACAO TRANSACAO"))
            b.add(row.get("BAIRRO"), mes, num(row.get("VALOR DECLARADO")),
                  num(row.get("AREA CONSTRUIDA ADQUIRIDA")), tipo,
                  base=num(row.get("VALOR BASE CALCULO")),
                  padrao=(row.get("PADRAO ACABAMENTO UNIDADE") or "").strip(),
                  ano=num(row.get("ANO DE CONSTRUCAO UNIDADE")))
    return b


# ------------------------------------------------------------------ Fortaleza
def fortaleza() -> Base:
    b = Base("fortaleza")
    recs = ckan_recursos("https://dados.fortaleza.ce.gov.br", "dados_abertos_itbi_transacoes_imobiliarias")
    url = next(x["url"] for x in recs if (x.get("url") or "").lower().endswith(".csv"))
    log("  Fortaleza baixando", url)
    ult = {}
    for row in ler_csv(get(url, timeout=900).content):
        dti = (row.get("NUM DTI") or "").strip()
        ver = num(row.get("VERSAO")) or 0
        if dti and (dti not in ult or ver >= ult[dti][0]):
            ult[dti] = (ver, row)
        elif not dti:
            ult[id(row)] = (ver, row)
    b.dbg["versoes_descartadas"] = 0
    for ver, row in ult.values():
        uso = row.get("TIPO USO IMOVEL") or ""
        b.conta("uso", uso)
        if chave(uso) != "RESIDENCIAL":
            b.dbg["nao_residencial"] += 1
            continue
        fr = num(row.get("FRACAO IDEAL"))
        pav = num(row.get("NUMERO PAVIMENTOS")) or 1
        tipo = "apto" if (fr is not None and fr < 0.5 and pav >= 2) else "casa"
        # mês em que a declaração (DTI) foi cadastrada; "ANO_MES_DEBITO" é o vencimento e vai até meses à frente
        mes = mes_de(row.get("DATA CADASTRAMENTO GI IMOVEL"))
        b.conta("padrao", row.get("PADRAO CONSTRUCAO"))
        x, y = num(row.get("XSIRGAS2000")), num(row.get("YSIRGAS2000"))
        pt = None
        if x and y and 400000 < x < 700000 and 9000000 < y < 9700000:
            pt = ponto("fortaleza", *utm_sul_para_latlon(x, y, 24))
        b.dbg["com_coordenada" if pt else "sem_coordenada"] += 1
        b.add(row.get("BAIRRO"), mes, num(row.get("VL BASE CALCULO")), num(row.get("AREA EDIFICADA")), tipo,
              venal=num(row.get("VL VENAL")), padrao=(row.get("PADRAO CONSTRUCAO") or "").strip(), pt=pt)
    return b


# ------------------------------------------------------------------ Porto Alegre
def porto_alegre() -> Base:
    b = Base("porto-alegre")
    recs = ckan_recursos("https://dadosabertos.poa.br", "itbi")
    for x in recs:
        url = x.get("url") or ""
        m = re.search(r"itbi-(\d{4})", url)
        if not url.lower().endswith(".zip") or not m or int(m.group(1)) < ANO_INICIO:
            continue
        log("  POA baixando", url)
        z = zipfile.ZipFile(io.BytesIO(get(url, timeout=600).content))
        guias = {}
        for nome in z.namelist():
            if not nome.lower().endswith((".csv", ".txt")):
                continue
            for row in ler_csv(z.read(nome)):
                g = (row.get("NUMERO GUIA") or "").strip() or str(len(guias))
                guias[g] = row
        for row in guias.values():
            if not (row.get("DATA PAGAMENTO") or "").strip():
                b.dbg["guia_nao_paga"] += 1
                continue
            perc = num(row.get("PERC TRANSMITIDO"))
            if perc is not None and perc < 99.9:
                b.dbg["parte_do_imovel"] += 1
                continue
            fin = chave(row.get("FINALIDADE CONSTRUCAO") or "")
            b.conta("finalidade", fin)
            if fin.startswith("APARTAMENTO") or fin.startswith("APART HOTEL"):
                tipo = "apto" if fin.startswith("APARTAMENTO") else None
            elif fin.startswith("RESIDENCIA"):
                tipo = "casa"
            else:
                tipo = None
            if not tipo:
                b.dbg["nao_residencial_ou_vaga"] += 1
                continue
            area = num(row.get("AREA CONSTR PRIVATIVA")) or num(row.get("AREA CONSTR TOTAL"))
            b.add(row.get("BAIRRO"), mes_de(row.get("DATA PAGAMENTO")), num(row.get("BASE DE CALCULO")), area, tipo,
                  ano=num(row.get("ANO CONSTRUCAO")))
    return b


# ------------------------------------------------------------------ Recife
def recife() -> Base:
    b = Base("recife")
    recs = ckan_recursos("https://dados.recife.pe.gov.br", "imposto-sobre-transmissao-de-bens-imoveis-itbi")
    for x in recs:
        url = x.get("url") or ""
        m = re.search(r"itbi[_-](\d{4})", url)
        if not url.lower().endswith(".csv") or not m or int(m.group(1)) < ANO_INICIO:
            continue
        log("  Recife baixando", url)
        for row in ler_csv(get(url, timeout=600).content):
            t = chave(row.get("TIPO IMOVEL") or "")
            b.conta("tipo_imovel", t)
            tipo = "apto" if t == "APARTAMENTO" else "casa" if t == "CASA" else None
            if not tipo:
                b.dbg["outro_tipo"] += 1
                continue
            pt = ponto("recife", num(row.get("LATITUDE")), num(row.get("LONGITUDE")))
            b.dbg["com_coordenada" if pt else "sem_coordenada"] += 1
            b.add(row.get("BAIRRO"), mes_de(row.get("DATA TRANSACAO")), num(row.get("VALOR AVALIACAO")),
                  num(row.get("AREA CONSTRUIDA")), tipo, ano=num(row.get("ANO CONSTRUCAO")),
                  padrao=(row.get("PADRAO ACABAMENTO") or "").strip(), pt=pt)
    return b


# ------------------------------------------------------------------ Rio (agregado)
RIO_CAMADA = "https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Fazenda/ITBI/MapServer/5"


def rio() -> dict:
    regs = []
    off = 0
    while True:
        url = (f"{RIO_CAMADA}/query?where=1%3D1&outFields=*&orderByFields=objectid"
               f"&resultOffset={off}&resultRecordCount=1000&f=json")
        j = get(url, timeout=180).json()
        fs = j.get("features", [])
        regs += [f["attributes"] for f in fs]
        log(f"  Rio {len(regs)} registros")
        if not fs or not j.get("exceededTransferLimit") and len(fs) < 1000:
            break
        off += len(fs)
    return {"registros": regs}


# ------------------------------------------------------------------ agregação
def quantis(vals, qs):
    s = sorted(vals)
    n = len(s)
    out = []
    for q in qs:
        if n == 0:
            out.append(None)
            continue
        p = q * (n - 1)
        i = int(p)
        f = p - i
        out.append(s[i] if i + 1 >= n else s[i] * (1 - f) + s[i + 1] * f)
    return out


def histograma(vals, lo, hi, nb=24):
    if not vals or hi <= lo:
        return None
    passo = (hi - lo) / nb
    c = [0] * nb
    for v in vals:
        if lo <= v <= hi:
            c[min(nb - 1, int((v - lo) / passo))] += 1
    return {"ini": round(lo), "passo": round(passo, 1), "c": c}


def r0(x):
    return None if x is None else round(x)


def faixa_meses(ms):
    """Todos os meses entre o primeiro e o último (mês sem dado fica com zero, não some do gráfico)."""
    if not ms:
        return []
    a, m = map(int, ms[0].split("-"))
    fim = ms[-1]
    out = []
    while True:
        k = f"{a:04d}-{m:02d}"
        out.append(k)
        if k >= fim:
            return out
        m += 1
        if m > 12:
            a, m = a + 1, 1


def agregar(b: Base, meta: dict) -> dict:
    vendas = b.v
    m2 = [v[3] / v[4] for v in vendas]
    lo, hi = quantis(m2, [0.01, 0.99]) if m2 else (0, 0)
    vendas = [v for v in vendas if lo <= v[3] / v[4] <= hi]
    b.dbg["m2_extremo_descartado"] = len(b.v) - len(vendas)
    meses = faixa_meses(sorted({v[2] for v in vendas}))
    ultimo = meses[-1] if meses else None
    # último mês só entra se tiver pelo menos 60% da mediana dos meses (arquivo do mês ainda incompleto)
    cont = Counter(v[2] for v in vendas)
    if len(meses) > 6 and cont[ultimo] < 0.6 * statistics.median(cont[m] for m in meses[-7:-1]):
        b.dbg["ultimo_mes_incompleto_descartado"] = ultimo
        vendas = [v for v in vendas if v[2] != ultimo]
        meses = meses[:-1]
        ultimo = meses[-1]
    idx = {m: i for i, m in enumerate(meses)}
    doze = set(meses[-12:])

    def resumo(lista, com_mensal=True):
        out = {}
        if com_mensal:
            n = [0] * len(meses)
            val = [0.0] * len(meses)
            pm = defaultdict(list)
            for v in lista:
                i = idx[v[2]]
                n[i] += 1
                val[i] += v[3]
                pm[i].append(v[3] / v[4])
            out["n"] = n
            out["valor"] = [round(x) for x in val]
            out["m2"] = [r0(statistics.median(pm[i])) if len(pm[i]) >= 5 else None for i in range(len(meses))]
        u = [v for v in lista if v[2] in doze]
        mm = [v[3] / v[4] for v in u]
        out["n12"] = len(u)
        if u:
            out["m2_12"] = r0(statistics.median(mm))
            q = quantis(mm, [0.1, 0.25, 0.5, 0.75, 0.9])
            out["q"] = [r0(x) for x in q]
            out["ticket12"] = r0(statistics.median(v[3] for v in u))
            out["area12"] = round(statistics.median(v[4] for v in u), 1)
            out["valor12"] = round(sum(v[3] for v in u))
            tipos = Counter(v[5] for v in u)
            out["tipos"] = dict(tipos)
            if len(u) >= 30:
                a, z = quantis(mm, [0.02, 0.98])
                out["hist"] = histograma(mm, a, z)
            fin = [v for v in u if "fin" in v[6]]
            if fin:
                out["financiado"] = round(sum(1 for v in fin if v[6]["fin"]) / len(fin), 3)
            cmp_ = [v for v in u if v[6].get("base")]
            if cmp_:
                out["base_acima"] = round(sum(1 for v in cmp_ if v[6]["base"] > v[3] * 1.01) / len(cmp_), 3)
            anos = [v[6]["ano"] for v in u if v[6].get("ano") and 1900 < v[6]["ano"] <= 2030]
            if anos:
                out["ano_med"] = int(statistics.median(anos))
            # mesmo período um ano antes, para a variação
        ant = set(meses[-24:-12])
        if len(ant) == 12:
            ua = [v[3] / v[4] for v in lista if v[2] in ant]
            out["n12_ant"] = len(ua)
            if len(ua) >= 10:
                out["m2_12_ant"] = r0(statistics.median(ua))
        return out

    por_bairro = defaultdict(list)
    nomes = defaultdict(Counter)
    for v in vendas:
        if v[0]:
            por_bairro[v[0]].append(v)
            nomes[v[0]][v[1]] += 1
    bairros = {}
    for k, lista in por_bairro.items():
        if len(lista) < 20:
            continue
        r = resumo(lista)
        r["nome"] = nomes[k].most_common(1)[0][0]
        # apartamento e casa separados (só os números dos últimos 12 meses; tipo com menos de 10 vendas fica de fora)
        pt = {}
        for t in ("apto", "casa"):
            sub = [v for v in lista if v[5] == t]
            rt = resumo(sub, com_mensal=False)
            if rt.get("n12", 0) >= 10:
                pt[t] = {c: rt[c] for c in ("n12", "m2_12", "q", "ticket12", "area12", "hist", "n12_ant", "m2_12_ant") if c in rt}
        if pt:
            r["pt"] = pt
        bairros[k] = r
    # mês com falha na base (muito abaixo dos vizinhos, como dez/2025 no Recife): fica em branco, não como queda
    cidade = resumo(vendas)
    falhos = []
    for i in range(len(meses) - 1):
        viz = [cidade["n"][j] for j in range(max(0, i - 3), min(len(meses), i + 4)) if j != i]
        if viz and cidade["n"][i] < 0.35 * statistics.median(viz):
            falhos.append(i)
    res = dict(meta)
    cal = calor(vendas, doze)
    if cal:
        res["calor"] = cal
        b.dbg["hexagonos"] = len(cal["cel"])
    res.update({"meses": meses, "ultimo_mes": ultimo, "cidade": cidade,
                "por_tipo": {t: resumo([v for v in vendas if v[5] == t]) for t in ("apto", "casa")},
                "bairros": bairros,
                "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    if falhos:
        res["meses_falhos"] = [meses[i] for i in falhos]
        b.dbg["meses_falhos"] = res["meses_falhos"]
        for r in [res["cidade"], *res["por_tipo"].values(), *res["bairros"].values()]:
            for i in falhos:
                for campo in ("n", "valor", "m2"):
                    if campo in r:
                        r[campo][i] = None
    b.dbg["vendas_no_site"] = len(vendas)
    b.dbg["bairros_no_site"] = len(bairros)
    b.dbg["bairros_total"] = len(por_bairro)
    return res


def agregar_rio(dados: dict, meta: dict) -> dict:
    regs = dados["registros"]
    d = DBG.setdefault("rio", {})
    d["registros"] = len(regs)
    d["usos"] = Counter(str(r.get("uso")) for r in regs).most_common(20)
    d["mercado"] = Counter(str(r.get("principal_transação_mercado")) for r in regs).most_common(10)
    d["exemplo"] = regs[:3]
    linhas = []
    for r in regs:
        uso = chave(str(r.get("uso") or ""))
        if not uso.startswith("RESIDENCIAL"):
            continue
        a, m = r.get("ano_transação"), r.get("mês_transação")
        try:
            mes = f"{int(a):04d}-{int(m):02d}"
        except (TypeError, ValueError):
            mm = MESES_PT.get(chave(str(m or "")))
            if not mm:
                continue
            mes = f"{int(a):04d}-{mm:02d}"
        if mes < f"{ANO_INICIO}-01":
            continue
        n = r.get("total_transações") or 0
        vm = r.get("média_valor_transação") or 0
        am = r.get("média_área_construída") or 0
        linhas.append((chave_bairro(r.get("bairro") or ""), (r.get("bairro") or "").strip(), mes, n, vm, am))
    meses = faixa_meses(sorted({x[2] for x in linhas}))
    idx = {m: i for i, m in enumerate(meses)}
    doze = set(meses[-12:])

    def resumo(ls):
        n = [0] * len(meses)
        val = [0.0] * len(meses)
        area = [0.0] * len(meses)
        for _, _, mes, q, vm, am in ls:
            i = idx[mes]
            n[i] += q
            val[i] += q * vm
            area[i] += q * am
        out = {"n": n, "valor": [round(x) for x in val],
               "m2": [r0(val[i] / area[i]) if n[i] >= 5 and area[i] > 0 else None for i in range(len(meses))]}
        u = [x for x in ls if x[2] in doze]
        q12 = sum(x[3] for x in u)
        v12 = sum(x[3] * x[4] for x in u)
        a12 = sum(x[3] * x[5] for x in u)
        out["n12"] = q12
        if q12:
            out["m2_12"] = r0(v12 / a12) if a12 else None
            out["ticket12"] = r0(v12 / q12)
            out["area12"] = round(a12 / q12, 1)
            out["valor12"] = round(v12)
        ant = set(meses[-24:-12])
        if len(ant) == 12:
            ua = [x for x in ls if x[2] in ant]
            qa = sum(x[3] for x in ua)
            out["n12_ant"] = qa
            aa = sum(x[3] * x[5] for x in ua)
            if qa >= 10 and aa:
                out["m2_12_ant"] = r0(sum(x[3] * x[4] for x in ua) / aa)
        return out

    por = defaultdict(list)
    nomes = {}
    for x in linhas:
        if x[0]:
            por[x[0]].append(x)
            nomes[x[0]] = x[1]
    bairros = {}
    for k, ls in por.items():
        r = resumo(ls)
        if r["n12"] + r.get("n12_ant", 0) < 20:
            continue
        r["nome"] = nomes[k]
        bairros[k] = r
    res = dict(meta)
    res.update({"meses": meses, "ultimo_mes": meses[-1] if meses else None, "cidade": resumo(linhas),
                "bairros": bairros, "agregado": True,
                "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    d["bairros_no_site"] = len(bairros)
    return res


CIDADES = {
    "sao-paulo": (sao_paulo, {"nome": "São Paulo", "uf": "SP", "valor": "declarado",
                              "fonte": "Prefeitura de São Paulo, Secretaria da Fazenda: guias de ITBI pagas",
                              "fonte_url": SP_PAGINA}),
    "belo-horizonte": (belo_horizonte, {"nome": "Belo Horizonte", "uf": "MG", "valor": "declarado",
                                        "fonte": "Prefeitura de Belo Horizonte, Portal de Dados Abertos: ITBI Relatórios",
                                        "fonte_url": "https://dados.pbh.gov.br/dataset/itbi-relatorios"}),
    "fortaleza": (fortaleza, {"nome": "Fortaleza", "uf": "CE", "valor": "base",
                              "fonte": "Prefeitura de Fortaleza, Portal de Dados Abertos: ITBI",
                              "fonte_url": "https://dados.fortaleza.ce.gov.br/dataset/dados_abertos_itbi_transacoes_imobiliarias"}),
    "porto-alegre": (porto_alegre, {"nome": "Porto Alegre", "uf": "RS", "valor": "base",
                                    "fonte": "Prefeitura de Porto Alegre, Dados Abertos POA: ITBI",
                                    "fonte_url": "https://dadosabertos.poa.br/dataset/itbi"}),
    "recife": (recife, {"nome": "Recife", "uf": "PE", "valor": "avaliacao",
                        "fonte": "Prefeitura do Recife, Dados Abertos Recife: ITBI",
                        "fonte_url": "https://dados.recife.pe.gov.br/dataset/imposto-sobre-transmissao-de-bens-imoveis-itbi"}),
}


JUROS_M = "https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/odata/TaxasJurosMensalPorMes"
JUROS_ARQ = RAIZ / "data" / "juros_imob.json"


def _olinda(url: str, params: dict):
    from urllib.parse import quote
    q = "&".join(f"{k}={quote(str(v), safe=chr(39))}" for k, v in params.items())  # o Olinda não entende '+'
    return get(url + "?" + q, timeout=120, tentativas=3).json().get("value", [])


def juros_imob():
    """Juros do financiamento imobiliário de cada banco (Banco Central, média do último mês publicado),
    corrigido pela TR, para o simulador. reguladas = SFH; mercado = demais (SFI)."""
    v = _olinda(JUROS_M, {"$top": "1", "$format": "json", "$orderby": "anoMes desc", "$select": "anoMes"})
    mes = str(v[0]["anoMes"])
    linhas = _olinda(JUROS_M, {"$top": "20000", "$format": "json", "$filter": f"anoMes eq '{mes}'"})
    out = {"mes": mes, "reguladas": [], "mercado": []}
    for x in linhas:
        mod = x.get("Modalidade") or ""
        if "imobili" not in mod.lower() or "TR" not in mod or x.get("TaxaJurosAoAno") is None:
            continue
        chave = "reguladas" if "reguladas" in mod else "mercado"
        out[chave].append([x["InstituicaoFinanceira"].strip(), round(float(x["TaxaJurosAoMes"]), 4), round(float(x["TaxaJurosAoAno"]), 4)])
    for k in ("reguladas", "mercado"):
        out[k].sort(key=lambda r: r[2])
    if len(out["reguladas"]) + len(out["mercado"]) < 5:
        raise RuntimeError(f"juros imobiliários: só {len(out['reguladas']) + len(out['mercado'])} bancos em {mes}")
    JUROS_ARQ.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"juros imobiliários {mes}: {len(out['reguladas'])} bancos (SFH), {len(out['mercado'])} (mercado)")


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    so = sys.argv[1:]  # opcional: só algumas cidades
    falhas = []
    try:  # juros do simulador: se falhar, fica o arquivo anterior
        juros_imob()
    except Exception as e:  # noqa: BLE001
        log(f"  ERRO juros imobiliários: {e!r}")
        DBG["juros_imob"] = {"erro": repr(e)[:300]}
    for slug, (f, meta) in CIDADES.items():
        if so and slug not in so:
            continue
        log(f"== {meta['nome']}")
        try:
            b = f()
            dados = agregar(b, meta)
            (SAIDA / f"{slug}.json").write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")),
                                                encoding="utf-8")
            DBG[slug] = {"contagens": dict(b.dbg),
                         "valores": {k: v.most_common(40) for k, v in b.valores.items()},
                         "meses": dados["meses"][-3:], "n_ultimos": dados["cidade"]["n"][-6:]}
        except Exception as e:  # noqa: BLE001
            log(f"  ERRO {slug}: {e!r}")
            DBG[slug] = {"erro": repr(e)[:500]}
            falhas.append(slug)
    if not so or "rio-de-janeiro" in so:
        log("== Rio de Janeiro")
        try:
            dados = agregar_rio(rio(), {"nome": "Rio de Janeiro", "uf": "RJ", "valor": "media",
                                        "fonte": "Prefeitura do Rio, Secretaria de Fazenda (via data.rio): "
                                                 "transações de ITBI por bairro e mês",
                                        "fonte_url": "https://www.data.rio/"})
            (SAIDA / "rio-de-janeiro.json").write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")),
                                                       encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            log(f"  ERRO rio: {e!r}")
            DBG.setdefault("rio", {})["erro"] = repr(e)[:500]
            falhas.append("rio-de-janeiro")
    if not DBG:
        return 0  # nenhuma cidade pedida (ex.: só republicar o site)
    if DEBUG.exists() and so:
        antigo = json.loads(DEBUG.read_text(encoding="utf-8"))
        antigo.update(DBG)
        DBG.clear()
        DBG.update(antigo)
    DBG["gerado_em"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    DEBUG.write_text(json.dumps(DBG, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if falhas:
        log("Falharam:", falhas)
    return 1 if len(falhas) == len(CIDADES) + 1 else 0


if __name__ == "__main__":
    sys.exit(main())
