"""
JARVIS - Archivio opportunita' e progetti (persistente).
Il file progetti.json e' salvato in locale e, se sono impostate le variabili
GITHUB_TOKEN e GITHUB_REPO, anche nel repository GitHub: cosi' non si perde al riavvio di Render.
Nessuna funzione invia messaggi ai proprietari.
"""
import json, os, re, base64, urllib.request, urllib.error
from datetime import date, datetime
from zoneinfo import ZoneInfo

PATH = os.environ.get("PROGETTI_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "progetti.json"))
STATI = ["nuovo", "da_verificare", "pronto_al_contatto", "contattato", "risposta_ricevuta",
         "appuntamento", "acquisito", "perso"]
URL_RE = re.compile(r'https?://[^\s<>"\)\]]+')


def _vuoto():
    return {"versione": 1, "progetti": {}, "opportunita": [], "ricerche": [], "prossimo_id": 1}


def carica():
    if not os.path.exists(PATH):
        return _vuoto()
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def salva(d):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)
    try:
        github_push()
    except Exception as e:
        print("salvataggio su GitHub non riuscito:", str(e)[:120])


def github_push():
    """Scrive progetti.json nel repository. Attivo solo con GITHUB_TOKEN e GITHUB_REPO.
    GITHUB_BRANCH e' facoltativo (default main): un ramo dedicato evita di riavviare l'app a ogni salvataggio."""
    tok = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPO", "")
    branch = os.environ.get("GITHUB_BRANCH", "main")
    if not tok or not repo:
        return False
    api = "https://api.github.com/repos/%s/contents/progetti.json" % repo
    h = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "jarvis-app"}
    sha = None
    try:
        with urllib.request.urlopen(urllib.request.Request(api + "?ref=" + branch, headers=h), timeout=15) as r:
            sha = json.loads(r.read().decode()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    with open(PATH, "rb") as f:
        contenuto = base64.b64encode(f.read()).decode()
    body = {"message": "JARVIS: aggiornamento progetti", "content": contenuto, "branch": branch}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request(api, data=json.dumps(body).encode(), method="PUT",
                                 headers=dict(h, **{"Content-Type": "application/json"}))
    with urllib.request.urlopen(req, timeout=20):
        return True


def oggi():
    return date.today().isoformat()


def ora():
    return datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="minutes")


def normalizza(url):
    u = (url or "").strip().lower().rstrip("/.,;:")
    u = u.replace("https://", "").replace("http://", "").replace("www.", "")
    return u.split("?")[0]


def crea_progetto(d, chiave, titolo, nota=""):
    if chiave not in d["progetti"]:
        d["progetti"][chiave] = {"titolo": titolo, "creato": ora(), "nota": nota}
    return d["progetti"][chiave]


def opportunita_esistente(d, url):
    k = normalizza(url)
    for o in d["opportunita"]:
        if normalizza(o["fonte"]) == k:
            return o
    return None


def aggiungi_opportunita(d, progetto, zona, fonte, titolo="", info_mancanti=None):
    if opportunita_esistente(d, fonte):
        return None
    o = {
        "id": d["prossimo_id"], "progetto": progetto, "zona": zona, "titolo": titolo,
        "fonte": fonte, "data_verifica": oggi(), "stato": "da_verificare",
        "info_mancanti": info_mancanti or ["prezzo", "metratura", "stato dell'immobile", "recapito del proprietario"],
        "prossima_azione": "aprire l'annuncio e verificare che esista ancora",
        "lettere": [], "creato": ora(),
    }
    d["prossimo_id"] += 1
    d["opportunita"].append(o)
    return o


def registra_ricerca(d, progetto, modalita, zona, testo):
    links = []
    for u in URL_RE.findall(testo or ""):
        u = u.rstrip(".,;:")
        if u not in links:
            links.append(u)
    nuove = []
    for u in links:
        o = aggiungi_opportunita(d, progetto, zona, u)
        if o:
            nuove.append(o["id"])
    d["ricerche"].append({
        "data": ora(), "progetto": progetto, "modalita": modalita, "zona": zona,
        "link_trovati": links, "nuove_opportunita": nuove, "testo": (testo or "")[:4000],
    })
    return {"link": len(links), "nuove": len(nuove)}


def stato(d, id_, nuovo_stato):
    if nuovo_stato not in STATI:
        raise ValueError("stato non valido: " + nuovo_stato)
    for o in d["opportunita"]:
        if o["id"] == id_:
            o["stato"] = nuovo_stato
            return o
    raise KeyError("id non trovato: %s" % id_)


def riepilogo(d, progetto=None):
    righe = []
    for o in d["opportunita"]:
        if progetto and o["progetto"] != progetto:
            continue
        righe.append("%d | %s | %s | %s | verificato il %s" % (o["id"], o.get("stato", "nuovo"), o.get("zona", ""), o["fonte"], o.get("data_verifica", "")))
    return "\n".join(righe) or "Nessuna opportunita' registrata."


def main(argv):
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("riepilogo")
    s = sub.add_parser("stato")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--stato", required=True, choices=STATI)
    a = p.parse_args(argv)
    d = carica()
    if a.cmd == "riepilogo":
        print(riepilogo(d))
    elif a.cmd == "stato":
        o = stato(d, a.id, a.stato)
        salva(d)
        print("id %d -> %s" % (o["id"], o["stato"]))


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
