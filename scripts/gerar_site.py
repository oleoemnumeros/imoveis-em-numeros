"""Gera o site do Imóveis em Números a partir de data/cidades/*.json.

Configuração em site/config.json:
  base    caminho do site quando ele fica numa subpasta (prévia no github.io: "/imoveis-em-numeros"; com domínio: "")
  previa  true = página marcada para o Google não indexar e faixa "prévia" no topo
As variáveis de ambiente BASE e PREVIA, se preenchidas, valem mais que o arquivo.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
import statistics
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "data" / "cidades"
SITE = RAIZ / "site"
SAIDA = RAIZ / "docs"
DOMINIO = "imoveisemnumeros.com.br"
URL = f"https://{DOMINIO}"

_cfg = json.loads((SITE / "config.json").read_text(encoding="utf-8")) if (SITE / "config.json").exists() else {}
BASEP = (os.environ.get("BASE") or _cfg.get("base") or "").rstrip("/")
PREVIA = (os.environ.get("PREVIA") or str(_cfg.get("previa", ""))).lower() in ("1", "true", "sim")
GOAT = '' if PREVIA else '<script data-goatcounter="https://imoveisemnumeros.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>'

ORDEM = ["sao-paulo", "rio-de-janeiro", "belo-horizonte", "fortaleza", "recife", "porto-alegre"]
NOMES_CIDADE = {"sao-paulo": "São Paulo", "rio-de-janeiro": "Rio de Janeiro", "belo-horizonte": "Belo Horizonte",
                "fortaleza": "Fortaleza", "recife": "Recife", "porto-alegre": "Porto Alegre"}
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
         "outubro", "novembro", "dezembro"]
MES_CURTO = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

FAMILIA = [
    ("Óleo em Números", "Petróleo e gás", "https://oleoemnumeros.com.br/", "#17758C"),
    ("Comex em Números", "Exportações e importações", "https://comexemnumeros.com.br/", "#1F85D0"),
    ("Voo em Números", "Pontualidade aérea", "https://vooemnumeros.com.br/", "#4FB8EE"),
    ("Economia em Números", "Macroeconomia", "https://economiaemnumeros.com.br/", "#D9A514"),
    ("Imóveis em Números", "Preço real dos imóveis", URL + "/", "#7A52C7"),
]
ATUAL = "Imóveis em Números"

# o que é o "valor" de cada cidade
VALOR_TXT = {
    "declarado": ("valor declarado na compra", "o valor que comprador e vendedor declararam à prefeitura ao pagar o ITBI"),
    "base": ("base de cálculo do ITBI", "a base de cálculo do ITBI: o maior entre o valor declarado na compra e a avaliação da prefeitura"),
    "avaliacao": ("avaliação da prefeitura", "o valor de avaliação que a prefeitura usa para cobrar o ITBI; a base aberta do Recife não traz o preço declarado"),
    "media": ("média das transações", "a média do valor das transações por bairro e mês; a prefeitura do Rio publica só as médias, não venda a venda"),
}

LOGO = ('<svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true"><rect x="1" y="1" width="28" height="28" rx="7" fill="#7A52C7"/>'
        '<path d="M7.5 15.2 15 8.8l7.5 6.4" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M10 14.2V22h3.4v-4h3.2v4H20v-7.8" fill="none" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/></svg>')
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 30"><rect x="1" y="1" width="28" height="28" rx="7" fill="#7A52C7"/>'
           '<path d="M7.5 15.2 15 8.8l7.5 6.4" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
           '<path d="M10 14.2V22h3.4v-4h3.2v4H20v-7.8" fill="none" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/></svg>')


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def u(caminho: str) -> str:
    """Endereço interno, com a subpasta da prévia quando houver."""
    return BASEP + caminho


def slug(s: str) -> str:
    t = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def nf(x, d=0) -> str:
    if x is None:
        return "–"
    s = f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(x) -> str:
    return "–" if x is None else "R$ " + nf(x)


def brl_curto(x) -> str:
    if x is None:
        return "–"
    if x >= 1e9:
        return f"R$ {nf(x / 1e9, 1)} {'bilhão' if round(x / 1e9, 1) < 2 else 'bilhões'}"
    if x >= 1e6:
        return f"R$ {nf(x / 1e6, 1)} {'milhão' if round(x / 1e6, 1) < 2 else 'milhões'}"
    if x >= 1e3:
        return f"R$ {nf(x / 1e3, 0)} mil"
    return brl(x)


def pct(x, d=1, sinal=False) -> str:
    if x is None:
        return "–"
    s = nf(x * 100, d) + "%"
    return ("+" + s if sinal and x > 0 else s).replace("-", "−")


ARTIGO = {"Rio de Janeiro": "o", "Recife": "o"}


def em_(nome: str) -> str:
    return ("no " if ARTIGO.get(nome) == "o" else "em ") + nome


def de_(nome: str) -> str:
    return ("do " if ARTIGO.get(nome) == "o" else "de ") + nome


def var(a, b):
    return None if not a or not b else a / b - 1


def mes_nome(m: str) -> str:
    a, mm = m.split("-")
    return f"{MESES[int(mm) - 1]} de {a}"


def mes_curto(m: str) -> str:
    a, mm = m.split("-")
    return f"{MES_CURTO[int(mm) - 1]}/{a[2:]}"


def seta(v, d=1) -> str:
    if v is None:
        return ""
    if abs(v) < 0.0005:
        return '<span class="small">estável</span>'
    c = "up" if v > 0 else "down"
    return f'<span class="{c}">{"▲" if v > 0 else "▼"} {pct(abs(v), d)}</span>'


# Nomes para mostrar: as prefeituras mandam os bairros sem acento ("SAUDE", "TRES FIGUEIRAS") e às vezes
# cortados ("MOINHOS VENTO"). preparar_nomes() troca pelo nome do OpenStreetMap quando o bairro é o mesmo
# e, se não houver, acentua palavra por palavra com o que aparece acentuado nos nomes do OSM.
# Só muda o que aparece na tela: os endereços das páginas continuam iguais.
NOMES_EXIB: dict = {}
PALAVRAS_ACENTO = {"sao": "são", "jose": "josé", "joao": "joão", "conceicao": "conceição", "antonio": "antônio",
                   "gloria": "glória", "america": "américa", "uniao": "união", "independencia": "independência",
                   "esperanca": "esperança", "goncalo": "gonçalo", "inacio": "inácio", "lucia": "lúcia",
                   "teresopolis": "teresópolis", "petropolis": "petrópolis", "higienopolis": "higienópolis",
                   "cristovao": "cristóvão", "sebastiao": "sebastião", "estacao": "estação", "alianca": "aliança"}


def _sem_acento(t: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", t) if unicodedata.category(ch) != "Mn")


def preparar_nomes(cidades: dict, mapas: dict) -> None:
    from collections import Counter
    formas, simples = {}, Counter()
    todos = []
    for s, c in cidades.items():
        m = mapas.get(s)
        osm = {}
        if m is not None and m.ok:
            for k, bs in m.por_dado.items():
                ns = {b["nome"] for b in bs}
                if len(ns) == 1:
                    osm[k] = ns.pop()
            todos += [b["nome"] for b in getattr(m, "areas", [])]
        fe = ENTORNO / f"{s}.json"
        if fe.exists():
            for lon, lat, nm in json.loads(fe.read_text(encoding="utf-8")).get("lugares", []):
                todos.append(nm)
                osm.setdefault(chave_bairro_site(nm), nm)
        for k, b in c["bairros"].items():
            nm = osm.get(k)
            # só usa o nome do OSM se for o mesmo nome (sem acento) ou o do ITBI cortado
            if nm and (_sem_acento(nm).upper().replace(" DE ", " ").replace(" DA ", " ").replace(" DO ", " ")
                       .startswith(_sem_acento(str(b["nome"])).upper().replace(" DE ", " ").replace(" DA ", " ").replace(" DO ", " ")[:15])):
                NOMES_EXIB[str(b["nome"])] = nm
    for nm in todos:
        for w in re.findall(r"[^\W\d_]+", nm):
            lw = w.lower()
            if len(lw) < 3:
                continue
            k = _sem_acento(lw)
            if k != lw:
                formas.setdefault(k, Counter())[lw] += 1
            else:
                simples[k] += 1
    for k, cont in formas.items():
        forma, n = cont.most_common(1)[0]
        if n > simples.get(k, 0) and k not in PALAVRAS_ACENTO:
            PALAVRAS_ACENTO[k] = forma


def _acentua(s: str) -> str:
    def troca(m):
        w = m.group(0)
        a = PALAVRAS_ACENTO.get(w.lower())
        if not a:
            return w
        return a[:1].upper() + a[1:] if w[:1].isupper() else a
    return re.sub(r"[^\W\d_]+", troca, s)


def nome_bonito(s: str) -> str:
    if str(s) in NOMES_EXIB:
        return NOMES_EXIB[str(s)]
    s = re.sub(r"\s+", " ", str(s)).strip()
    if s.isupper() or s.islower():
        minus = {"de", "da", "do", "das", "dos", "e", "d"}
        ps = []
        for i, p in enumerate(s.lower().split(" ")):
            ps.append(p if (i and p in minus) else p[:1].upper() + p[1:])
        s = " ".join(ps)
    s = re.sub(r"\bJd\b\.?", "Jardim", s)
    s = re.sub(r"\bVl\b\.?", "Vila", s)
    s = re.sub(r"\bPq\b\.?", "Parque", s)
    s = re.sub(r"\bCid\b\.?", "Cidade", s)
    s = re.sub(r"\bSta\b\.?", "Santa", s)
    s = re.sub(r"\bSto\b\.?", "Santo", s)
    s = re.sub(r"\bHistoric\b", "Histórico", s)
    return _acentua(s)


# ---------------------------------------------------------------- termômetro
def termometro(n: list, meses: list) -> tuple[str, str, float | None]:
    """Vendas dos últimos 3 meses contra os mesmos 3 meses do ano anterior."""
    if len(n) < 15:
        return ("", "", None)
    if any(x is None for x in n[-3:] + n[-15:-12]):
        return ("", "", None)
    atual = sum(n[-3:])
    antes = sum(n[-15:-12])
    if antes < 15:
        return ("", "", None)
    v = atual / antes - 1
    if v >= 0.10:
        return ("q", "Aquecendo", v)
    if v <= -0.10:
        return ("f", "Esfriando", v)
    return ("e", "Estável", v)


def termo_html(t) -> str:
    cls, txt, v = t
    if not cls:
        return ""
    return f'<span class="termo {cls}">{txt} <span class="num">{pct(v, 0, True)}</span></span>'


def media_movel(v: list, k=3):
    out = []
    for i in range(len(v)):
        jan = [x for x in v[max(0, i - k + 1): i + 1] if x is not None]
        out.append(round(sum(jan) / len(jan)) if len(jan) >= 2 else None)
    return out


# ---------------------------------------------------------------- gráficos
def svg_barras(vals, cor="#7A52C7", w=640, h=200) -> str:
    vs = [v or 0 for v in vals]
    mx = max(vs) or 1
    n = len(vs)
    bw = w / max(n, 1)
    rects = "".join(f'<rect x="{i * bw + 1:.1f}" y="{h - 20 - (v / mx) * (h - 30):.1f}" width="{max(bw - 2, 1):.1f}" '
                    f'height="{(v / mx) * (h - 30):.1f}" fill="{cor}"/>' for i, v in enumerate(vs))
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-hidden="true">{rects}</svg>'


def svg_linha(vals, cor="#7A52C7", w=640, h=200) -> str:
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 2:
        return ""
    lo = min(v for _, v in pts)
    hi = max(v for _, v in pts)
    hi = hi if hi > lo else lo + 1
    n = len(vals) - 1 or 1
    d = " ".join(f"{(i / n) * (w - 10) + 5:.1f},{h - 15 - ((v - lo) / (hi - lo)) * (h - 30):.1f}" for i, v in pts)
    return f'<svg viewBox="0 0 {w} {h}" role="img" aria-hidden="true"><polyline points="{d}" fill="none" stroke="{cor}" stroke-width="2.5"/></svg>'


def fam_gr(cfg: dict, reserva: str, aria: str) -> str:
    dados = html.escape(json.dumps({**cfg, "a": aria}, ensure_ascii=False, separators=(",", ":")), quote=True)
    return f'<div class="fam-gr" data-fam-gr="{dados}">{reserva}</div>'


def grafico_vendas(meses, n, aria) -> str:
    return fam_gr({"t": "b", "p": meses, "s": [{"n": "Vendas", "v": n}], "d": 0, "u": "vendas", "z": 1},
                  svg_barras(n), aria)


def grafico_valor(meses, valor, aria) -> str:
    mi = [None if v is None else round(v / 1e6, 1) for v in valor]
    return fam_gr({"t": "b", "p": meses, "s": [{"n": "Valor movimentado", "v": mi}], "d": 1, "pre": "R$ ",
                   "suf": " mi", "u": "R$ milhões", "z": 1}, svg_barras(mi), aria)


def grafico_m2(meses, m2, aria, rotulo="m² mediano") -> str:
    return fam_gr({"t": "l", "p": meses, "s": [{"n": rotulo, "v": m2}], "d": 0, "pre": "R$ ", "u": "R$ por m²"},
                  svg_linha(m2), aria)


def tipo_bairro_html(b: dict, nb: str) -> str:
    """Apartamento e casa separados no bairro (últimos 12 meses)."""
    pt = b.get("pt") or {}
    if not pt:
        return ""
    rot = {"apto": "Apartamentos", "casa": "Casas"}
    ls = []
    for t in ("apto", "casa"):
        d = pt.get(t)
        if not d:
            continue
        vb = var(d.get("m2_12"), d.get("m2_12_ant")) if (d.get("n12", 0) >= 30 and d.get("n12_ant", 0) >= 30) else None
        faixa = f"R$ {nf(d['q'][1])} a {nf(d['q'][3])}" if d.get("q") and d["n12"] >= 20 else "–"
        ls.append(f'<tr><td>{rot[t]}</td><td class="r num">R$ {nf(d.get("m2_12"))}</td><td class="r num m-esc">{seta(vb)}</td>'
                  f'<td class="r num m-esc">{faixa}</td><td class="r num">{brl_curto(d.get("ticket12"))}</td>'
                  f'<td class="r num m-esc">{nf(d.get("area12"), 0)} m²</td><td class="r num">{nf(d["n12"])}</td></tr>')
    falta = [rot[t].lower() for t in ("apto", "casa") if t not in pt]
    nota = f" Não há vendas suficientes de {falta[0]} para mostrar (mínimo de 10 em 12 meses)." if falta else ""
    return f"""<section class="card" id="tipos"><h2>Apartamento ou casa em {esc(nb)}</h2>
<div class="tw"><table><thead><tr><th>Tipo</th><th class="r">m² mediano</th><th class="r m-esc">Em 1 ano</th><th class="r m-esc">Metade das vendas (m²)</th><th class="r">Preço mediano</th><th class="r m-esc">Área mediana</th><th class="r">Vendas (12 meses)</th></tr></thead>
<tbody>{"".join(ls)}</tbody></table></div>
<p class="small">Últimos 12 meses. "Metade das vendas" é a faixa do meio do preço do m²: um quarto saiu abaixo e um quarto acima.{nota}</p></section>"""


def curva_html(b: dict, cidade_m2: int | None, nome: str) -> str:
    """Distribuição do preço do m² das vendas dos últimos 12 meses, com a faixa do meio marcada."""
    h = b.get("hist")
    q = b.get("q")
    if not h or not q:
        return ""
    c = h["c"]
    ini, passo = h["ini"], h["passo"]
    nb = len(c)
    W, H, PAD = 640, 220, 26
    mx = max(c) or 1
    # suaviza um pouco (média de 3) para a curva não ficar serrilhada
    s = [(c[max(0, i - 1)] + 2 * c[i] + c[min(nb - 1, i + 1)]) / 4 for i in range(nb)]
    mx = max(s) or 1
    x0, x1 = ini, ini + passo * nb

    def X(v):
        return PAD + (v - x0) / (x1 - x0) * (W - 2 * PAD)

    def Y(v):
        return H - 34 - (v / mx) * (H - 70)
    pts = [(X(ini + passo * (i + 0.5)), Y(v)) for i, v in enumerate(s)]
    area = f"M{X(x0):.1f},{Y(0):.1f} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in pts) + f" L{X(x1):.1f},{Y(0):.1f} Z"
    faixa = (f'<rect x="{X(q[1]):.1f}" y="18" width="{max(X(q[3]) - X(q[1]), 1):.1f}" height="{H - 52}" '
             f'fill="#7A52C7" opacity=".10"/>')
    linhas = []

    def marca(v, rot, cor, y):
        if v is None or not (x0 <= v <= x1):
            return
        linhas.append(f'<line x1="{X(v):.1f}" x2="{X(v):.1f}" y1="18" y2="{H - 34}" stroke="{cor}" stroke-width="1.5" stroke-dasharray="4 3"/>'
                      f'<text class="rot" x="{X(v):.1f}" y="{y}" text-anchor="middle">{rot}</text>')
    marca(q[2], f"mediana R$ {nf(q[2])}", "#5B36A8", 13)
    if cidade_m2 and abs((cidade_m2 or 0) - q[2]) / q[2] > 0.08:
        marca(cidade_m2, "cidade", "#9AA6B2", H - 20)
    eixo = "".join(f'<text x="{X(v):.1f}" y="{H - 6}" text-anchor="middle">{nf(v / 1000, 0 if v >= 10000 else 1)} mil</text>'
                   for v in [x0 + (x1 - x0) * k / 4 for k in range(5)])
    svg = (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Distribuição do preço do metro quadrado {esc(em_(nome))}">'
           f'{faixa}<path d="{area}" fill="#7A52C7" opacity=".55"/>{"".join(linhas)}{eixo}</svg>')
    tq = {t: d["q"] for t, d in (b.get("pt") or {}).items() if d.get("q") and d.get("n12", 0) >= 20}
    dados = esc(json.dumps({"q": q, "h": h, **({"t": tq} if tq else {})}, separators=(",", ":")))
    sel_tipo = ('<label>Tipo<select name="tipo"><option value="">Todos</option>'
                + "".join(f'<option value="{t}">{r}</option>' for t, r in (("apto", "Apartamento"), ("casa", "Casa")) if t in tq)
                + "</select></label>") if tq else ""
    return f"""<section class="card" id="curva">
<h2>Onde fica o preço do metro quadrado {esc(em_(nome))}</h2>
<p class="small">Cada venda dos últimos 12 meses entra uma vez. A faixa escura reúne a metade do meio: 25% das vendas saíram abaixo de <b>R$ {nf(q[1])}/m²</b> e 25% acima de <b>R$ {nf(q[3])}/m²</b>.</p>
<div class="curva">{svg}</div>
<h3>Compare um imóvel</h3>
<div class="comp" data-comp="{dados}">
<label>Preço (R$)<input type="text" inputmode="numeric" name="preco" placeholder="650.000" autocomplete="off"></label>
<label>Área (m²)<input type="text" inputmode="decimal" name="area" placeholder="80" autocomplete="off"></label>
{sel_tipo}
</div>
<p class="comp-res" aria-live="polite">Digite o preço e a área de um imóvel anunciado para ver em que ponto da curva ele cai.</p>
</section>"""


# ---------------------------------------------------------------- mapa
CORES_MAPA = ["#E2D8F5", "#C3AEEB", "#9F7FDB", "#7A52C7", "#4E2496"]
MAPAS = RAIZ / "data" / "mapas"


def casar_bairros(mapa_bairros, dados_bairros):
    """{chave do contorno: chave do ITBI}: nome igual depois de tirar "de/da/do" e espaços e de abrir
    abreviações (JAR, STA, STO); ou nome do ITBI cortado no limite de caracteres da base (15)."""
    def norm(k):
        ab = {"JAR": "JARDIM", "JD": "JARDIM", "STA": "SANTA", "STO": "SANTO", "VL": "VILA", "PQ": "PARQUE"}
        ps = [ab.get(p, p) for p in k.split() if p not in ("DE", "DA", "DO", "DAS", "DOS", "E")]
        return "".join(ps)
    por_norm = {}
    for k in dados_bairros:
        por_norm.setdefault(norm(k), k)
    par = {}
    for b in mapa_bairros:
        k = b["k"]
        if k in dados_bairros:
            par[k] = k
            continue
        n = norm(k)
        if n in por_norm:
            par[k] = por_norm[n]
            continue
        cortados = [x for x in dados_bairros if len(x) == 15 and n.startswith(norm(x))]
        if len(cortados) == 1:
            par[k] = cortados[0]
    return par


PADRAO_SD = ""


class Mapa:
    """Contornos de uma cidade casados com os bairros do ITBI, projetados para SVG (640 de largura)."""
    W = 640

    def __init__(self, s, c):
        import math
        self.s, self.c = s, c
        self.ok = False
        f = MAPAS / f"{s}.json"
        if not f.exists():
            return
        mp = json.loads(f.read_text(encoding="utf-8"))
        self.nivel = mp.get("nivel")
        self.areas = mp["bairros"]
        self.dados = c["bairros"]
        self.par = casar_bairros(self.areas, self.dados)
        vals = sorted(self.dados[self.par[b["k"]]]["m2_12"] for b in self.areas
                      if b["k"] in self.par and self.dados[self.par[b["k"]]].get("m2_12"))
        if len(vals) < 8:
            return
        self.cortes = [vals[int(len(vals) * q)] for q in (0.2, 0.4, 0.6, 0.8)]
        xs = [x for b in self.areas for a in b["p"] for x, _ in a]
        ys = [y for b in self.areas for a in b["p"] for _, y in a]
        self.x0, self.y1 = min(xs), max(ys)
        self.kx = math.cos(math.radians((min(ys) + max(ys)) / 2))
        self.e = self.W / ((max(xs) - min(xs)) * self.kx)
        self.H = (max(ys) - min(ys)) * self.e + 2
        # projeta tudo uma vez
        for b in self.areas:
            b["xy"] = [[self.xy(x, y) for x, y in a] for a in b["p"]]
            b["cxy"] = self.xy(*b["c"])
            todos = [q for a in b["xy"] for q in a]
            b["bb"] = (min(q[0] for q in todos), min(q[1] for q in todos), max(q[0] for q in todos), max(q[1] for q in todos))
        self.por_dado = {}
        for b in self.areas:
            if b["k"] in self.par:
                self.por_dado.setdefault(self.par[b["k"]], []).append(b)
        self.ok = True

    def xy(self, x, y):
        return ((x - self.x0) * self.kx * self.e, (self.y1 - y) * self.e + 1)

    def classe(self, k):
        v = self.dados[k].get("m2_12")
        return None if v is None else sum(1 for x in self.cortes if v > x)

    def path(self, b, dec=1):
        return " ".join("M" + " L".join(f"{x:.{dec}f} {y:.{dec}f}" for x, y in a) + "Z" for a in b["xy"])

    def area_svg(self, b, dec=1, destaque=False):
        d = self.path(b, dec)
        k = self.par.get(b["k"])
        if k and self.dados[k].get("m2_12"):
            dd = self.dados[k]
            tit = f"{nome_bonito(dd['nome'])}: R$ {nf(dd['m2_12'])}/m² ({nf(dd['n12'])} vendas em 12 meses)"
            extra = ' class="eu"' if destaque else ""
            return (f'<a href="{u(f"/{self.s}/{slug(dd["nome"])}/")}"><path{extra} d="{d}" fill="{CORES_MAPA[self.classe(k)]}">'
                    f'<title>{esc(tit)}</title></path></a>')
        return f'<path class="sd" d="{d}"><title>{esc(nome_bonito(b["nome"]))}: sem dados ou poucas vendas no período</title></path>'

    def legenda(self):
        cs = self.cortes
        faixas = [f"até R$ {nf(cs[0])}"] + [f"R$ {nf(cs[i])} a {nf(cs[i + 1])}" for i in range(3)] + [f"acima de R$ {nf(cs[3])}"]
        leg = "".join(f'<li><i style="background:{CORES_MAPA[i]}"></i>{t}</li>' for i, t in enumerate(faixas))
        return f'<ul class="legenda-m2">{leg}<li><i class="sd"></i>sem dados ou poucas vendas</li></ul>'

    def credito(self, extra=""):
        nivel = "distritos" if self.nivel == 9 else "bairros"
        return (f'<p class="small">Contornos dos {nivel}: © colaboradores do <a href="https://www.openstreetmap.org/copyright" '
                f'rel="noopener">OpenStreetMap</a>.{extra}</p>')

    @staticmethod
    def rotulos(itens, fs, limite):
        """itens: (x, y, texto, classe). Põe o nome ao lado do ponto, sem sobrepor outro nome."""
        postos, out = [], []
        for x, y, t, cls in itens:
            w, h = len(t) * fs * 0.5, fs * 1.2
            for dx, dy, anc in ((fs * 0.6, fs * 0.35, "start"), (-fs * 0.6, fs * 0.35, "end"),
                                (0, -fs * 0.7, "middle"), (0, fs * 1.4, "middle")):
                x0 = x + dx if anc == "start" else x + dx - w if anc == "end" else x - w / 2
                caixa = (x0, y + dy - h * 0.8, x0 + w, y + dy + h * 0.2)
                if caixa[0] < 0 or caixa[2] > limite[0] or caixa[1] < 0 or caixa[3] > limite[1]:
                    continue
                if any(not (caixa[2] < p[0] or caixa[0] > p[2] or caixa[3] < p[1] or caixa[1] > p[3]) for p in postos):
                    continue
                postos.append(caixa)
                pad = fs * 0.25
                out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{fs * 0.24:.1f}" class="pt"/>'
                           f'<rect x="{caixa[0] - pad:.1f}" y="{caixa[1] - pad * 0.4:.1f}" width="{w + 2 * pad:.1f}" height="{h + pad * 0.4:.1f}" '
                           f'rx="{fs * 0.3:.1f}" class="et {cls}"/>'
                           f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" text-anchor="{anc}" font-size="{fs:.1f}" class="{cls}">{esc(t)}</text>')
                break
        return "".join(out)

    def cidade_html(self) -> str:
        if not self.ok:
            return ""
        partes = [self.area_svg(b) for b in self.areas]
        # nomes: os 5 bairros com mais vendas e os 5 mais caros (com pelo menos 30 vendas)
        com = [k for k in self.por_dado if self.dados[k].get("m2_12")]
        mais_vendas = sorted(com, key=lambda k: -self.dados[k]["n12"])[:5]
        caros = [k for k in sorted(com, key=lambda k: -self.dados[k]["m2_12"]) if self.dados[k]["n12"] >= 30 and k not in mais_vendas][:5]
        # marcadores numerados (no celular, nome escrito em cima do mapa fica ilegível); a lista vem embaixo
        marcas, lista = [], []
        fs = 17
        for i, k in enumerate(mais_vendas + caros, 1):
            b = max(self.por_dado[k], key=lambda b: (b["bb"][2] - b["bb"][0]) * (b["bb"][3] - b["bb"][1]))
            x, y = b["cxy"]
            cls = "rot-c" if k in caros else "rot-v"
            marcas.append(f'<g class="num-m {cls}"><circle cx="{x:.1f}" cy="{y:.1f}" r="{fs * 0.78:.1f}"/>'
                          f'<text x="{x:.1f}" y="{y + fs * 0.36:.1f}" text-anchor="middle" font-size="{fs:.0f}">{i}</text></g>')
            dd = self.dados[k]
            lista.append(f'<li class="{cls}"><b>{i}</b><a href="{u(f"/{self.s}/{slug(dd["nome"])}/")}">{esc(nome_bonito(dd["nome"]))}</a>'
                         f'<span>R$ {nf(dd["m2_12"])}/m² · {nf(dd["n12"])} vendas</span></li>')
        rot = "".join(marcas)
        lista_html = (f'<div class="mapa-lista"><div><h3>Mais vendas</h3><ol>{"".join(lista[:len(mais_vendas)])}</ol></div>'
                      f'<div><h3>Mais caros</h3><ol>{"".join(lista[len(mais_vendas):])}</ol></div></div>') if lista else ""
        nome = self.c["nome"]
        return f"""<section class="card" id="mapa"><h2>Mapa do preço do m² {esc(em_(nome))}</h2>
<p class="small">Quanto mais escuro, mais caro o metro quadrado (mediana dos últimos 12 meses). Os números marcam os 5 bairros com mais vendas e os 5 mais caros. Toque num bairro para abrir a página dele.</p>
<div class="mapa-m2"><svg viewBox="0 0 {self.W} {self.H:.0f}" role="img" aria-label="Mapa do preço do metro quadrado por bairro {esc(em_(nome))}">{PADRAO_SD}{"".join(partes)}<g class="rotulos">{rot}</g></svg></div>
{self.legenda()}
{lista_html}
{self.credito(f" {sum(1 for b in self.areas if b['k'] in self.par)} de {len(self.areas)} áreas com dados.")}</section>"""

    def bairro_html(self, k) -> str:
        if not self.ok or k not in self.por_dado:
            return ""
        meus = self.por_dado[k]
        bx0 = min(b["bb"][0] for b in meus); by0 = min(b["bb"][1] for b in meus)
        bx1 = max(b["bb"][2] for b in meus); by1 = max(b["bb"][3] for b in meus)
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        # janela: 3 vezes o tamanho do bairro, no mínimo 1/6 da largura da cidade, proporção entre 4:3 e 1:1
        lado = max(bx1 - bx0, by1 - by0) * 3
        lado = max(lado, self.W / 6)
        w, h = lado, lado * 0.8
        vx, vy = cx - w / 2, cy - h / 2
        vis = [b for b in self.areas if not (b["bb"][2] < vx or b["bb"][0] > vx + w or b["bb"][3] < vy or b["bb"][1] > vy + h)]
        partes = [self.area_svg(b, dec=2) for b in vis if b not in meus] + [self.area_svg(b, dec=2, destaque=True) for b in meus]
        fs = w / 640 * 21
        # nome do próprio bairro primeiro; depois os vizinhos com dados mais próximos
        dd = self.dados[k]
        grande = max(meus, key=lambda b: (b["bb"][2] - b["bb"][0]) * (b["bb"][3] - b["bb"][1]))
        itens = [(grande["cxy"][0] - vx, grande["cxy"][1] - vy, nome_bonito(dd["nome"]), "rot-eu")]
        viz = []
        for b in vis:
            kk = self.par.get(b["k"])
            if b in meus or not kk or not self.dados[kk].get("m2_12"):
                continue
            x, y = b["cxy"]
            if vx < x < vx + w and vy < y < vy + h:
                viz.append(((x - cx) ** 2 + (y - cy) ** 2, x - vx, y - vy, nome_bonito(self.dados[kk]["nome"])))
        vistos = set()
        for _, x, y, t in sorted(viz)[:12]:
            if t not in vistos:
                vistos.add(t)
                itens.append((x, y, t, "rot-v"))
        rot = self.rotulos(itens, fs, (w, h))
        nome_b = nome_bonito(dd["nome"])
        return f"""<section class="card" id="mapa"><h2>{esc(nome_b)} e os bairros vizinhos</h2>
<p class="small">Quanto mais escuro, mais caro o metro quadrado. Toque num vizinho para comparar.</p>
<div class="mapa-m2 zoom"><svg viewBox="{vx:.1f} {vy:.1f} {w:.1f} {h:.1f}" role="img" aria-label="Mapa de {esc(nome_b)} e dos bairros vizinhos">{PADRAO_SD}{"".join(partes)}<g class="rotulos" transform="translate({vx:.1f} {vy:.1f})">{rot}</g></svg></div>
{self.legenda()}
{self.credito(f' <a href="{u("/" + self.s + "/#mapa")}">Ver o mapa da cidade inteira</a>.')}</section>"""


# ---------------------------------------------------------------- entorno (o que tem em volta)
ENTORNO = RAIZ / "data" / "entorno"
ITENS_ENTORNO = [  # categoria, rótulo, tipo ("n" = quantos num raio de 1 km; "d" = quantos e quais, pelo nome)
    ("escolas", "Escolas e creches", "n"),
    ("saude", "Hospitais, clínicas e postos de saúde", "n"),
    ("mercados", "Supermercados e atacarejos", "n"),
    ("farmacias", "Farmácias", "n"),
    ("restaurantes", "Restaurantes, bares e cafés", "n"),
    ("parques", "Parques e praças", "n"),
    ("onibus", "Pontos de ônibus", "n"),
    ("estacoes", "Estações de metrô, trem ou BRT", "d"),
    ("shoppings", "Shoppings", "d"),
]


# Para morar, basta ter o suficiente perto: a partir daqui (a até 1 km), mais não melhora o bairro no ranking.
BASTA = {"escolas": 3, "saude": 2, "mercados": 2, "farmacias": 2, "restaurantes": 5, "parques": 2, "onibus": 5}

PESOS_PADRAO = {"escolas": 3, "saude": 2, "mercados": 2, "farmacias": 1, "restaurantes": 1, "parques": 2,
                "onibus": 1, "estacoes": 2, "shoppings": 1, "renda": 3}
RANKING = True
PARTE_RENDA = 0.2167  # cada ponto do controle "renda" = ~22% da nota (3 = 65%); o resto é a estrutura
ROTULO_CURTO = {"escolas": "Escolas e creches", "saude": "Saúde", "mercados": "Supermercados", "farmacias": "Farmácias",
                "restaurantes": "Restaurantes e bares", "parques": "Parques e praças", "onibus": "Pontos de ônibus",
                "estacoes": "Metrô, trem ou BRT", "shoppings": "Shoppings", "renda": "Renda dos moradores"}


def _dist(a, b):
    import math
    dx = (a[0] - b[0]) * 111320 * math.cos(math.radians(a[1]))
    dy = (a[1] - b[1]) * 110540
    return math.hypot(dx, dy)


GEO = {}  # cidade: (centros, contornos) dos bairros, preenchido por calcular_entorno
CENSO = RAIZ / "data" / "censo"


def calcular_censo(s, c) -> dict:
    """Renda dos moradores por bairro (Censo 2022): soma os setores censitários cujo ponto cai dentro do
    contorno do bairro; sem contorno, os setores a até 700 m do ponto do bairro.
    {chave: {"renda": média mensal dos responsáveis, "pessoas": moradores (só com contorno), "p": percentil}}
    e "_cidade": renda da cidade toda."""
    f = CENSO / f"{s}.json"
    if not f.exists() or s not in GEO:
        return {}
    import numpy as np
    d = json.loads(f.read_text(encoding="utf-8"))
    A = np.array([[x[0], x[1], x[2], x[4] or 0, x[5] or 0] for x in d["setores"]], dtype=float)
    centros, poligonos = GEO[s]
    out = {}
    for k, ctr in centros.items():
        aneis = poligonos.get(k)
        if aneis:
            xs = [x for a in aneis for x, _ in a]
            ys = [y for a in aneis for _, y in a]
            sel = np.where((A[:, 0] >= min(xs)) & (A[:, 0] <= max(xs)) & (A[:, 1] >= min(ys)) & (A[:, 1] <= max(ys)))[0]
            idx = [i for i in sel if _dentro((A[i, 0], A[i, 1]), aneis)]
        else:
            kx = 111320 * np.cos(np.radians(ctr[1]))
            dd = ((A[:, 0] - ctr[0]) * kx) ** 2 + ((A[:, 1] - ctr[1]) * 110540) ** 2
            idx = list(np.where(dd <= 700 ** 2)[0])
        if not idx:
            continue
        B = A[idx]
        resp = B[:, 3].sum()
        if resp < 150:  # poucos domicílios: média instável
            continue
        out[k] = {"renda": float((B[:, 3] * B[:, 4]).sum() / resp), "pessoas": int(B[:, 2].sum()) if aneis else None}
    vals = sorted(v["renda"] for v in out.values())
    for v in out.values():
        menos = sum(1 for x in vals if x < v["renda"])
        v["p"] = menos / max(len(vals) - 1, 1)
    out["_cidade"] = float((A[:, 3] * A[:, 4]).sum() / A[:, 3].sum())
    return out


def calcular_entorno(s, c, mapa) -> dict:
    """{chave do bairro: {categoria: (valor, percentil, nome)}}; percentil = parte dos bairros da cidade que
    ficam atrás deste (menos itens, ou mais longe)."""
    f = ENTORNO / f"{s}.json"
    if not f.exists():
        return {}
    ent = json.loads(f.read_text(encoding="utf-8"))
    cats = dict(ent.get("cat", {}))
    # "shop=mall" no OpenStreetMap inclui galerias pequenas: para "shopping mais próximo", só os com nome de shopping
    import re as _re
    cats["shoppings"] = [p for p in cats.get("shoppings", [])
                         if len(p) > 2 and _re.search(r"shopping|mall|plaza|outlet|center|centre", p[2], _re.I)
                         and not _re.match(r"\s*(condom[ií]nio|edif[ií]cio|residencial)", p[2], _re.I)
                         and not _re.search(r"estacionamento|parking", p[2], _re.I)]
    # centro de cada bairro: ponto central do contorno; sem contorno, o ponto com o nome do bairro no OSM
    centros, poligonos = {}, {}
    if mapa.ok:
        for k, bs in mapa.por_dado.items():
            b = max(bs, key=lambda b: (b["bb"][2] - b["bb"][0]) * (b["bb"][3] - b["bb"][1]))
            centros[k] = tuple(b["c"])
            poligonos[k] = [a for b2 in bs for a in b2["p"]]
    lugares = {}
    for lon, lat, nome in ent.get("lugares", []):
        lugares.setdefault(chave_bairro_site(nome), (lon, lat))
    for k in c["bairros"]:
        if k not in centros and k in lugares:
            centros[k] = lugares[k]
    GEO[s] = (centros, poligonos)
    if len(centros) < 10:
        return {}
    # Pontos de amostra espalhados pelo bairro (uma grade de ~300 m dentro do contorno). Para cada item,
    # contamos o que há a até 1 km de cada ponto e tiramos a média: o tamanho do bairro não pesa, e um
    # bairro grande não depende de um único "centro". Sem contorno, só o ponto do bairro.
    import numpy as np
    arr = {cat: np.array([(p[0], p[1]) for p in cats[cat]], dtype=float) for cat, _, _ in ITENS_ENTORNO if cats.get(cat)}
    brutos, sufs = {}, {}
    for k, ctr in centros.items():
        aneis = poligonos.get(k)
        amostra = _amostra(aneis, ctr) if aneis else [ctr]
        S = np.array(amostra, dtype=float)
        kx = 111320 * np.cos(np.radians(ctr[1]))
        x0, x1 = S[:, 0].min() - 0.011, S[:, 0].max() + 0.011
        y0, y1 = S[:, 1].min() - 0.01, S[:, 1].max() + 0.01
        r, suf = {}, {}
        for cat, _, tipo in ITENS_ENTORNO:
            P = arr.get(cat)
            if P is None:
                continue
            sel = (P[:, 0] >= x0) & (P[:, 0] <= x1) & (P[:, 1] >= y0) & (P[:, 1] <= y1)
            Q = P[sel]
            if len(Q):
                dx = (S[:, 0:1] - Q[None, :, 0]) * kx
                dy = (S[:, 1:2] - Q[None, :, 1]) * 110540
                perto = (dx * dx + dy * dy) <= 1000 * 1000
                por_ponto = perto.sum(axis=1)
            else:
                por_ponto = np.zeros(len(S))
            if tipo == "n":
                r[cat] = (float(por_ponto.mean()), None, "")
                suf[cat] = float(np.minimum(por_ponto / BASTA[cat], 1).mean())
                continue
            # estações e shoppings: quais ficam no bairro (pelo nome, sem repetir a mesma marcada em vários
            # pontos) e que parte do bairro fica a até 1 km de um deles (é isso que entra na comparação)
            pts = cats[cat]
            if aneis:
                dentro = [p for p in pts if _dentro(p, aneis)]
                modo = "dentro"
            else:
                dentro = [p for p in pts if _dist(ctr, p) <= 1000]
                modo = "1km"
            dentro.sort(key=lambda p: _dist(ctr, p))
            nomes, vistos = [], set()
            for p in dentro:
                nm = limpa_nome(p[2] if len(p) > 2 else "")
                ch = chave_bairro_site(nm) if _nome_ok(nm) else None
                if ch and ch not in vistos:
                    vistos.add(ch)
                    nomes.append(nm)
            info = {"nomes": nomes, "modo": modo, "qtd": len(nomes) if nomes else len(dentro),
                    "cobre": float((por_ponto > 0).mean())}
            suf[cat] = info["cobre"]
            if not dentro:
                bons = [p for p in pts if _nome_ok(limpa_nome(p[2] if len(p) > 2 else ""))] or pts
                melhor = min(bons, key=lambda p: _dist(ctr, p))
                info["mais_proxima"] = limpa_nome(melhor[2] if len(melhor) > 2 else "")
            r[cat] = (info["cobre"], None, info)
        brutos[k] = r
        sufs[k] = suf
    out = {k: {"_suf": sufs[k]} for k in brutos}
    for cat, _, tipo in ITENS_ENTORNO:
        grupos = {}
        for k in brutos:
            if cat in brutos[k]:
                nome = brutos[k][cat][2]
                grupos.setdefault(nome.get("modo") if isinstance(nome, dict) else "", []).append(brutos[k][cat][0])
        for k in brutos:
            if cat not in brutos[k]:
                continue
            v, _, nome = brutos[k][cat]
            vals = grupos[nome.get("modo") if isinstance(nome, dict) else ""]
            if len(vals) < 10:
                continue
            atras = sum(1 for x in vals if x < v) + 0.5 * (sum(1 for x in vals if x == v) - 1)
            out[k][cat] = (v, atras / max(len(vals) - 1, 1), nome)
    return out


def _amostra(aneis, ctr, alvo=300):
    """Grade de pontos dentro do contorno, de ~300 m (mais espaçada em bairros enormes)."""
    import math
    xs = [x for a in aneis for x, _ in a]
    ys = [y for a in aneis for _, y in a]
    kx = math.cos(math.radians(ctr[1]))
    larg = (max(xs) - min(xs)) * 111320 * kx
    alt = (max(ys) - min(ys)) * 110540
    passo = max(300.0, math.sqrt(larg * alt / alvo))
    dx, dy = passo / (111320 * kx), passo / 110540
    pts = []
    y = min(ys) + dy / 2
    while y < max(ys):
        x = min(xs) + dx / 2
        while x < max(xs):
            if _dentro((x, y), aneis):
                pts.append((x, y))
            x += dx
        y += dy
    return pts or [ctr]


def _dentro(p, aneis) -> bool:
    """Ponto dentro do contorno (regra par-ímpar, vale para buracos e várias partes)."""
    x, y = p[0], p[1]
    d = False
    for a in aneis:
        n = len(a)
        for i in range(n):
            x1, y1 = a[i]
            x2, y2 = a[i - 1]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                d = not d
    return d


def _nome_ok(nm: str) -> bool:
    """Nome que serve para mostrar ("Move", "BRT", "Estação 2" não dizem qual é)."""
    return bool(nm) and not re.fullmatch(r"(move|brt|esta[çc][ãa]o|terminal)?\s*\d*", nm.strip(), flags=re.I)


def limpa_nome(nm: str) -> str:
    """'Estação AACD-Servidor;AACD – Servidor' -> 'AACD-Servidor'."""
    nm = (nm or "").split(";")[0].strip()
    nm = re.sub(r"^(Estação|Estacao|Station)\s+", "", nm, flags=re.I)
    nm = nm.split(" / ")[0].strip()  # Rio: "Cantagalo / Copacabana" -> "Cantagalo"
    return nm


def chave_bairro_site(nome):
    import importlib
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent))
    return importlib.import_module("atualizar").chave_bairro(nome)


def entorno_html(ind: dict, nome_b: str, nome_c: str, s: str, pos=None, url_rank="") -> str:
    if not ind:
        return ""
    poli = any(isinstance(ind[c][2], dict) and ind[c][2].get("modo") == "dentro" for c in ("estacoes", "shoppings") if c in ind)
    linhas = []
    for cat, rot, tipo in ITENS_ENTORNO:
        if cat not in ind:
            continue
        v, p, nome = ind[cat]
        if tipo == "n":
            val = nf(round(v))
            rot = f"{rot}<small>{'média a até 1 km' if poli else 'a até 1 km do ponto do bairro'}</small>"
            if p >= 0.999:
                comp = "o maior número entre os bairros"
            elif p <= 0.001:
                comp = "o menor número entre os bairros"
            else:
                comp = f"mais que {min(int(p * 100), 99)}% dos bairros" if p >= 0.5 else f"menos que {min(int((1 - p) * 100), 99)}% dos bairros"
        else:
            info = nome or {}
            val = nf(info.get("qtd", 0))
            fem = cat != "shoppings"
            um = "uma estação" if fem else "um shopping"
            if info.get("nomes"):
                ns = info["nomes"]
                lista = ", ".join(ns[:4]) + (f" e mais {len(ns) - 4}" if len(ns) > 4 else "")
                rot = f"{rot}<small>{esc(lista)}</small>"
            elif info.get("mais_proxima"):
                onde = "no bairro" if info.get("modo") == "dentro" else "a até 1 km"
                rot = f"{rot}<small>Nenhuma {onde}; a mais próxima é {esc(info['mais_proxima'])}</small>" if fem \
                    else f"{rot}<small>Nenhum {onde}; o mais próximo é o {esc(info['mais_proxima'])}</small>"
            if v <= 0:
                rank = "como a maioria dos bairros" if p >= 0.25 else "menos que a maioria dos bairros"
            elif p >= 0.5:
                rank = f"mais que {min(int(p * 100), 99)}% dos bairros"
            else:
                rank = f"menos que {min(int((1 - p) * 100), 99)}% dos bairros"
            if info.get("modo") == "dentro":
                pct = round(v * 100)
                cob = f"nenhuma parte do bairro fica a até 1 km de {um}" if pct == 0 else \
                      (f"todo o bairro fica a até 1 km de {um}" if pct >= 100 else f"{pct}% do bairro fica a até 1 km de {um}")
                comp = f"{cob} · {rank}"
            else:
                comp = rank
        linhas.append(f'<li><div class="en-t"><span>{rot}</span><b class="num">{val}</b></div>'
                      f'<div class="en-b"><i style="width:{max(p * 100, 2):.0f}%"></i></div><span class="en-c">{comp}</span></li>')
    if not linhas:
        return ""
    dentro = any(isinstance(ind[c][2], dict) and ind[c][2].get("modo") == "dentro" for c in ("estacoes", "shoppings") if c in ind)
    if dentro:
        intro = ("Nada aqui é contado só dentro do bairro, senão bairro grande ganharia por ser grande. Medimos o que "
                 "fica a até 1 km (em linha reta) de pontos espalhados pelo bairro inteiro e tiramos a média. Em estações e shoppings, a comparação "
                 "é por quanto do bairro fica a até 1 km de um deles; os nomes são os que ficam dentro do bairro.")
    else:
        intro = "Quantos há a até 1 km do ponto do bairro (estações e shoppings: quantos e quais)."
    return f"""<section class="card" id="entorno"><h2>O que tem em volta de {esc(nome_b)}</h2>
<p class="small">{intro} Comparado com os outros bairros {esc(de_(nome_c))}: quanto mais cheia a barra, melhor o bairro está nesse item.</p>
<ul class="entorno">{"".join(linhas)}</ul>
{f'<p class="rank-pos">No ranking de melhores bairros para morar, <b>{pos[0]}º de {pos[1]} bairros</b> {esc(de_(nome_c))}. <a href="{url_rank}">Ver o ranking</a></p>' if pos else ''}
<p class="small">Fonte: © colaboradores do <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap</a>, mapa colaborativo: pode faltar algum estabelecimento, mas a falta tende a ser parecida entre bairros da mesma cidade.{"" if dentro else " Este bairro não tem contorno no mapa; usamos o ponto que o OpenStreetMap marca com o nome dele."}</p></section>"""


# ---------------------------------------------------------------- ITBI: regras de cada prefeitura (conferidas em nov/2026)
# geral: alíquota padrão (%). fin: redução para a parte financiada (taxa sobre o financiado; resto = alíquota sobre o restante;
# teto_fin = limite do valor financiado com a taxa menor; teto_imovel = valor máximo do imóvel para ter a redução).
ITBI_REGRAS = {
    "sao-paulo": {"geral": 3, "fin": {"taxa": 0.5, "resto": 3, "teto_fin": 120968, "teto_imovel": 725808,
                                      "quando": "financiamento pelo SFH, PAR, HIS ou consórcio, com imóvel de até R$ 725.808 (valores de 2026)"},
                  "url": "https://prefeitura.sp.gov.br/web/fazenda/w/servicos/itbi/2513",
                  "nota": "A prefeitura usa como base o maior valor entre o preço da compra e o valor venal de referência dela."},
    "rio-de-janeiro": {"geral": 3, "fin": None, "url": "https://carioca.rio/servicos/itbi-duvidas-sobre-avaliacao-interpretacao-e-aplicacao-da-legislacao-tributaria/",
                       "nota": "A alíquota é de 3% desde 2018. Há reduções para casos específicos, como famílias de baixa renda; confira na prefeitura se a sua compra se enquadra."},
    "belo-horizonte": {"geral": 3, "fin": None, "url": "https://prefeitura.pbh.gov.br/fazenda/tributos/itbi",
                       "nota": "A alíquota é de 3% desde maio de 2014. Há isenções para casos específicos; confira na prefeitura."},
    "fortaleza": {"geral": 3, "fin": {"taxa": 0.5, "resto": 2, "teto_fin": None, "teto_imovel": None,
                                      "quando": "financiamento pelo SFH: 0,5% sobre o valor financiado e 2% sobre o restante"},
                  "url": "https://www.sefin.fortaleza.ce.gov.br/",
                  "nota": "Regra da Lei Municipal 9.133/2006: nas compras pelo SFH, 0,5% sobre o financiado e 2% sobre o resto; nas demais, 3%."},
    "recife": {"geral": 3, "fin": {"taxa": 1, "resto": 3, "teto_fin": None, "teto_imovel": None,
                                   "quando": "financiamento pelo SFH: 1% sobre o valor financiado"},
               "url": "https://recifeemdia.recife.pe.gov.br/",
               "nota": "O Recife já teve alíquota menor por tempo limitado (2% até jan/2026) e alíquota de 1,8% para quem paga antes; as regras mudaram em 2026 (Lei 19.490), então confira na prefeitura antes de pagar."},
    "porto-alegre": {"geral": 3, "fin": {"taxa": 0.5, "resto": 3, "teto_fin": 410795, "teto_imovel": None,
                                         "quando": "financiamento imobiliário residencial de pelo menos 5 anos, consórcio ou FGTS, até 68.000 UFM (R$ 410.795 em 2026)"},
                     "url": "https://prefeitura.poa.br/carta-de-servicos/imposto-sobre-transmissao-de-bens-imoveis-itbi",
                     "nota": "A prefeitura usa como base o maior valor entre o preço da compra e o valor venal que ela apura."},
}


def itbi_calc(regra: dict, valor: float, financiado: float = 0) -> float:
    """Mesma conta da calculadora em JavaScript (imoveis.js)."""
    f = regra.get("fin")
    if not f or not financiado or (f.get("teto_imovel") and valor > f["teto_imovel"]):
        return valor * regra["geral"] / 100
    fin = min(financiado, valor, f["teto_fin"] or financiado)
    return fin * f["taxa"] / 100 + (valor - fin) * f["resto"] / 100


def itbi_caixa(regras: dict, s0: str = "") -> str:
    """Calculadora: escolhe a cidade, digita o valor e, se for o caso, quanto vai financiar."""
    opts = "".join(f'<option value="{k}"{" selected" if k == s0 else ""}>{esc(NOMES_CIDADE.get(k, k))}</option>' for k in regras)
    dados = esc(json.dumps(regras, ensure_ascii=False, separators=(",", ":")))
    return f"""<div class="itbi" data-itbi="{dados}">
<label>Cidade<select name="cidade">{opts}</select></label>
<label>Valor do imóvel (R$)<input type="text" inputmode="numeric" name="valor" placeholder="500.000" autocomplete="off"></label>
<label class="itbi-fin">Valor financiado (R$), se houver<input type="text" inputmode="numeric" name="fin" placeholder="0" autocomplete="off"></label>
<div class="itbi-res" aria-live="polite"><p>Digite o valor do imóvel.</p></div>
</div>"""


# ---------------------------------------------------------------- página
NAV = [("/", "Início")]


def familia_html() -> str:
    itens = []
    for nome, tema, url, cor in FAMILIA:
        miolo = f'<span class="ponto" style="background:{cor}"></span><span><b>{nome}</b> {tema}</span>'
        itens.append(f'<li>{miolo} <em>você está aqui</em></li>' if nome == ATUAL else f'<li><a href="{url}">{miolo}</a></li>')
    return ('<div class="familia"><p><b>Família em Números</b> · portais independentes que organizam dados públicos do Brasil · '
            '<a href="https://x.com/familianumeros" rel="noopener" target="_blank">Siga no X</a> · '
            '<a href="https://www.instagram.com/familiaemnumeros/" rel="noopener" target="_blank">Siga no Instagram</a> · '
            '<a href="https://www.linkedin.com/company/familiaemnumeros/" rel="noopener" target="_blank">Siga no LinkedIn</a></p>'
            f'<ul>{"".join(itens)}</ul></div>')


class Site:
    def __init__(self):
        self.cidades: dict[str, dict] = {}
        for s in ORDEM:
            f = DADOS / f"{s}.json"
            if f.exists():
                self.cidades[s] = json.loads(f.read_text(encoding="utf-8"))
        self.gerado = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3)))
        self.paginas: list[str] = []
        self.busca: list = []

    def nav(self, ativo):
        itens = [("/", "Início")] + [(f"/{s}/", c["nome"]) for s, c in self.cidades.items()] + [("/financiamento/", "Simular financiamento"), ("/itbi/", "Calculadora de ITBI"), ("/sobre/", "Como funciona")]
        return "".join(f'<a href="{u(h)}"' + (' aria-current="page"' if h == ativo else "") + f">{esc(t)}</a>" for h, t in itens)

    def pagina(self, caminho, titulo, descricao, corpo, ativo="", migalhas=None, jsonld=None, media=False) -> None:
        if media:
            def m(t):
                for a, b_ in (("medianos", "médios"), ("mediano", "médio"), ("medianas", "médias"), ("mediana", "média"),
                              ("Mediana", "Média")):
                    t = t.replace(a, b_)
                return t
            titulo, descricao, corpo = m(titulo), m(descricao), m(corpo)
            jsonld = json.loads(m(json.dumps(jsonld, ensure_ascii=False))) if jsonld else jsonld
        bc = ""
        lds = list(jsonld or [])
        if migalhas:
            partes = [f'<a href="{u("/")}">Início</a>'] + [f'<a href="{u(h)}">{esc(t)}</a>' if h else esc(t) for h, t in migalhas]
            bc = '<nav class="bc" aria-label="Você está em">' + " › ".join(partes) + "</nav>"
            itens = [{"@type": "ListItem", "position": 1, "name": "Início", "item": URL + "/"}]
            for i, (h, t) in enumerate(migalhas, 2):
                itens.append({"@type": "ListItem", "position": i, "name": t, "item": URL + (h or caminho)})
            lds.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": itens})
        ld = "".join(f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>' for x in lds)
        v = self.gerado.strftime("%Y%m%d%H")
        robots = '<meta name="robots" content="noindex, nofollow">' if PREVIA else ""
        faixa = ('<div class="previa"><div><b>Prévia.</b> Esta versão ainda não foi lançada; os números já são os dados reais das prefeituras.</div></div>'
                 if PREVIA else "")
        doc = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(titulo)}</title>
<meta name="description" content="{esc(descricao)}">
{robots}
<link rel="canonical" href="{URL + caminho}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Imóveis em Números">
<meta property="og:title" content="{esc(titulo)}">
<meta property="og:description" content="{esc(descricao)}">
<meta property="og:url" content="{URL + caminho}">
<meta property="og:locale" content="pt_BR">
<meta name="theme-color" content="#7A52C7">
<link rel="icon" href="{u('/favicon.svg')}" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{u('/assets/estilo.css')}?v={v}">
{ld}
</head>
<body>
{faixa}
<header class="top"><div class="top-in">
<a class="brand" href="{u('/')}" aria-label="Imóveis em Números, início">{LOGO}<span style="color:var(--ink)">Imóveis <span>em Números</span></span></a>
<nav class="main" aria-label="Seções">{self.nav(ativo)}</nav>
</div></header>
<div class="info-bar"><div><strong>Preço real, não preço de anúncio:</strong> vendas registradas no ITBI das prefeituras. Atualizado automaticamente em {self.gerado.strftime("%d/%m/%Y")}.</div></div>
<main>
{bc}
{corpo}
</main>
<footer><div>
<span><strong>Imóveis em Números</strong> · versão beta</span>
<span>Compras de apartamentos e casas registradas no ITBI (imposto pago na compra de imóvel), a partir dos dados abertos de cada prefeitura. Valores em reais da época, sem correção pela inflação.</span>
<span>{" · ".join(f'<a href="{u("/" + s + "/")}">{esc(c["nome"])}</a>' for s, c in self.cidades.items())} · <a href="{u('/sobre/')}">Como funciona</a> · <a href="{u('/contato/')}">Contato</a> · <a href="{u('/privacidade/')}">Privacidade</a></span>
</div>{familia_html()}</footer>
<script src="{u('/assets/familia.js')}?v={v}" defer></script>
<script src="{u('/assets/familia-graficos.js')}?v={v}" defer></script>
<script src="{u('/assets/imoveis.js')}?v={v}" defer></script>
<script src="{u('/assets/familia-busca.js')}?v={v}" data-indice="{u('/busca.json')}?v={v}" data-dica="Bairro ou cidade (Savassi, Boa Viagem...)" defer></script>
{GOAT}
</body>
</html>
"""
        destino = SAIDA / caminho.strip("/") / "index.html" if caminho != "/" else SAIDA / "index.html"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(doc, encoding="utf-8")
        self.paginas.append(caminho)

    # ------------------------------------------------------------ início
    def inicio(self):
        cards = []
        for s, c in self.cidades.items():
            ci = c["cidade"]
            t = termometro(ci["n"], c["meses"])
            vm = var(ci.get("m2_12"), ci.get("m2_12_ant"))
            cards.append(f"""<a href="{u('/' + s + '/')}"><h3>{esc(c['nome'])}</h3>
<span class="big num">R$ {nf(ci.get('m2_12'))}<small class="s">/m²</small></span>
<span class="s">metro quadrado mediano, últimos 12 meses {('· ' + seta(vm)) if vm is not None else ''}</span>
<span class="s num">{nf(ci.get('n12'))} vendas em 12 meses · {len(c['bairros'])} bairros</span>
{termo_html(t)}</a>""")
        corpo = f"""<section class="hero">
<span class="kicker">Imóveis em Números</span>
<h1>Quanto os imóveis estão sendo vendidos de verdade</h1>
<p class="lead">Preço de anúncio é o que o vendedor pede. Aqui está o que foi <strong>registrado na compra</strong>: cada venda de apartamento e casa que pagou o ITBI na prefeitura, organizada por cidade e bairro, mês a mês.</p>
</section>
<section><div class="cidades">{"".join(cards)}</div></section>
<section class="grid2">
<div class="card"><h2>O que você encontra</h2><ul>
<li><b>Preço do m² por bairro</b>, com a curva de todas as vendas: dá para ver se um anúncio está caro ou barato.</li>
<li><b>Mercado aquecendo ou esfriando</b>: vendas dos últimos 3 meses contra os mesmos meses do ano anterior.</li>
<li><b>Mês a mês</b>: quantidade de vendas, dinheiro movimentado e preço do m².</li>
</ul></div>
<div class="card"><h2>De onde vêm os números</h2>
<p>Toda compra de imóvel paga o ITBI à prefeitura. Algumas prefeituras publicam essas guias como dados abertos, sem nome de comprador ou vendedor. O robô do site baixa as bases, separa as compras de apartamentos e casas e calcula as medianas. <a href="{u('/sobre/')}">Veja como funciona</a>.</p>
<p class="small">Hoje: {", ".join(c["nome"] for c in self.cidades.values())}. Outras capitais entram quando abrirem os dados.</p></div>
</section>"""
        self.pagina("/", "Imóveis em Números: preço real do m² por bairro, pelas vendas do ITBI",
                    "Preço real dos imóveis por bairro em " + ", ".join(c["nome"] for c in self.cidades.values())
                    + ": metro quadrado mediano, vendas mês a mês e mercado aquecendo ou esfriando, com dados do ITBI das prefeituras.",
                    corpo, ativo="/")

    # ------------------------------------------------------------ cidade
    def cidade(self, s, c):
        ci = c["cidade"]
        meses = c["meses"]
        ult = c["ultimo_mes"]
        vtxt = VALOR_TXT[c["valor"]]
        t = termometro(ci["n"], meses)
        vm = var(ci.get("m2_12"), ci.get("m2_12_ant"))
        vn = var(ci.get("n12"), ci.get("n12_ant"))
        bairros = sorted(c["bairros"].items(), key=lambda kv: -kv[1]["n12"])
        nome = c["nome"]
        n_rank = self.ranking(s, c) if RANKING else 0

        tiles = '<div class="tiles">' + "".join([
            tile("m² mediano (12 meses)", f"R$ {nf(ci.get('m2_12'))}", (seta(vm) + " em 1 ano") if vm is not None else ""),
            tile("Vendas em 12 meses", nf(ci.get("n12")), (seta(vn) + " em 1 ano") if vn is not None else ""),
            tile("Preço mediano", brl_curto(ci.get("ticket12")), f"área mediana {nf(ci.get('area12'), 0)} m²" if ci.get("area12") else ""),
            tile("Dinheiro movimentado", brl_curto(ci.get("valor12")), "últimos 12 meses"),
        ]) + "</div>"

        for k, b in bairros:
            self.busca.append([f"{nome_bonito(b['nome'])} ({nome})", f"/{s}/{slug(b['nome'])}/", "Bairro"])

        def tabela_bairros(tid, lista, rotulo):
            """Tabela de bairros (todos os imóveis, só apartamentos ou só casas), com filtro e 'mostrar todos'."""
            ls = []
            for i_b, b in enumerate(lista):
                extra = ' class="mais" hidden' if i_b >= 40 else ""
                vb = var(b.get("m2_12"), b.get("m2_12_ant")) if (b.get("n12", 0) >= 30 and b.get("n12_ant", 0) >= 30) else None
                ls.append(f'<tr{extra}><td><a href="{u(f"/{s}/{slug(b["nome"])}/")}">{esc(nome_bonito(b["nome"]))}</a></td>'
                          f'<td class="r num">{nf(b.get("m2_12"))}</td><td class="r num">{seta(vb)}</td>'
                          f'<td class="r num">{nf(b["n12"])}</td><td class="r num m-esc">{brl_curto(b.get("ticket12"))}</td></tr>')
            return (f'<input class="filtro" type="search" placeholder="Filtrar bairro" aria-label="Filtrar bairro ({rotulo})" data-filtro="{tid}">'
                    f'<div class="tw"><table id="{tid}"><thead><tr><th>Bairro</th><th class="r">m² mediano</th><th class="r">Em 1 ano</th>'
                    f'<th class="r">Vendas (12 meses)</th><th class="r m-esc">Preço mediano</th></tr></thead><tbody>{"".join(ls)}</tbody></table></div>'
                    + (f'<button class="btn sec" type="button" data-mais="{tid}">Mostrar os {len(lista)} bairros</button>' if len(lista) > 40 else ""))

        todos_b = [b for _, b in bairros]
        por_t = {}
        for tp_ in ("apto", "casa"):
            lt = []
            for b in todos_b:
                d = (b.get("pt") or {}).get(tp_)
                if d:
                    lt.append({**d, "nome": b["nome"]})
            por_t[tp_] = sorted(lt, key=lambda x: -x["n12"])
        if por_t["apto"] or por_t["casa"]:
            abas = [("todos", "Todos", todos_b), ("apto", "Apartamentos", por_t["apto"]), ("casa", "Casas", por_t["casa"])]
            abas = [a for a in abas if a[2]]
            botoes = "".join(f'<button type="button" role="tab" data-aba="ab-{ta}" aria-selected="{"true" if i == 0 else "false"}">{r}</button>'
                             for i, (ta, r, _) in enumerate(abas))
            paineis = "".join(f'<div id="ab-{ta}" role="tabpanel"{"" if i == 0 else " hidden"}>{tabela_bairros("tab-" + ta, l, r.lower())}</div>'
                              for i, (ta, r, l) in enumerate(abas))
            tabela_html = f'<div class="abas" role="tablist">{botoes}</div>{paineis}'
            nota_tipo = " Nas abas Apartamentos e Casas, entram os bairros com pelo menos 10 vendas daquele tipo."
        else:
            tabela_html = tabela_bairros("tab-bairros", todos_b, "todos")
            nota_tipo = ""

        def top(lista, chave_ord, fmt, n=8, rev=True):
            itens = sorted(lista, key=chave_ord, reverse=rev)[:n]
            return "".join(f'<li><a href="{u(f"/{s}/{slug(b["nome"])}/")}">{esc(nome_bonito(b["nome"]))}</a><span>{fmt(b)}</span></li>' for b in itens)
        bl = [b for _, b in bairros if b["n12"] >= 30 and b.get("m2_12")]
        alta = [b for b in bl if b.get("m2_12_ant") and b.get("n12_ant", 0) >= 30]
        for b in alta:
            b["_v"] = b["m2_12"] / b["m2_12_ant"] - 1
        ranks = f"""<section class="grid2">
<div class="card"><h2>Bairros mais caros</h2><ol class="rank">{top(bl, lambda b: b["m2_12"], lambda b: f"R$ {nf(b['m2_12'])}/m²")}</ol></div>
<div class="card"><h2>Bairros mais em conta</h2><ol class="rank">{top(bl, lambda b: b["m2_12"], lambda b: f"R$ {nf(b['m2_12'])}/m²", rev=False)}</ol></div>
<div class="card"><h2>Onde o m² mais subiu</h2><ol class="rank">{top(alta, lambda b: b["_v"], lambda b: pct(b["_v"], 1, True))}</ol>
<p class="small">m² mediano dos últimos 12 meses contra os 12 anteriores; bairros com pelo menos 30 vendas em cada período.</p></div>
<div class="card"><h2>Onde mais se vende</h2><ol class="rank">{top(bl, lambda b: b["n12"], lambda b: f"{nf(b['n12'])} vendas")}</ol></div>
</section>"""

        tipos = c.get("por_tipo") or {}
        tipo_html = ""
        if tipos.get("apto", {}).get("n12") and tipos.get("casa", {}).get("n12"):
            a, cs = tipos["apto"], tipos["casa"]
            tipo_html = f"""<section class="card"><h2>Apartamento ou casa</h2>
<div class="tw"><table><thead><tr><th>Tipo</th><th class="r">m² mediano</th><th class="r">Preço mediano</th><th class="r">Área mediana</th><th class="r">Vendas (12 meses)</th></tr></thead><tbody>
<tr><td>Apartamentos</td><td class="r num">R$ {nf(a.get('m2_12'))}</td><td class="r num">{brl_curto(a.get('ticket12'))}</td><td class="r num">{nf(a.get('area12'), 0)} m²</td><td class="r num">{nf(a['n12'])}</td></tr>
<tr><td>Casas</td><td class="r num">R$ {nf(cs.get('m2_12'))}</td><td class="r num">{brl_curto(cs.get('ticket12'))}</td><td class="r num">{nf(cs.get('area12'), 0)} m²</td><td class="r num">{nf(cs['n12'])}</td></tr>
</tbody></table></div></section>"""

        extras = []
        if ci.get("financiado") is not None:
            extras.append(f"<li><b>{pct(ci['financiado'], 0)}</b> das compras dos últimos 12 meses tiveram financiamento bancário.</li>")
        if ci.get("base_acima") is not None:
            extras.append(f"<li>Em <b>{pct(ci['base_acima'], 0)}</b> das compras, a prefeitura considerou o imóvel mais valioso que o preço declarado e cobrou o ITBI sobre o valor dela.</li>")
        if ci.get("ano_med"):
            extras.append(f"<li>Metade dos imóveis vendidos foi construída antes de <b>{ci['ano_med']}</b>.</li>")
        if s in ITBI_REGRAS and ci.get("ticket12"):
            extras.append(f'<li>Vai comprar? No preço mediano ({brl_curto(ci["ticket12"])}), o ITBI à vista fica em cerca de '
                          f'<b>R$ {nf(itbi_calc(ITBI_REGRAS[s], ci["ticket12"]))}</b>. <a href="{u(f"/{s}/itbi/")}">Calcule o seu →</a> · '
                          f'<a href="{u("/financiamento/")}?valor={round(ci["ticket12"])}&amp;cidade={s}">Simule o financiamento →</a></li>')
        extras_html = f'<section class="card"><h2>Outros números {esc(de_(nome))}</h2><ul>{"".join(extras)}</ul></section>' if extras else ""

        curva = curva_html(ci, None, nome) if not c.get("agregado") else ""
        m2_mm = media_movel(ci["m2"])
        corpo = f"""<section class="hero">
<span class="kicker">{esc(nome)} · dados até {mes_nome(ult)}</span>
<h1>Preço real dos imóveis {esc(em_(nome))}</h1>
<p class="lead">Nos últimos 12 meses, {nf(ci.get('n12'))} apartamentos e casas foram vendidos {esc(em_(nome))}, com metro quadrado mediano de <strong>R$ {nf(ci.get('m2_12'))}</strong>{f" ({pct(vm, 1, True)} em um ano)" if vm is not None else ""}. {termo_html(t)}</p>
</section>
{tiles}
<section class="card"><h2>Vendas por mês</h2>{grafico_vendas(meses, ci['n'], f'Vendas de imóveis por mês {em_(nome)}')}
<p class="small">Compras de apartamentos e casas registradas no ITBI, pelo mês em que o imposto foi {'declarado' if c['valor'] == 'base' and s == 'fortaleza' else 'pago'}.</p></section>
<section class="grid2">
<div class="card"><h2>Preço do m² mês a mês</h2>{grafico_m2(meses, m2_mm, f'Metro quadrado mediano {em_(nome)}, média móvel de 3 meses')}
<p class="small">Mediana do m² de cada mês, em média móvel de 3 meses. Valor usado: {vtxt[0]}.</p></div>
<div class="card"><h2>Dinheiro movimentado</h2>{grafico_valor(meses, ci['valor'], f'Valor movimentado por mês {em_(nome)}')}</div>
</section>
{self.mapas[s].cidade_html()}
{f'<section class="card aviso"><div><h2>Melhores bairros para morar {esc(em_(nome))}</h2><p>Ranking de {n_rank} bairros pela renda dos moradores (Censo 2022) e pela estrutura perto de casa. Você escolhe o peso de cada item.</p></div><a class="btn" href="{u(f"/{s}/melhores-bairros/")}">Ver o ranking</a></section>' if n_rank else ''}
{curva}
<section class="card" id="bairros"><h2>Todos os bairros {esc(de_(nome))}</h2>
{tabela_html}
<p class="small">Últimos 12 meses. Entram os bairros com pelo menos 20 vendas desde {mes_nome(meses[0])}. A variação só aparece com 30 vendas ou mais em cada período.{nota_tipo}</p></section>
{ranks}
{tipo_html}
{extras_html}
<section class="card"><h2>Sobre estes números</h2>
<p>O valor de cada venda é {vtxt[1]}. Metro quadrado = valor ÷ área construída. Valores em reais da época, sem correção pela inflação.</p>
<p class="small">Fonte: <a href="{esc(c['fonte_url'])}" rel="noopener">{esc(c['fonte'])}</a>.</p></section>"""
        self.busca.append([f"{nome} (cidade)", f"/{s}/", "Cidade"])
        self.pagina(f"/{s}/", f"Preço do m² {em_(nome)} por bairro: vendas reais do ITBI",
                    f"Metro quadrado mediano {em_(nome)}: R$ {nf(ci.get('m2_12'))} nos últimos 12 meses, com {nf(ci.get('n12'))} vendas. "
                    f"Preço real por bairro, vendas mês a mês e mercado aquecendo ou esfriando, com dados do ITBI.",
                    corpo, ativo=f"/{s}/", migalhas=[(None, nome)], media=bool(c.get("agregado")))
        for k, b in bairros:
            self.bairro(s, c, b, k)

    # ------------------------------------------------------------ ranking
    def ranking(self, s, c) -> int:
        """Melhores bairros para morar: renda dos moradores (Censo 2022, posição entre os bairros da cidade)
        + estrutura perto de casa medida como "tem o suficiente?" (0 a 100%, sem premiar excesso).
        Pesos padrão em PESOS_PADRAO; a página deixa a pessoa mudar os pesos."""
        ent = self.entorno.get(s, {})
        cen = self.censo.get(s, {})
        cats = [cat for cat, _, _ in ITENS_ENTORNO if any(cat in ent.get(k, {}).get("_suf", {}) for k in ent)]
        if len(cats) < 5 or not cen:
            return 0
        eleg = [(k, b) for k, b in c["bairros"].items()
                if b.get("n12", 0) >= 30 and b.get("m2_12") and k in cen
                and all(cat in ent.get(k, {}).get("_suf", {}) for cat in cats)]
        if len(eleg) < 15:
            return 0
        # renda: posição só entre os bairros que entram no ranking
        rs = sorted(cen[k]["renda"] for k, _ in eleg)
        def p_renda(v):
            return (sum(1 for x in rs if x < v) + 0.5 * (sum(1 for x in rs if x == v) - 1)) / max(len(rs) - 1, 1)
        chaves = cats + ["renda"]
        linhas = []
        for k, b in eleg:
            ps = [ent[k]["_suf"][cat] for cat in cats] + [p_renda(cen[k]["renda"])]
            linhas.append({"k": k, "nome": nome_bonito(b["nome"]), "url": u(f"/{s}/{slug(b['nome'])}/"),
                           "m2": b["m2_12"], "renda": cen[k]["renda"], "p": [round(x, 3) for x in ps]})
        pesos = [PESOS_PADRAO[ch] for ch in chaves]
        def nota(p, w):
            we, wv = w[:-1], w[-1]
            estr = sum(a * b for a, b in zip(we, p[:-1])) / sum(we) if sum(we) else 0
            v = min(wv * PARTE_RENDA, 1) if sum(we) else 1
            return ((1 - v) * estr + v * p[-1]) * 100
        for ln in linhas:
            ln["nota"] = nota(ln["p"], pesos)
        linhas.sort(key=lambda ln: -ln["nota"])
        self.posicoes[s] = {ln["k"]: (i + 1, len(linhas)) for i, ln in enumerate(linhas)}
        nome = c["nome"]
        tab = []
        for i, ln in enumerate(linhas):
            extra = ' class="mais" hidden' if i >= 30 else ""
            tab.append(f'<tr{extra}><td class="num">{i + 1}</td><td><a href="{ln["url"]}">{esc(ln["nome"])}</a></td>'
                       f'<td class="r num"><b>{nf(ln["nota"])}</b></td><td class="r num">R$ {nf(ln["renda"])}</td>'
                       f'<td class="r num m-esc">R$ {nf(ln["m2"])}</td></tr>')
        ctl = "".join(
            f'<label class="peso"><span>{esc(ROTULO_CURTO[ch])}</span>'
            f'<input type="range" min="0" max="3" step="1" value="{PESOS_PADRAO[ch]}" data-i="{i}" aria-label="Peso de {esc(ROTULO_CURTO[ch])}">'
            f'<output>{PESOS_PADRAO[ch]}</output></label>' for i, ch in enumerate(chaves))
        dados = json.dumps([[ln["nome"], ln["url"], ln["m2"], ln["p"], round(ln["renda"])] for ln in linhas],
                           ensure_ascii=False, separators=(",", ":"))
        top3 = ", ".join(ln["nome"] for ln in linhas[:3])
        basta = "; ".join(f"{ROTULO_CURTO[c2].lower()}: {n}" for c2, n in BASTA.items())
        corpo = f"""<section class="hero">
<span class="kicker">{esc(nome)} · ranking</span>
<h1>Melhores bairros para morar {esc(em_(nome))}</h1>
<p class="lead">{len(linhas)} bairros ordenados pela renda dos moradores, do Censo 2022 do IBGE, e pela estrutura perto de casa: escola, saúde, mercado, parque e transporte. No peso padrão, os três primeiros são <strong>{esc(top3)}</strong>. Mude os pesos e o ranking muda na hora.</p>
</section>
<section class="card"><h2>O que pesa mais para você?</h2>
<p class="small">0 = não conta; 3 = conta muito.</p>
<div class="pesos" id="pesos">{ctl}</div>
<button class="btn sec" type="button" id="pesos-reset">Voltar ao padrão</button></section>
<section class="card"><h2>Ranking</h2>
<input class="filtro" type="search" placeholder="Achar um bairro" aria-label="Achar um bairro" data-filtro="tab-rank" data-col="1">
<div class="tw"><table id="tab-rank" data-rank='{esc(dados)}' data-pesos='{json.dumps(pesos)}' data-parte="{PARTE_RENDA}"><thead><tr><th>#</th><th>Bairro</th><th class="r">Pontos</th><th class="r">Renda média</th><th class="r m-esc">m² mediano</th></tr></thead>
<tbody>{"".join(tab)}</tbody></table></div>
<button class="btn sec" type="button" data-mais="tab-rank">Mostrar os {len(linhas)} bairros</button></section>
<section class="card"><h2>Como a conta é feita</h2>
<ul>
<li><b>Renda dos moradores:</b> renda média mensal de quem chefia os domicílios do bairro, no Censo 2022 do IBGE (divulgada em 2025). Somamos os setores censitários que ficam dentro do bairro. Entra pela posição do bairro na cidade: o de maior renda vale 100. Ela resume muito do que não tem dado aberto por bairro, como segurança e conservação das ruas.</li>
<li><b>Estrutura perto de casa:</b> para pontos espalhados pelo bairro, vemos se há o suficiente a até 1 km ({esc(basta)}; metrô, trem ou BRT e shopping: pelo menos um). Passando disso, mais não conta: dez padarias não fazem um bairro melhor que três. Vale de 0 a 100%.</li>
<li>No padrão (renda com peso 3), a renda vale 65% dos pontos e a estrutura, 35%. Cada ponto a menos no controle da renda tira 22% dela.</li>
<li>Entram os bairros com pelo menos 30 vendas em 12 meses, com renda calculada e com todos os itens de estrutura.</li>
<li><b>O que não entra diretamente:</b> segurança, barulho e qualidade das escolas, por falta de dado aberto comparável por bairro.</li>
<li>Fontes: IBGE, Censo Demográfico 2022; © colaboradores do <a href="https://www.openstreetmap.org/copyright" rel="noopener">OpenStreetMap</a>; preço: {esc(c['fonte'])}.</li>
</ul></section>"""
        self.busca.append([f"Melhores bairros para morar {em_(nome)}", f"/{s}/melhores-bairros/", "Ranking"])
        self.pagina(f"/{s}/melhores-bairros/", f"Melhores bairros para morar {em_(nome)}: ranking com dados do IBGE",
                    f"Ranking de {len(linhas)} bairros {de_(nome)} pela renda dos moradores (Censo 2022) e pela estrutura perto de casa: "
                    f"escola, saúde, mercado, parque e transporte. Escolha o peso de cada item.",
                    corpo, ativo=f"/{s}/", migalhas=[(f"/{s}/", nome), (None, "Melhores bairros")], media=bool(c.get("agregado")))
        return len(linhas)

    # ------------------------------------------------------------ bairro
    def bairro(self, s, c, b, chave_k):
        meses = c["meses"]
        nome_c = c["nome"]
        nb = nome_bonito(b["nome"])
        bs = slug(b["nome"])
        ci = c["cidade"]
        vtxt = VALOR_TXT[c["valor"]]
        t = termometro(b["n"], meses)
        vm = var(b.get("m2_12"), b.get("m2_12_ant")) if (b.get("n12", 0) >= 30 and b.get("n12_ant", 0) >= 30) else None
        rel = var(b.get("m2_12"), ci.get("m2_12"))
        tiles = '<div class="tiles">' + "".join([
            tile("m² mediano (12 meses)", f"R$ {nf(b.get('m2_12'))}", (seta(vm) + " em 1 ano") if vm is not None else ""),
            tile("Vendas em 12 meses", nf(b.get("n12")), termo_html(t)),
            tile("Preço mediano", brl_curto(b.get("ticket12")), f"área mediana {nf(b.get('area12'), 0)} m²" if b.get("area12") else ""),
            tile(f"Contra a média {de_(nome_c)}", pct(rel, 0, True) if rel is not None else "–", f"cidade: R$ {nf(ci.get('m2_12'))}/m²"),
        ]) + "</div>"
        frase_rel = ""
        if rel is not None:
            frase_rel = (f"{pct(abs(rel), 0)} {'acima' if rel > 0 else 'abaixo'} da mediana {esc(de_(nome_c))}" if abs(rel) >= 0.03
                         else f"praticamente igual à mediana {esc(de_(nome_c))}")
        q = b.get("q")
        faixa = (f" Metade das vendas ficou entre <strong>R$ {nf(q[1])}</strong> e <strong>R$ {nf(q[3])}</strong> por m²." if q else "")
        m2_mm = media_movel(b["m2"])
        extras = []
        cen = self.censo.get(s, {})
        if chave_k in cen and cen.get("_cidade"):
            rz = cen[chave_k]["renda"] / cen["_cidade"]
            comp_r = (f"{nf(rz, 1)} vez{'es' if rz >= 1.95 else ''} a da cidade" if rz >= 1.15 else
                      ("parecida com a da cidade" if rz > 0.87 else f"{pct(1 - rz, 0)} abaixo da cidade"))
            pop = cen[chave_k].get("pessoas")
            extras.append(f"<li><b>R$ {nf(cen[chave_k]['renda'])}</b> por mês é a renda média de quem chefia os domicílios"
                          f"{' do bairro' if pop else ' da região do bairro'}, {comp_r} (R$ {nf(cen['_cidade'])})"
                          f"{f'; {nf(pop)} moradores' if pop else ''}. Fonte: IBGE, Censo 2022.</li>")
        tp = b.get("tipos") or {}
        if tp:
            tot = sum(tp.values())
            extras.append(f"<li><b>{pct(tp.get('apto', 0) / tot, 0)}</b> das vendas foram de apartamentos e {pct(tp.get('casa', 0) / tot, 0)} de casas.</li>")
        if b.get("financiado") is not None:
            extras.append(f"<li><b>{pct(b['financiado'], 0)}</b> das compras tiveram financiamento bancário (cidade: {pct(ci.get('financiado'), 0)}).</li>")
        if b.get("base_acima") is not None:
            extras.append(f"<li>Em <b>{pct(b['base_acima'], 0)}</b> das compras, a prefeitura avaliou o imóvel acima do preço declarado e cobrou o ITBI sobre o valor dela (cidade: {pct(ci.get('base_acima'), 0)}).</li>")
        if b.get("ano_med"):
            extras.append(f"<li>Metade dos imóveis vendidos foi construída antes de <b>{b['ano_med']}</b>.</li>")
        if s in ITBI_REGRAS and b.get("ticket12"):
            extras.append(f'<li>No preço mediano do bairro ({brl_curto(b["ticket12"])}), o ITBI à vista fica em cerca de '
                          f'<b>R$ {nf(itbi_calc(ITBI_REGRAS[s], b["ticket12"]))}</b>. <a href="{u(f"/{s}/itbi/")}">Calcule o seu →</a></li>')
        if b.get("ticket12"):
            extras.append(f'<li>Financiando 80% de {brl_curto(b["ticket12"])} em 30 anos: <a href="{u("/financiamento/")}?valor={round(b["ticket12"])}&amp;cidade={s}">simule a parcela com os juros de cada banco →</a></li>')
        extras_html = f'<section class="card"><h2>Outros números de {esc(nb)}</h2><ul>{"".join(extras)}</ul></section>' if extras else ""
        perguntas = [
            (f"Quanto custa o metro quadrado em {nb}?",
             f"Nos últimos 12 meses, o metro quadrado mediano das vendas de apartamentos e casas em {nb}, {nome_c}, foi de R$ {nf(b.get('m2_12'))}"
             + (f", {pct(abs(rel), 0)} {'acima' if rel > 0 else 'abaixo'} da mediana da cidade." if rel is not None and abs(rel) >= 0.03 else ".")
             + (f" Metade das vendas ficou entre R$ {nf(q[1])} e R$ {nf(q[3])} por m²." if q else "")),
            (f"O mercado de imóveis em {nb} está aquecido?",
             (f"Nos últimos 3 meses houve {pct(abs(t[2]), 0)} {'mais' if t[2] > 0 else 'menos'} vendas que nos mesmos meses do ano anterior ({t[1].lower()})."
              if t[0] else "Ainda não há vendas suficientes para comparar com o ano anterior.")),
            (f"De onde vêm esses preços?",
             f"Das guias de ITBI, o imposto pago na compra do imóvel, publicadas pela prefeitura {de_(nome_c)}. O valor usado é {vtxt[1]}."),
        ]
        faq = '<section class="faq">' + "".join(f"<div><h3>{esc(p)}</h3><p>{esc(r)}</p></div>" for p, r in perguntas) + "</section>"
        ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": p, "acceptedAnswer": {"@type": "Answer", "text": r}} for p, r in perguntas]}
        corpo = f"""<section class="hero">
<span class="kicker">{esc(nb)} · {esc(nome_c)}</span>
<h1>Preço do m² em {esc(nb)}</h1>
<p class="lead">Nos últimos 12 meses, {nf(b['n12'])} imóveis foram vendidos em {esc(nb)} com metro quadrado mediano de <strong>R$ {nf(b.get('m2_12'))}</strong>{', ' + frase_rel if frase_rel else ''}.{faixa}</p>
</section>
{tiles}
{self.mapas[s].bairro_html(chave_k)}
{curva_html(b, ci.get('m2_12'), nb) if not c.get('agregado') else ''}
{tipo_bairro_html(b, nb)}
<section class="grid2">
<div class="card"><h2>Vendas por mês</h2>{grafico_vendas(meses, b['n'], f'Vendas por mês em {nb}')}</div>
<div class="card"><h2>Preço do m² mês a mês</h2>{grafico_m2(meses, m2_mm, f'Metro quadrado mediano em {nb}, média móvel de 3 meses')}
<p class="small">Média móvel de 3 meses; meses com menos de 5 vendas ficam de fora.</p></div>
</section>
{entorno_html(self.entorno.get(s, {}).get(chave_k, {}), nb, nome_c, s, self.posicoes.get(s, {}).get(chave_k), u(f"/{s}/melhores-bairros/"))}
{extras_html}
{faq}
<section class="card"><h2>Sobre estes números</h2>
<p>O valor de cada venda é {vtxt[1]}. Metro quadrado = valor ÷ área construída. Valores em reais da época, sem correção pela inflação.</p>
<p class="small">Fonte: <a href="{esc(c['fonte_url'])}" rel="noopener">{esc(c['fonte'])}</a>. <a href="{u('/' + s + '/#bairros')}">Ver todos os bairros {esc(de_(nome_c))}</a>.</p></section>"""
        self.pagina(f"/{s}/{bs}/", f"Preço do m² em {nb}, {nome_c}: R$ {nf(b.get('m2_12'))} (vendas reais)",
                    f"Metro quadrado mediano em {nb} ({nome_c}): R$ {nf(b.get('m2_12'))}, com {nf(b['n12'])} vendas nos últimos 12 meses. "
                    "Curva de preços, vendas mês a mês e comparação com a cidade, pelos dados do ITBI.",
                    corpo, ativo=f"/{s}/", migalhas=[(f"/{s}/", nome_c), (None, nb)], jsonld=[ld], media=bool(c.get("agregado")))

    # ------------------------------------------------------------ fixas
    # ------------------------------------------------------------ ITBI
    def itbi(self):
        regras = {k: v for k, v in ITBI_REGRAS.items() if k in self.cidades}
        if not regras:
            return
        def regra_txt(k, r):
            f_ = r.get("fin")
            t = f"<b>{nf(r['geral'], 0)}%</b> sobre o valor do imóvel"
            if f_:
                t += f"; com {esc(f_['quando'])}, {nf(f_['taxa'], 1)}% sobre a parte financiada"
                if f_.get("teto_fin"):
                    t += f" (até R$ {nf(f_['teto_fin'])})"
                t += f" e {nf(f_['resto'], 0)}% sobre o restante"
            return t
        linhas = "".join(f'<tr><td><a href="{u(f"/{k}/itbi/")}">{esc(NOMES_CIDADE[k])}</a></td><td>{regra_txt(k, r)}</td>'
                         f'<td class="r num">R$ {nf(itbi_calc(r, 500000))}</td></tr>' for k, r in regras.items())
        corpo = f"""<section class="hero">
<span class="kicker">Calculadora</span>
<h1>Calculadora de ITBI: quanto você paga de imposto na compra do imóvel</h1>
<p class="lead">O ITBI é o imposto da prefeitura pago por quem compra um imóvel, antes da escritura. Escolha a cidade, digite o valor e, se for financiar, quanto vai pegar no banco.</p>
</section>
<section class="card"><h2>Calcule o seu ITBI</h2>{itbi_caixa(regras, "sao-paulo")}
<p class="small">Estimativa pelas regras gerais de cada prefeitura. Isenções e casos especiais (primeiro imóvel de baixo valor, programas habitacionais) não entram na conta.</p></section>
<section class="card"><h2>Alíquota do ITBI em cada cidade</h2>
<div class="tw"><table><thead><tr><th>Cidade</th><th>Regra geral</th><th class="r">Imóvel de R$ 500 mil, à vista</th></tr></thead><tbody>{linhas}</tbody></table></div></section>
<section class="card"><h2>Perguntas comuns</h2>
<h3>Quem paga o ITBI?</h3><p>Quem compra, salvo acordo diferente no contrato. Sem o imposto pago, o cartório não registra a transferência.</p>
<h3>Sobre qual valor o imposto é calculado?</h3><p>Sobre o valor da compra. Algumas prefeituras usam uma avaliação própria quando ela é maior que o preço declarado; quem discorda pode pedir revisão. Nas páginas de cada cidade mostramos com que frequência isso acontece.</p>
<h3>Financiar reduz o ITBI?</h3><p>Em algumas cidades, sim: a parte paga com financiamento habitacional tem alíquota menor. A calculadora já aplica essa regra onde ela existe.</p>
</section>"""
        self.busca.append(["Calculadora de ITBI", "/itbi/", "Ferramenta"])
        self.pagina("/itbi/", "Calculadora de ITBI 2026: São Paulo, Rio, BH, Fortaleza, Recife e Porto Alegre",
                    "Calcule o ITBI na compra do imóvel em São Paulo, Rio de Janeiro, Belo Horizonte, Fortaleza, Recife e Porto Alegre, "
                    "com a alíquota de cada prefeitura e a redução para financiamento.", corpo, ativo="/itbi/", migalhas=[(None, "Calculadora de ITBI")])
        for k, r in regras.items():
            c = self.cidades[k]
            nome = c["nome"]
            ci = c["cidade"]
            exemplos = "".join(
                f'<tr><td class="num">R$ {nf(v)}</td><td class="r num">R$ {nf(itbi_calc(r, v))}</td>'
                + (f'<td class="r num">R$ {nf(itbi_calc(r, v, v * 0.8))}</td>' if r.get("fin") else "") + "</tr>"
                for v in (300000, 500000, 800000, 1200000))
            cab_ex = '<th class="r">Financiando 80%</th>' if r.get("fin") else ""
            # imposto de um imóvel típico nos bairros com mais vendas
            bs = sorted((b for b in c["bairros"].values() if b.get("ticket12")), key=lambda b: -b["n12"])[:15]
            tb = "".join(f'<tr><td><a href="{u(f"/{k}/{slug(b["nome"])}/")}">{esc(nome_bonito(b["nome"]))}</a></td>'
                         f'<td class="r num">{brl_curto(b["ticket12"])}</td><td class="r num">R$ {nf(itbi_calc(r, b["ticket12"]))}</td></tr>' for b in bs)
            extra = []
            if ci.get("ticket12"):
                extra.append(f"O preço mediano das compras {esc(em_(nome))} nos últimos 12 meses foi de <b>{brl_curto(ci['ticket12'])}</b>, "
                             f"o que dá cerca de <b>R$ {nf(itbi_calc(r, ci['ticket12']))}</b> de ITBI à vista.")
            if ci.get("financiado") is not None:
                extra.append(f"<b>{pct(ci['financiado'], 0)}</b> das compras tiveram financiamento bancário.")
            if ci.get("base_acima") is not None:
                extra.append(f"Em <b>{pct(ci['base_acima'], 0)}</b> das compras, a prefeitura avaliou o imóvel acima do preço declarado e cobrou o imposto sobre o valor dela.")
            corpo = f"""<section class="hero">
<span class="kicker">{esc(nome)} · ITBI</span>
<h1>ITBI {esc(em_(nome))}: alíquota e calculadora</h1>
<p class="lead">{regra_txt(k, r)}. {" ".join(extra)}</p>
</section>
<section class="card"><h2>Calcule o ITBI {esc(em_(nome))}</h2>{itbi_caixa({k: r}, k)}
<p class="small">{esc(r.get("nota", ""))} Fonte: <a href="{esc(r["url"])}" rel="noopener">prefeitura {esc(de_(nome))}</a>. Estimativa pelas regras gerais; isenções e casos especiais não entram na conta.</p></section>
<section class="grid2">
<div class="card"><h2>Exemplos</h2><div class="tw"><table><thead><tr><th>Valor do imóvel</th><th class="r">À vista</th>{cab_ex}</tr></thead><tbody>{exemplos}</tbody></table></div></div>
<div class="card"><h2>ITBI de um imóvel típico por bairro</h2><div class="tw"><table><thead><tr><th>Bairro</th><th class="r">Preço mediano</th><th class="r">ITBI à vista</th></tr></thead><tbody>{tb}</tbody></table></div>
<p class="small">Preço mediano das compras de cada bairro nos últimos 12 meses (ITBI da prefeitura). Bairros com mais vendas.</p></div>
</section>
<section class="card"><p><a href="{u("/itbi/")}">Calculadora para as outras cidades →</a> · <a href="{u(f"/{k}/")}">Preço do m² {esc(em_(nome))} por bairro →</a></p></section>"""
            self.busca.append([f"ITBI {nome}", f"/{k}/itbi/", "Calculadora"])
            self.pagina(f"/{k}/itbi/", f"ITBI {em_(nome)} 2026: alíquota, calculadora e quanto se paga por bairro",
                        f"ITBI {em_(nome)}: {r['geral']}% sobre o valor do imóvel" + (", com alíquota menor para a parte financiada" if r.get("fin") else "")
                        + ". Calcule o imposto e veja quanto se paga num imóvel típico de cada bairro.",
                        corpo, ativo=f"/{k}/", migalhas=[(f"/{k}/", nome), (None, "ITBI")], media=bool(c.get("agregado")))

    # ------------------------------------------------------------ simulador de financiamento
    def financiamento(self):
        arq = RAIZ / "data" / "juros_imob.json"
        if not arq.exists():
            return
        J = json.loads(arq.read_text(encoding="utf-8"))
        if not (J.get("reguladas") or J.get("mercado")):
            return
        def nome_banco(n):
            n = re.sub(r"^(BCO|BANCO)\s+", "", n.strip(), flags=re.I)
            n = re.sub(r"\s+S\.?A\.?$", "", n, flags=re.I)
            troca = {"CAIXA ECONOMICA FEDERAL": "Caixa", "DO BRASIL": "Banco do Brasil", "ITAÚ UNIBANCO": "Itaú", "BRADESCO": "Bradesco",
                     "SANTANDER (BRASIL)": "Santander", "INTER": "Inter", "COOPERATIVO SICREDI": "Sicredi", "SICOOB": "Sicoob",
                     "APE POUPEX": "Poupex", "BRB - BCO DE BRASILIA": "BRB"}
            return troca.get(n.upper(), n.title())
        bancos = {k: [[nome_banco(n), aa] for n, _, aa in J.get(k, [])] for k in ("reguladas", "mercado")}
        med = {k: statistics.median([aa for _, aa in v]) for k, v in bancos.items() if v}
        dados = esc(json.dumps({"b": bancos, "med": med, "itbi": {k: v for k, v in ITBI_REGRAS.items() if k in self.cidades}},
                               ensure_ascii=False, separators=(",", ":")))
        mes = mes_nome(J["mes"])
        opts_cid = '<option value="">Outra cidade</option>' + "".join(
            f'<option value="{k}">{esc(NOMES_CIDADE[k])}</option>' for k in ITBI_REGRAS if k in self.cidades)
        tab = "".join(f'<tr><td>{esc(n)}</td><td class="r num">{nf(aa, 2)}% ao ano</td></tr>' for n, aa in bancos.get("reguladas", []))
        corpo = f"""<section class="hero">
<span class="kicker">Simulador</span>
<h1>Simulador de financiamento imobiliário: parcelas na SAC e na Price</h1>
<p class="lead">Veja quanto fica a parcela, quanto você paga de juros e quanto precisa ter na mão para comprar, com os juros reais de cada banco publicados pelo Banco Central ({esc(mes)}).</p>
</section>
<section class="card"><h2>Simule</h2>
<div class="fin" data-fin="{dados}">
<label>Valor do imóvel (R$)<input type="text" inputmode="numeric" name="valor" placeholder="500.000" autocomplete="off"></label>
<label>Entrada (R$)<input type="text" inputmode="numeric" name="entrada" placeholder="20% do valor" autocomplete="off"></label>
<label>Prazo (anos)<input type="text" inputmode="numeric" name="prazo" value="30" autocomplete="off"></label>
<label>Linha de crédito<select name="linha"><option value="reguladas">SFH (taxas reguladas)</option><option value="mercado">Taxas de mercado</option></select></label>
<label>Banco<select name="banco"></select></label>
<label class="fin-outra" hidden>Sua taxa (% ao ano)<input type="text" inputmode="decimal" name="taxa" placeholder="11,5" autocomplete="off"></label>
<label>Cidade (para o ITBI)<select name="cidade">{opts_cid}</select></label>
<div class="fin-res" aria-live="polite"><p>Digite o valor do imóvel.</p></div>
</div>
<p class="small">Estimativa: juros anuais do banco, sem TR, seguros obrigatórios e taxa de administração, que aumentam um pouco a parcela. Renda mínima pela regra comum dos bancos: parcela de até 30% da renda. Fora escritura e registro.</p></section>
<section class="card"><h2>SAC ou Price?</h2>
<p><b>SAC:</b> a parcela começa mais alta e cai todo mês, porque você paga sempre a mesma parte da dívida. No total, paga menos juros. É o mais usado pelos bancos.</p>
<p><b>Price:</b> a parcela é igual do começo ao fim. A primeira cabe melhor no bolso, mas no total os juros são maiores.</p></section>
<section class="card"><h2>Juros do financiamento imobiliário por banco (SFH, {esc(mes)})</h2>
<div class="tw"><table><thead><tr><th>Banco</th><th class="r">Juros</th></tr></thead><tbody>{tab}</tbody></table></div>
<p class="small">Taxa média cobrada por cada banco no mês, mais TR. Fonte: Banco Central do Brasil. <a href="https://economiaemnumeros.com.br/juros-dos-bancos/financiamento-imobiliario/">Veja todas as linhas e a evolução dos juros no Economia em Números →</a></p></section>"""
        self.busca.append(["Simulador de financiamento imobiliário", "/financiamento/", "Ferramenta"])
        self.pagina("/financiamento/", "Simulador de financiamento imobiliário: parcela SAC e Price com os juros de cada banco",
                    f"Simule o financiamento do imóvel: parcela na SAC e na Price, juros totais, renda mínima e quanto precisa de entrada e ITBI, "
                    f"com a taxa real de cada banco ({mes}, Banco Central).", corpo, ativo="/financiamento/", migalhas=[(None, "Simulador de financiamento")])

    def sobre(self):
        linhas = "".join(
            f"<tr><td>{esc(c['nome'])}</td><td class='wrap'>{esc(VALOR_TXT[c['valor']][1])}</td><td>{mes_nome(c['meses'][0])} a {mes_nome(c['ultimo_mes'])}</td>"
            f"<td class='wrap'><a href='{esc(c['fonte_url'])}' rel='noopener'>{esc(c['fonte'])}</a></td></tr>"
            for c in self.cidades.values())
        corpo = f"""<section class="hero"><span class="kicker">Como funciona</span><h1>De onde vêm os preços</h1>
<p class="lead">Toda compra de imóvel paga o ITBI (Imposto sobre a Transmissão de Bens Imóveis) à prefeitura. Algumas prefeituras publicam as guias desse imposto como dados abertos, sem o nome de quem comprou ou vendeu. É daí que saem os números deste site.</p></section>
<section class="card"><h2>As cidades e o valor usado em cada uma</h2>
<div class="tw"><table class="direitos"><thead><tr><th>Cidade</th><th>Valor de cada venda</th><th>Período</th><th>Fonte</th></tr></thead><tbody>{linhas}</tbody></table></div></section>
<section class="card prose"><h2>O que entra na conta</h2><ul>
<li>Só compras de <b>apartamentos e casas</b>. Ficam de fora lojas, salas, terrenos, vagas de garagem, doações, heranças e outras transmissões que não são compra.</li>
<li>Onde a base permite, só a compra do <b>imóvel inteiro</b> (quem compra a parte de um irmão, por exemplo, fica de fora).</li>
<li><b>Metro quadrado</b> = valor da venda ÷ área construída que consta na prefeitura. Para não deixar um registro errado puxar a conta, as vendas com m² entre os 1% mais baixos e os 1% mais altos de cada cidade são descartadas.</li>
<li>Usamos a <b>mediana</b> (o valor do meio) e não a média: uma cobertura de luxo não muda a mediana de um bairro.</li>
<li>Bairro só ganha página com pelo menos 20 vendas no período; a curva de preços aparece a partir de 30 vendas em 12 meses.</li>
<li><b>Aquecendo ou esfriando</b>: vendas dos últimos 3 meses contra os mesmos 3 meses do ano anterior. Acima de +10%, aquecendo; abaixo de −10%, esfriando.</li>
<li>Valores em reais da época, sem correção pela inflação.</li>
</ul>
<h2>Por que é diferente do preço de anúncio</h2>
<p>Anúncio é o que o vendedor pede; o ITBI registra o que foi pago (ou o valor que a prefeitura usou). O preço fechado costuma ficar abaixo do pedido, e a área cadastrada na prefeitura pode ser maior que a área "privativa" dos anúncios, porque às vezes inclui a parte das áreas comuns do prédio. Por isso o m² daqui tende a sair menor que o dos portais de anúncio.</p>
<h2>Limitações</h2><ul>
<li>Em São Paulo e em Porto Alegre, apartamentos de prédios novos vendidos antes de cada unidade ter cadastro próprio aparecem como fração do terreno e ficam de fora.</li>
<li>No Rio, a prefeitura publica só médias por bairro e mês: lá não há curva de preços nem mediana.</li>
<li>No Recife, a base traz a avaliação da prefeitura, não o preço declarado.</li>
<li>Os nomes de bairro são os da prefeitura; alguns aparecem abreviados.</li>
</ul></section>"""
        self.pagina("/sobre/", "Como funciona o Imóveis em Números", "De onde vêm os preços dos imóveis: guias de ITBI publicadas pelas prefeituras, o que entra na conta e as limitações.",
                    corpo, ativo="/sobre/", migalhas=[(None, "Como funciona")])
        self.pagina("/contato/", "Contato | Imóveis em Números", "Fale com o Imóveis em Números.",
                    '<section class="hero"><h1>Contato</h1><p class="lead">Sugestões, correções e pedidos: <a href="mailto:oleoemnumeros@gmail.com">oleoemnumeros@gmail.com</a>.</p></section>',
                    migalhas=[(None, "Contato")])
        self.pagina("/privacidade/", "Privacidade | Imóveis em Números", "Política de privacidade do Imóveis em Números.",
                    '<section class="hero prose"><h1>Privacidade</h1><p>O site não pede cadastro nem guarda dados pessoais de quem visita. A contagem de visitas é feita pelo GoatCounter, sem cookies e sem identificar pessoas. Os números publicados vêm de bases abertas das prefeituras, que não trazem nome de comprador nem de vendedor; o site mostra só totais e medianas por bairro, nunca uma venda isolada.</p></section>',
                    migalhas=[(None, "Privacidade")])

    def arquivos(self):
        (SAIDA / "assets").mkdir(parents=True, exist_ok=True)
        for f in SITE.glob("*.js"):
            shutil.copy(f, SAIDA / "assets" / f.name)
        shutil.copy(SITE / "estilo.css", SAIDA / "assets" / "estilo.css")
        (SAIDA / "favicon.svg").write_text(FAVICON, encoding="utf-8")
        (SAIDA / "busca.json").write_text(json.dumps([[t, u(h), k] for t, h, k in self.busca], ensure_ascii=False,
                                                     separators=(",", ":")), encoding="utf-8")
        if PREVIA:
            (SAIDA / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
        else:
            (SAIDA / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {URL}/sitemap.xml\n", encoding="utf-8")
            (SAIDA / "CNAME").write_text(DOMINIO + "\n", encoding="utf-8")
        hoje = self.gerado.strftime("%Y-%m-%d")
        sm = "".join(f"<url><loc>{URL}{p}</loc><lastmod>{hoje}</lastmod></url>" for p in self.paginas)
        (SAIDA / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>', encoding="utf-8")
        (SAIDA / ".nojekyll").write_text("", encoding="utf-8")

    def gerar(self):
        if SAIDA.exists():
            shutil.rmtree(SAIDA)
        SAIDA.mkdir(parents=True)
        self.mapas = {s: Mapa(s, c) for s, c in self.cidades.items()}
        preparar_nomes(self.cidades, self.mapas)
        self.inicio()
        self.entorno = {s: calcular_entorno(s, c, self.mapas[s]) for s, c in self.cidades.items()}
        self.censo = {s: calcular_censo(s, c) for s, c in self.cidades.items()}
        self.posicoes = {}
        for s, c in self.cidades.items():
            self.cidade(s, c)
        self.itbi()
        self.financiamento()
        self.sobre()
        # 404
        self.pagina("/404/", "Página não encontrada | Imóveis em Números", "Página não encontrada.",
                    f'<section class="hero"><h1>Página não encontrada</h1><p class="lead"><a href="{u("/")}">Voltar ao início</a>.</p></section>')
        shutil.move(SAIDA / "404" / "index.html", SAIDA / "404.html")
        shutil.rmtree(SAIDA / "404")
        self.paginas.remove("/404/")
        self.arquivos()
        print(f"Site gerado: {len(self.paginas)} páginas, {len(self.cidades)} cidades. Base: '{BASEP}'. Prévia: {PREVIA}.")


def tile(lbl, val, nota="") -> str:
    return f'<div class="tile"><span class="lbl">{lbl}</span><span class="val num">{val}</span><span class="chg">{nota}</span></div>'


if __name__ == "__main__":
    Site().gerar()
