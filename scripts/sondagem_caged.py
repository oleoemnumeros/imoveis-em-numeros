"""Sondagem: microdados do Novo Caged no FTP do Ministério do Trabalho (pastas, um mês, colunas, layout com nomes da CBO)."""
import ftplib, io, json, subprocess, os, time
from pathlib import Path
out = {}
try:
    ftp = ftplib.FTP("ftp.mtps.gov.br", timeout=120, encoding="latin-1")
    ftp.login()
    base = "/pdet/microdados/NOVO CAGED"
    out["raiz"] = ftp.nlst(base)[-15:]
    anos = sorted(x for x in ftp.nlst(base) if x.rsplit("/", 1)[-1].isdigit())
    ult_ano = anos[-1]
    meses = sorted(ftp.nlst(ult_ano))
    out["meses_ultimo_ano"] = meses[-6:]
    pasta = meses[-1]
    arqs = ftp.nlst(pasta)
    out["arquivos_ultimo_mes"] = arqs
    mov = [a for a in arqs if "CAGEDMOV" in a.upper()][0]
    out["tamanho_mov"] = ftp.size(mov)
    t0 = time.time()
    with open("/tmp/mov.7z", "wb") as fh:
        ftp.retrbinary(f"RETR {mov}", fh.write)
    out["download_s"] = round(time.time() - t0)
    subprocess.run(["7z", "x", "-y", "-o/tmp/mov", "/tmp/mov.7z"], check=True, capture_output=True)
    txt = [str(p) for p in Path("/tmp/mov").rglob("*") if p.is_file()]
    out["extraido"] = [(p, os.path.getsize(p)) for p in txt]
    with open(txt[0], encoding="utf-8", errors="replace") as fh:
        linhas = [next(fh).rstrip("\n") for _ in range(4)]
    out["amostra"] = linhas
    n = sum(1 for _ in open(txt[0], encoding="utf-8", errors="replace"))
    out["linhas"] = n
    lay = [x for x in ftp.nlst(base) if "layout" in x.lower() or "Layout" in x]
    out["layouts"] = lay
    for l in lay[:2]:
        if l.lower().endswith((".xlsx", ".xls")):
            b = io.BytesIO(); ftp.retrbinary(f"RETR {l}", b.write)
            import openpyxl
            wb = openpyxl.load_workbook(b, read_only=True)
            out[f"abas {l}"] = wb.sheetnames
            for nm in wb.sheetnames:
                if "cbo" in nm.lower():
                    ws = wb[nm]; out[f"cbo {nm}"] = [list(r) for r in ws.iter_rows(min_row=1, max_row=5, values_only=True)]
                    out[f"cbo {nm} linhas"] = ws.max_row
    ftp.quit()
except Exception as e:
    out["erro"] = repr(e)[:500]
Path("data/sondagem_caged.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
print(json.dumps(out, ensure_ascii=False, indent=1, default=str)[:4000])
