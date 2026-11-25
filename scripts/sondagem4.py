"""Sondagem 2 do Censo 2022: tamanhos, colunas dos arquivos por setor e pastas da malha."""
import io, json, re, zipfile, requests
from pathlib import Path

H = {"User-Agent": "Mozilla/5.0"}
F = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/"
G = "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/"
MUN = ["3550308", "3304557", "3106200", "2304400", "2611606", "4314902"]
out = {}

def lista(url):
    r = requests.get(url, headers=H, timeout=60)
    out["lista " + url] = re.findall(r'href="([^"?/][^"?]*)"[^\n]*?(\d+(?:\.\d+)?[KMG]?)\s*$', r.text, re.M) or re.findall(r'href="([^"?]+)"', r.text)

for u in [F + "Agregados_por_Setores_Censitarios/malha_com_atributos/setores/csv/",
          F + "Agregados_por_Setores_Censitarios/malha_com_atributos/setores/gpkg/",
          G + "setores/gpkg/UF/SP/", G + "setores/gpkg/UF/RJ/",
          F + "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/",
          F + "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"]:
    try:
        lista(u)
    except Exception as e:
        out["lista " + u] = str(e)

def amostra(url, nome):
    try:
        r = requests.get(url, headers=H, timeout=600)
        out[nome + " bytes"] = len(r.content)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        out[nome + " arquivos"] = z.namelist()
        for n in z.namelist():
            if not n.lower().endswith(".csv"):
                continue
            with z.open(n) as fh:
                txt = io.TextIOWrapper(fh, encoding="latin-1", errors="replace")
                cab = txt.readline().strip()
                linhas = [cab]
                for ln in txt:
                    if any(m in ln[:40] for m in MUN[:1]):
                        linhas.append(ln.strip())
                        if len(linhas) > 4:
                            break
                out[nome + " " + n] = linhas
    except Exception as e:
        out[nome + " erro"] = str(e)

amostra(F + "Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip", "renda")
amostra(F + "Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/Agregados_por_setores_basico_BR_20260520.zip", "basico")
amostra(F + "Agregados_por_Setores_Censitarios_Caracteristicas_urbanisticas_do_entorno_dos_domicilios/Agregados_por_Setor_csv/Agregados_por_setores_entorno_moradores_BR.zip", "entorno")
Path("data/sondagem_censo2.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
