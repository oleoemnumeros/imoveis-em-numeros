"""Consulta pública (RDAP do registro.br) de domínios: datas de criação e mudança, servidores DNS."""
import json, requests
from pathlib import Path
out = {}
for d in ["ensinoemnumeros.com.br", "escolaemnumeros.com.br", "escolasemnumeros.com.br", "educaemnumeros.com.br", "estudoemnumeros.com.br", "educacaoemnumeros.com", "educacaoemnumeros.net.br"]:
    try:
        r = requests.get(f"https://rdap.registro.br/domain/{d}", timeout=30, headers={"Accept": "application/rdap+json"})
        if r.status_code == 404:
            out[d] = "livre (não registrado)"; continue
        j = r.json()
        out[d] = {"status": j.get("status"), "eventos": [(e.get("eventAction"), e.get("eventDate")) for e in j.get("events", [])],
                  "dns": [n.get("ldhName") for n in j.get("nameservers", [])],
                  "titular": [ (e.get("roles"), (e.get("vcardArray") or [None, []])[1][1:3] if e.get("vcardArray") else e.get("handle")) for e in j.get("entities", [])][:3]}
    except Exception as e:
        out[d] = f"erro {e}"
Path("data/dns.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
