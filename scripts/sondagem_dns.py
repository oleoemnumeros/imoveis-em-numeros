"""Confere o DNS do domínio (A, NS, CNAME do www) e se o site responde."""
import json, subprocess, requests
from pathlib import Path
out = {}
D = "imoveisemnumeros.com.br"
for nome, tipo in [(D, "A"), ("www." + D, "CNAME"), ("www." + D, "A"), (D, "SOA"), (D, "AAAA"), (D, "TXT"),
                   (D + "." + D, "A"), ("www." + D + "." + D, "CNAME"), ("@." + D, "A")]:
    for srv in ("8.8.8.8", "a.auto.dns.br", "b.auto.dns.br"):
        r = subprocess.run(["dig", "+short", f"@{srv}", tipo, nome], capture_output=True, text=True, timeout=30)
        out[f"{tipo} {nome} @{srv}"] = r.stdout.strip() or r.stderr.strip() or "(vazio)"
for u in ["http://imoveisemnumeros.com.br/", "https://imoveisemnumeros.com.br/"]:
    try:
        r = requests.get(u, timeout=20, allow_redirects=False)
        out[u] = f"{r.status_code} {r.headers.get('server','')} {r.headers.get('location','')}"
    except Exception as e:
        out[u] = f"erro: {type(e).__name__}: {str(e)[:150]}"
Path("data/dns.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
