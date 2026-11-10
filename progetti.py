"""
JARVIS - Archivio opportunita' (FASE 1: protezione dei dati).

Regole di sicurezza:
- Con GITHUB_TOKEN e GITHUB_REPO impostati, l'archivio UFFICIALE e' il file progetti.json
  sul ramo GITHUB_BRANCH (es. Dati). carica() lo legge sempre da GitHub.
- Se GitHub non risponde o la lettura fallisce, carica() e salva() sollevano ArchivioError
  e NON scrivono nulla.
- salva() rilegge sempre il remoto, unisce le modifiche (nessuna perdita) e scrive con lo sha
  corrente. In caso di conflitto (409) ripete l'unione. Non scrive mai un archivio piu' piccolo
  di quello remoto.
- Senza variabili GitHub funziona in locale (sviluppo e test).
"""
import json, os, re, base64, copy, unicodedata, urllib.request, urllib.error, urllib.parse
from datetime import date, datetime
from zoneinfo import ZoneInfo

PATH = os.environ.get("PROGETTI_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "progetti.json"))
STATI = ["nuovo", "da_verificare", "pronto_al_contatto", "contattato", "risposta_ricevuta",
         "appuntamento", "acquisito", "perso"]
URL_RE = re.compile(r'https?://[^\s<>"\)\]]+')
FILE_REMOTO = "progetti.json"


class ArchivioError(RuntimeError):
    """Archivio non leggibile o non scrivibile: nessuna modifica e' stata salvata."""


class _Conflitto(Exception):
    pass


def _vuoto():
    return {"versione": 1, "progetti": {}, "opportunita": [], "ricerche": [], "prossimo_id": 1}


def _cfg():
    return os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPO", ""), os.environ.get("GITHUB_BRANCH", "main")


def github_attivo():
    tok, repo, _ = _cfg()
    return bool(tok and repo)


def _headers(tok):
    return {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "jarvis-app"}


def _http(req, timeout=15):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace") if e.fp else ""
    except Exception as e:
        raise ArchivioError("GitHub non raggiungibile: %s" % str(e)[:120])


def _leggi_remoto():
    """Ritorna (dati, sha). dati=None se il file non esiste ancora sul ramo. Solleva ArchivioError se il ramo non esiste o GitHub non risponde."""
    tok, repo, branch = _cfg()
    h = _headers(tok)
    st, _ = _http(urllib.request.Request("https://api.github.com/repos/%s/git/ref/heads/%s" % (repo, urllib.parse.quote(branch)), headers=h))
    if st != 200:
        raise ArchivioError("ramo '%s' non trovato su GitHub (codice %s): archivio non letto" % (branch, st))
    st, corpo = _http(urllib.request.Request("https://api.github.com/repos/%s/contents/%s?ref=%s" % (repo, FILE_REMOTO, urllib.parse.quote(branch)), headers=h))
    if st == 404:
        return None, None
    if st != 200:
        raise ArchivioError("lettura archivio fallita (codice %s): nessuna modifica salvata" % st)
    j = json.loads(corpo)
    testo = base64.b64decode(j["content"].replace("\n", "")).decode("utf-8") if j.get("content") else ""
    if not testo.strip():
        raise ArchivioError("archivio remoto vuoto o illeggibile: nessuna modifica salvata")
    try:
        dati = json.loads(testo)
    except json.JSONDecodeError:
        raise ArchivioError("archivio remoto corrotto: nessuna modifica salvata")
    return dati, j.get("sha")


def _scrivi_remoto(dati, sha):
    tok, repo, branch = _cfg()
    h = _headers(tok)
    body = {"message": "JARVIS: aggiornamento archivio", "branch": branch,
            "content": base64.b64encode(json.dumps(dati, ensure_ascii=False, indent=2).encode("utf-8")).decode()}
    if sha:
        body["sha"] = sha
    req = urllib.request.Request("https://api.github.com/repos/%s/contents/%s" % (repo, FILE_REMOTO), data=json.dumps(body).encode(),
                                 method="PUT", headers=dict(h, **{"Content-Type": "application/json"}))
    st, corpo = _http(req, timeout=20)
    if st in (409, 422):
        raise _Conflitto()
    if st not in (200, 201):
        raise ArchivioError("scrittura archivio fallita (codice %s): nessuna modifica salvata" % st)


def _scrivi_locale(d):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def carica():
    if github_attivo():
        dati, _ = _leggi_remoto()
        if dati is None:
            dati = _vuoto()
        _scrivi_locale(dati)
        return dati
    if not os.path.exists(PATH):
        return _vuoto()
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def unisci(remoto, locale):
    """Unisce due archivi senza perdere nulla. Per la stessa fonte vince la versione locale (la piu' recente), l'id resta quello remoto."""
    out = copy.deepcopy(remoto)
    out.setdefault("progetti", {})
    out.setdefault("ricerche", [])
    out.setdefault("opportunita", [])
    per_fonte = {normalizza(o["fonte"]): o for o in out["opportunita"]}
    max_id = max([o["id"] for o in out["opportunita"]] + [out.get("prossimo_id", 1) - 1, 0])
    for o in locale.get("opportunita", []):
        k = normalizza(o["fonte"])
        if k in per_fonte:
            tgt = per_fonte[k]
            for kk, vv in o.items():
                if kk != "id":
                    tgt[kk] = vv
        else:
            max_id += 1
            n = dict(o)
            n["id"] = max_id
            out["opportunita"].append(n)
            per_fonte[k] = n
    out["progetti"].update(locale.get("progetti", {}))
    if locale.get("preferenze") or remoto.get("preferenze"):
        out["preferenze"] = {**remoto.get("preferenze", {}), **locale.get("preferenze", {})}
    viste = {(r.get("data"), r.get("modalita"), r.get("zona")) for r in out["ricerche"]}
    for r in locale.get("ricerche", []):
        chiave = (r.get("data"), r.get("modalita"), r.get("zona"))
        if chiave not in viste:
            out["ricerche"].append(r)
            viste.add(chiave)
    out["prossimo_id"] = max_id + 1
    return out


def salva(d):
    if not github_attivo():
        _scrivi_locale(d)
        return
    for _ in range(3):
        remoto, sha = _leggi_remoto()
        base = remoto if remoto is not None else _vuoto()
        unito = unisci(base, d)
        if remoto is not None and len(unito["opportunita"]) < len(remoto["opportunita"]):
            raise ArchivioError("protezione: il salvataggio ridurrebbe l'archivio: annullato")
        try:
            _scrivi_remoto(unito, sha)
        except _Conflitto:
            continue
        _scrivi_locale(unito)
        d.clear()
        d.update(unito)
        return
    raise ArchivioError("conflitto persistente sull'archivio: salvataggio annullato, riprova")


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
