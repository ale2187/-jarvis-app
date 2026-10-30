"""
JARVIS - Radar gestione clienti (operatore commerciale per property management).
Modulo indipendente da radar.py (che cerca immobili da comprare: non viene toccato).

Tre categorie separate:
  A  proprietari con immobili in affitto (segnali commerciali da verificare)
  B  proprietari e strutture che cercano espressamente un gestore
  C  societa' e agenzie che cercano collaboratori / partner operativi

Per ogni categoria: zone complete, due gruppi di fonti, query separate.
Esiti per ogni link: VERIFICATO, DA VERIFICARE MANUALMENTE (link valido ma pagina non accessibile),
SCARTATO (falso, generico, sospetto, vendita, agenzia concorrente, non pertinente).
Report Telegram separato per categoria, con conteggi reali per fonte e ricerche a zero risultati.
Per ogni opportunita': scheda in archivio + pacchetto (lettera, presentazione, due proposte, bozza contratto).
Non invia nulla a nessuno: prepara, tu decidi e invii.
"""
import os, re, json, socket, time, urllib.request, urllib.error
from datetime import date, timedelta

import progetti as P

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KEY = os.environ.get("OPENAI_API_KEY", "")
DRY = os.environ.get("JARVIS_DRY") == "1"
PROGETTO = "gestione-clienti"
PROGETTO_TITOLO = "Acquisizione clienti per gestione immobiliare e turistica"

ZONE_COMO = ["Como", "Cernobbio", "Blevio", "Torno", "Faggeto Lario", "Nesso", "Lezzeno", "Bellagio", "Laglio",
             "Carate Urio", "Moltrasio", "Brienno", "Argegno", "Tremezzina", "Menaggio", "lago di Como"]
ZONE_LIDI = ["Lido delle Nazioni", "Lido di Pomposa", "Lido degli Scacchi", "Lido degli Estensi", "Lido di Spina",
             "Lido di Volano", "Porto Garibaldi", "Comacchio"]
GRUPPI_ZONA = {"lago_di_como": ZONE_COMO, "lidi_ferraresi": ZONE_LIDI}

FONTI = {
    "portali": "Immobiliare.it, Idealista, Subito, portali di case vacanze, pagine pubbliche indicizzate di Airbnb e Booking",
    "web_agenzie": "motori di ricerca, siti di agenzie immobiliari locali, siti di societa' di gestione turistica, annunci pubblici di collaborazione",
}

CATEGORIE = {
    "A": {"titolo": "PROPRIETARI CON IMMOBILI IN AFFITTO", "priorita_base": "media",
          "cerca": "annunci di case e appartamenti in affitto (turistico, stagionale o settimanale) pubblicati da privati o agenzie. "
                   "Cerca soprattutto: annunci in affitto da tempo, ripubblicati, con prezzo modificato o ribassato, con poche fotografie, "
                   "con descrizione breve o poco professionale. Considera questi elementi segnali da verificare, non certezze."},
    "B": {"titolo": "PROPRIETARI CHE CERCANO UN GESTORE", "priorita_base": "alta",
          "cerca": "annunci di proprietari o strutture che cercano espressamente un gestore. Parole chiave: cerco property manager, cerco gestore casa vacanze, "
                   "cerco gestione Airbnb, gestione affitti brevi, cerco collaboratore per gestione appartamenti, affidare gestione immobile, "
                   "gestione completa casa vacanze, gestione B&B, gestione appartamenti turistici."},
    "C": {"titolo": "SOCIETA' E AGENZIE CHE CERCANO COLLABORATORI", "priorita_base": "alta",
          "cerca": "societa' di gestione immobiliare o turistica, aziende turistiche e agenzie che cercano property manager, gestori di strutture o collaboratori "
                   "per la gestione di immobili, o proprieta' che cercano un partner operativo per affitti brevi e stagionali. "
                   "Questa categoria puo' generare collaborazioni, non solo clienti."},
}

PAROLE_B = ("cerco property", "cerco gestore", "cercasi gestore", "cerco gestione", "gestione airbnb", "gestione affitti brevi",
            "cerco collaboratore", "affidare la gestione", "gestione completa", "gestione b&b", "gestione appartamenti",
            "cerco chi gestisca", "cercasi host", "cerco co-host", "gestore casa vacanze")
PAROLE_C = ("cerchiamo", "collaboratore", "collaboratori", "assumiamo", "partner operativo", "cerchiamo property", "cerchiamo gestori")
PAROLE_AGENZIA = ("agenzia", "gestiamo", "il nostro servizio", "offriamo il servizio", "gestione completa per proprietari", "channel manager",
                  "affidaci", "servizi di gestione per")
PAROLE_VENDITA = ("in vendita", "vendesi", "prezzo di vendita", "compravendita")
PAROLE_AFFITTO = ("affitto", "affittasi", "vacanze", "casa vacanze", "b&b", "bed and breakfast", "per ospiti", "prenota", "soggiorno", "settimanale")
PAROLE_SEGNALI_A = ("ripubblicat", "ribassat", "prezzo modificato", "ribasso", "offerta speciale", "da tempo", "disponibile da", "sconto")

URL_RE = re.compile(r'https?://[^\s<>"\)\]]+')
FALSI_RE = re.compile(r'(123456|654321|987654|000000|111111|example\.)', re.I)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


def log(*a):
    print(*a, flush=True)


# ---------- verifica link ----------
def check_url(u):
    """'ok' verificato, 'falso' inesistente o generico, 'bloccato' valido ma non accessibile automaticamente."""
    low = u.lower().rstrip(".,;:")
    if FALSI_RE.search(low):
        return "falso"
    if "immobiliare.it" in low and not re.search(r"/annunci/\d{6,}", low):
        return "falso"
    if "subito.it" in low and not re.search(r"-\d{6,}\.htm", low):
        return "falso"
    if "idealista." in low and not re.search(r"/immobile/\d{5,}", low):
        return "falso"
    try:
        with urllib.request.urlopen(urllib.request.Request(u.rstrip(".,;:"), headers=UA), timeout=8) as r:
            return "ok" if r.status < 400 else "bloccato"
    except urllib.error.HTTPError as e:
        return "falso" if e.code in (404, 410) else "bloccato"
    except urllib.error.URLError as e:
        return "falso" if isinstance(e.reason, socket.gaierror) else "bloccato"
    except Exception:
        return "bloccato"


def sospetti(urls):
    """Serie di ID consecutivi sullo stesso dominio (es. 30712345..30712349): costruiti, non letti. Restituisce gli URL sospetti."""
    per_dominio = {}
    for u in urls:
        m = re.search(r"https?://([^/]+)/.*?(\d{6,})", u)
        if m:
            per_dominio.setdefault(m.group(1), []).append((int(m.group(2)), u))
    marcati = set()
    for dom, lista in per_dominio.items():
        lista.sort()
        run = [lista[0]] if lista else []
        for prev, cur in zip(lista, lista[1:]):
            if cur[0] - prev[0] == 1:
                run.append(cur)
            else:
                if len(run) >= 3:
                    marcati.update(u for _, u in run)
                run = [cur]
        if len(run) >= 3:
            marcati.update(u for _, u in run)
    return marcati


# ---------- classificazione deterministica sul testo letto ----------
def classifica(cat_ricerca, c):
    testo = " ".join([c.get("testo_letto", ""), c.get("nome", ""), c.get("tipo", ""), " ".join(c.get("segnali", []) or [])]).lower()
    tipo = (c.get("tipo") or "").lower()
    if any(m in testo for m in PAROLE_C):
        return "C", "cerca collaboratori o partner operativi"
    if any(m in testo for m in PAROLE_B):
        return "B", "chiede espressamente un gestore per il proprio immobile o la propria struttura"
    if any(m in testo for m in PAROLE_AGENZIA) or tipo in ("agenzia", "societa"):
        return "escluso_agenzia", "agenzia o societa' che offre gia' gestione: concorrente"
    if any(m in testo for m in PAROLE_VENDITA) and not any(m in testo for m in PAROLE_AFFITTO):
        return "escluso_vendita", "annuncio di vendita, non di gestione"
    if any(m in testo for m in PAROLE_AFFITTO):
        return "A", "immobile in affitto pubblicato dal proprietario"
    return "escluso_non_pertinente", "nessun segnale di affitto o di gestione nel testo letto"


def priorita(cat_finale, c):
    if cat_finale in ("B", "C"):
        return "alta"
    testo = " ".join([c.get("testo_letto", ""), " ".join(c.get("segnali", []) or [])]).lower()
    n_foto = c.get("n_foto")
    lunghezza = c.get("lunghezza_descrizione")
    segnale = any(m in testo for m in PAROLE_SEGNALI_A)
    poco = (isinstance(n_foto, int) and n_foto <= 3) or (isinstance(lunghezza, int) and lunghezza < 300)
    if segnale or poco:
        return "alta"
    return "media"


# ---------- ricerca ----------
def _web_call(prompt, budget=90, max_out=1800):
    t0 = time.time()
    last = "nessun risultato"
    for model in ("gpt-4.1", "gpt-4o-mini"):
        for tool in ("web_search_preview", "web_search"):
            left = budget - (time.time() - t0)
            if left < 6:
                raise RuntimeError("tempo scaduto: " + last)
            try:
                body = json.dumps({"model": model, "tools": [{"type": tool}], "input": prompt, "max_output_tokens": max_out}).encode()
                req = urllib.request.Request("https://api.openai.com/v1/responses", data=body,
                                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
                with urllib.request.urlopen(req, timeout=int(left)) as r:
                    j = json.loads(r.read().decode())
                txt = "".join(c.get("text", "") for o in j.get("output", []) if o.get("type") == "message"
                              for c in o.get("content", []) if c.get("type") == "output_text")
                query = []
                for o in j.get("output", []):
                    if o.get("type") == "web_search_call":
                        act = o.get("action") or {}
                        q = act.get("query") or ""
                        if q:
                            query.append(q)
                if txt.strip():
                    return txt, query
            except Exception as e:
                last = str(e)[:90]
    raise RuntimeError(last)


def prompt_ricerca(cat, gruppo_zona, zone, gruppo_fonti):
    return ("Cerca sul web SOLO pagine pubbliche e risultati indicizzati. Non accedere ad aree riservate, non aggirare protezioni, "
            "non inventare annunci, link, nomi o recapiti. "
            "Categoria: " + CATEGORIE[cat]["titolo"] + ". Cosa cercare: " + CATEGORIE[cat]["cerca"] + " "
            "Zone (usa anche le singole localita' e frazioni): " + ", ".join(zone) + ". "
            "Fonti da interrogare in questa ricerca: " + FONTI[gruppo_fonti] + ". "
            "Rispondi SOLO con un array JSON, nessun testo prima o dopo. Ogni elemento: "
            "{\"url\": link diretto alla pagina pubblica letta, \"nome\": immobile o societa', "
            "\"localita\": localita' scritta nella pagina, \"tipo\": privato | agenzia | societa | sconosciuto, "
            "\"testo_letto\": frase breve copiata o parafrasata da cio' che hai letto, "
            "\"segnali\": lista di segnali commerciali osservati (es. ripubblicato, prezzo ribassato, poche foto), "
            "\"n_foto\": numero di foto se lo leggi, altrimenti null, "
            "\"lunghezza_descrizione\": caratteri della descrizione se li leggi, altrimenti null, "
            "\"contatto_pubblico\": recapito scritto nella pagina, altrimenti null}. "
            "Massimo 5 elementi. Se non trovi nulla di pertinente rispondi []. ")


def estrai_json(txt):
    a, b = txt.find("["), txt.rfind("]")
    if a < 0 or b < a:
        return None
    try:
        v = json.loads(txt[a:b + 1])
        return v if isinstance(v, list) else None
    except Exception:
        return None


def raccogli(log_ricerche):
    """Una ricerca per ogni combinazione categoria x gruppo di zone x gruppo di fonti. Tutte registrate."""
    candidati = []
    for cat in CATEGORIE:
        for gz, zone in GRUPPI_ZONA.items():
            for gf in FONTI:
                nome = "%s | %s | %s" % (cat, gz, gf)
                try:
                    txt, query = _web_call(prompt_ricerca(cat, gz, zone, gf))
                    lista = estrai_json(txt)
                    if lista is None:
                        log_ricerche.append({"nome": nome, "esito": "risposta non leggibile", "risultati": 0, "query": query})
                        continue
                    for c in lista:
                        c.update({"cat_ricerca": cat, "gruppo_zona": gz, "gruppo_fonti": gf})
                    candidati += lista
                    esito = "zero risultati" if not lista else "ok"
                    if not query:
                        esito += " (nessuna ricerca web registrata dal motore: verificare)"
                    log_ricerche.append({"nome": nome, "esito": esito, "risultati": len(lista), "query": query})
                except Exception as e:
                    log_ricerche.append({"nome": nome, "esito": "NON RIUSCITA: " + str(e)[:60], "risultati": 0, "query": []})
    return candidati


# ---------- valutazione ----------
def valuta(candidati, d):
    esiti = {"verificato": [], "manuale": [], "scartati": {}, "duplicati": 0}
    urls = [(c.get("url") or "").strip() for c in candidati]
    sospetti_set = sospetti([u for u in urls if u.startswith("http")])
    visti = set()
    for c, url in zip(candidati, urls):
        if not url.startswith("http"):
            esiti["scartati"]["link_non_valido"] = esiti["scartati"].get("link_non_valido", 0) + 1
            continue
        k = P.normalizza(url)
        if k in visti:
            continue
        visti.add(k)
        if url in sospetti_set:
            esiti["scartati"]["id_sequenziali_sospetti"] = esiti["scartati"].get("id_sequenziali_sospetti", 0) + 1
            continue
        stato_link = check_url(url)
        if stato_link == "falso":
            esiti["scartati"]["link_falso_o_generico"] = esiti["scartati"].get("link_falso_o_generico", 0) + 1
            continue
        cat, motivo = classifica(c["cat_ricerca"], c)
        if cat.startswith("escluso"):
            esiti["scartati"][cat] = esiti["scartati"].get(cat, 0) + 1
            continue
        c.update({"url": url, "categoria": cat, "motivo": motivo, "priorita": priorita(cat, c),
                  "link_stato": "verificato" if stato_link == "ok" else "da verificare manualmente"})
        if P.opportunita_esistente(d, url):
            esiti["duplicati"] += 1
            continue
        (esiti["verificato"] if stato_link == "ok" else esiti["manuale"]).append(c)
    return esiti


# ---------- pacchetto operatore ----------
def pacchetto_per(o):
    """Lettera, presentazione e due proposte, basati solo sui fatti osservati. Nessun numero inventato."""
    fatti = {"categoria": o["categoria"], "nome": o.get("titolo", ""), "localita": o.get("localita", ""), "fonte": o["fonte"],
             "osservato": o.get("osservato", ""), "segnali": o.get("segnali", []), "n_foto": o.get("n_foto"),
             "tipo": o.get("tipo_soggetto", ""), "contatto_pubblico": o.get("contatto_pubblico")}
    prompt = ("Prepara, in italiano e in testo semplice senza asterischi, un pacchetto commerciale per Alessandro (host del B&B Ale House "
              "al Lido delle Nazioni, esperienza di accoglienza, prenotazioni, check-in, pulizie, comunicazione). Usa SOLO questi fatti: "
              + json.dumps(fatti, ensure_ascii=False) + ". "
              "Sezioni con titolo: LETTERA (7 righe max, osservazione concreta, proposta di chiacchierata senza impegno, "
              "se non interessa basta un cenno); PRESENTAZIONE (4 righe sul servizio); "
              "PROPOSTA 1 GESTIONE COMPLETA (servizi inclusi, responsabilita' del gestore e del proprietario, nessuna cifra inventata); "
              "PROPOSTA 2 GESTIONE CONDIVISA (ipotesi 70% proprietario e 30% gestore calcolata su una base esplicita: "
              "ricavi lordi di affitto meno costi operativi documentati, come pulizie, commissioni delle piattaforme e utenze, "
              "che restano esclusi dalla base; le imposte non entrano nella base e restano a carico di ciascuno per la propria parte; "
              "indica che e' una ipotesi da negoziare); "
              "BOZZA CONTRATTO (solo punti principali, con la dicitura da sottoporre a commercialista e avvocato). "
              "Non promettere guadagni, non inventare numeri, recensioni o problemi del proprietario.")
    try:
        return _web_call(prompt, budget=60, max_out=1500)[0].strip()
    except Exception as e:
        return "[pacchetto non generato: %s]" % str(e)[:60]


# ---------- archivio ----------
def salva(d, esiti, stat_ricerche):
    P.crea_progetto(d, PROGETTO, PROGETTO_TITOLO, nota="Radar gestione clienti: categorie A, B, C")
    salvate = []
    for c in esiti["verificato"] + esiti["manuale"]:
        o = P.aggiungi_opportunita(d, PROGETTO, c.get("localita") or c.get("gruppo_zona"), c["url"], titolo=c.get("nome", ""),
                                   info_mancanti=["prezzo", "recapito del proprietario", "stato reale della struttura"])
        if not o:
            continue
        o.update({"categoria": c["categoria"], "categoria_nome": CATEGORIE.get(c["categoria"], {}).get("titolo", c["categoria"]),
                  "priorita": c["priorita"], "motivo": c["motivo"], "link_stato": c["link_stato"], "tipo_soggetto": c.get("tipo", ""),
                  "segnali": c.get("segnali", []), "n_foto": c.get("n_foto"), "osservato": c.get("testo_letto", ""),
                  "contatto_pubblico": c.get("contatto_pubblico"), "localita": c.get("localita", ""),
                  "prossima_azione": "aprire il link e verificare; poi inviare il pacchetto se confermato",
                  "prossimo_ricontatto": (date.today() + timedelta(days=7)).isoformat(),
                  "pacchetto": pacchetto_per({"categoria": c["categoria"], "titolo": c.get("nome", ""), "localita": c.get("localita", ""),
                                              "fonte": c["url"], "osservato": c.get("testo_letto", ""), "segnali": c.get("segnali", []),
                                              "n_foto": c.get("n_foto"), "tipo_soggetto": c.get("tipo", ""),
                                              "contatto_pubblico": c.get("contatto_pubblico")})})
        salvate.append(o)
    d["ricerche"].append({"data": P.ora(), "progetto": PROGETTO, "modalita": "gestione_clienti_v3",
                          "ricerche": stat_ricerche, "scartati": esiti["scartati"], "duplicati": esiti["duplicati"],
                          "verificati": len(esiti["verificato"]), "da_verificare_manualmente": len(esiti["manuale"]),
                          "link_trovati": [o["fonte"] for o in salvate], "nuove_opportunita": [o["id"] for o in salvate]})
    P.salva(d)
    return salvate


# ---------- report Telegram separati per categoria ----------
def report(cat, salvate, esiti, stat_ricerche):
    voci = [o for o in salvate if o["categoria"] == cat]
    titolo = "JARVIS - " + cat + ": " + CATEGORIE[cat]["titolo"]
    righe = [titolo, ""]
    if voci:
        for o in sorted(voci, key=lambda x: {"alta": 0, "media": 1, "bassa": 2}[x["priorita"]]):
            righe += [
                "- Immobile o societa': " + (o.get("titolo") or "non indicato"),
                "  Localita': " + (o.get("localita") or "non indicata"),
                "  Link (" + o["link_stato"] + "): " + o["fonte"],
                "  Soggetto: " + (o.get("tipo_soggetto") or "non identificato"),
                "  Segnali osservati: " + (", ".join(o.get("segnali") or []) or "nessuno nel testo letto"),
                "  Perche' interessante: " + o["motivo"],
                "  Recapito pubblico: " + (o.get("contatto_pubblico") or "non disponibile"),
                "  Priorita': " + o["priorita"],
                "  Prossima azione: " + o["prossima_azione"],
                "",
            ]
    else:
        righe.append("Nessuna opportunita' verificata in questa categoria.")
        righe.append("")
    qui = [r for r in stat_ricerche if r["nome"].startswith(cat + " |")]
    righe.append("Ricerche di questa categoria:")
    for r in qui:
        righe.append("- %s: %s, risultati %d" % (r["nome"], r["esito"], r["risultati"]))
        for q in r.get("query", []):
            righe.append("    query eseguita: " + q)
    zero = [r["nome"] for r in qui if r["esito"] == "zero risultati"]
    fallite = [r["nome"] for r in qui if r["esito"].startswith("NON RIUSCITA") or r["esito"].startswith("risposta")]
    if zero:
        righe.append("Zero risultati in: " + "; ".join(zero) + ".")
    if fallite:
        righe.append("Ricerche NON riuscite (non significa assenza di opportunita'): " + "; ".join(fallite) + ".")
    return "\n".join(righe).strip()


def invia(testo):
    if DRY or not TOKEN or not CHAT_ID:
        log("[TELEGRAM non inviato]\n" + testo)
        return False
    body = json.dumps({"chat_id": CHAT_ID, "text": testo[:3900], "disable_web_page_preview": True}).encode()
    req = urllib.request.Request("https://api.telegram.org/bot" + TOKEN + "/sendMessage", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15):
        return True


def main():
    d = P.carica()
    stat = []
    candidati = raccogli(stat)
    esiti = valuta(candidati, d)
    salvate = salva(d, esiti, stat)
    for cat in ("A", "B", "C"):
        invia(report(cat, salvate, esiti, stat))
    log("ricerche: %d | candidati: %d | verificati: %d | da verificare manualmente: %d | scartati: %s | duplicati: %d"
        % (len(stat), len(candidati), len(esiti["verificato"]), len(esiti["manuale"]), esiti["scartati"], esiti["duplicati"]))


if __name__ == "__main__":
    main()
