"""Sondagem: arquivos do Censo 2022 por setor no FTP do IBGE (renda, população, malha)."""
import json, re, requests
from pathlib import Path

H = {"User-Agent": "Mozilla/5.0"}
RAIZES = [
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/",
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/",
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/",
    "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/",
]
out = {}

def lista(url, prof):
    try:
        r = requests.get(url, headers=H, timeout=60)
    except Exception as e:
        out[url] = f"erro {e}"; return
    if r.status_code != 200:
        out[url] = f"http {r.status_code}"; return
    links = [l for l in re.findall(r'href="([^"?]+)"', r.text) if not l.startswith(("/", "http", "..")) and l != "./"]
    # tamanhos aproximados do índice do Apache
    out[url] = links
    if prof > 0:
        for l in links:
            if l.endswith("/") and len(out) < 120:
                lista(url + l, prof - 1)

for raiz in RAIZES:
    lista(raiz, 2 if "geoftp" not in raiz else 3)
Path("data").mkdir(exist_ok=True)
Path("data/sondagem_censo.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(len(out))
