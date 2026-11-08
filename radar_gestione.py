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
import os, re, json, socket, time, unicodedata, urllib.request, urllib.error
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


SEGNALI_FORTI = ("ripubblicat", "ribassat", "prezzo modificato", "prezzo ribassato", "da tempo", "disponibile da", "ribasso")


CITTA_FUORI_ZONA = ["roma", "milano", "pisa", "firenze", "napoli", "torino", "venezia", "bologna", "genova", "rimini",
                    "riccione", "cesenatico", "cattolica", "jesolo", "bibione", "sanremo", "portofino", "cortina"]
LISTING_ID = {"immobiliare.it": r"/annunci/\d{6,}", "idealista.": r"/immobile/\d{5,}",
              "subito.it": r"-\d{6,}\.htm", "casadaprivato.it": r"/annunci/\d+"}
GENERICO = ("ricerca", "cerca", "search", "tag", "categoria", "lista", "risultati", "italia/", "vendita/appartamenti/")


def pagina_singola(url):
    """True solo per un annuncio o una pagina specifica. False per homepage, ricerche, liste, portali generici."""
    low = url.lower()
    for dom, pat in LISTING_ID.items():
        if dom in low:
            return re.search(pat, low) is not None
    path = re.sub(r"https?://[^/]+", "", low).split("?")[0].strip("/")
    if not path or path.count("/") < 1:
        return False
    if any(g in path for g in GENERICO):
        return False
    return True


def prova_gestione(c):
    """Vale solo se la frase di prova e' stata trovata nella pagina indicata (verificata in valuta)."""
    return bool(c.get("prova_verificata"))


def stato_commerciale(cat, c, link_ok=False):
    """'interessante' = cliente verificato: B o C, con prova e link verificato. Tutto il resto: da approfondire.
    Gli annunci di privati non diventano mai clienti da soli (poche foto, prezzi ribassati non bastano)."""
    if cat in ("B", "C") and link_ok and prova_gestione(c):
        return "interessante"
    return "da_approfondire"


def priorita(cat_finale, c, link_ok=False):
    return "alta" if stato_commerciale(cat_finale, c, link_ok) == "interessante" else "media"


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
            "\"contatto_pubblico\": recapito scritto nella pagina, altrimenti null, \"pagina_prova\": per le richieste di gestore, l\'URL di una pagina DIVERSA dalla homepage che contiene la richiesta, altrimenti null, \"frase_prova\": la frase esatta letta in pagina che dimostra la richiesta, altrimenti null}. "
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

def _norm(s):
    """Minuscole, senza accenti, spazi normalizzati: per confronti di testo."""
    t = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


ZONA_TERMINI = {_norm(z): gz for gz, zone in GRUPPI_ZONA.items() for z in zone}


def localita_in_zona(loc):
    """(gruppo, termine) se la localita' e' una delle zone richieste, altrimenti None. Pisa -> None."""
    n = _norm(loc)
    if not n:
        return None
    for term, gz in sorted(ZONA_TERMINI.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"(^|\W)" + re.escape(term) + r"(\W|$)", n):
            return gz, term
    return None


def leggi_pagina(u):
    """('ok', testo) se la pagina si apre; ('falso', '') se non esiste o e' generica; ('bloccato', '') se non accessibile."""
    if check_url(u) == "falso":
        return "falso", ""
    try:
        with urllib.request.urlopen(urllib.request.Request(u.rstrip(".,;:"), headers=UA), timeout=10) as r:
            return "ok", r.read(400000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return ("falso" if e.code in (404, 410) else "bloccato"), ""
    except urllib.error.URLError as e:
        return ("falso" if isinstance(e.reason, socket.gaierror) else "bloccato"), ""
    except Exception:
        return "bloccato", ""


def verifica_contatto(c, corpo):
    """Il recapito resta solo se compare nel testo della pagina. Altrimenti viene tolto."""
    cont = (c.get("contatto_pubblico") or "").strip()
    if not cont:
        return
    dig = re.sub(r"\D", "", cont)
    ok = (len(dig) >= 6 and dig in re.sub(r"\D", "", corpo)) or (len(_norm(cont)) >= 6 and _norm(cont) in _norm(corpo))
    if not ok:
        c["contatto_non_verificato"] = cont
        c["contatto_pubblico"] = None


def prova_su_pagina(c, url, corpo):
    """La frase che dimostra la richiesta di gestione deve comparire davvero nella pagina indicata."""
    frase = _norm(c.get("frase_prova") or "")
    pagina = (c.get("pagina_prova") or "").strip()
    if len(frase) < 15 or not pagina or not pagina_singola(pagina):
        return False
    if pagina == url:
        testo = corpo
    else:
        st, testo = leggi_pagina(pagina)
        if st != "ok":
            return False
    return frase in _norm(testo)


def scarta(esiti, motivo):
    esiti["scartati"][motivo] = esiti["scartati"].get(motivo, 0) + 1


def valuta(candidati, d):
    """Filtro effettivo: link reale, pagina specifica, zona verificata nel testo della pagina,
    contatto presente nella pagina, prova verificata per le richieste di gestione."""
    esiti = {"verificato": [], "manuale": [], "scartati": {}, "duplicati": 0}
    urls = [(c.get("url") or "").strip() for c in candidati]
    sospetti_set = sospetti([u for u in urls if u.startswith("http")])
    visti = set()
    for c, url in zip(candidati, urls):
        if not url.startswith("http"):
            scarta(esiti, "link_non_valido"); continue
        k = P.normalizza(url)
        if k in visti:
            continue
        visti.add(k)
        if url in sospetti_set:
            scarta(esiti, "id_sequenziali_sospetti"); continue
        if not pagina_singola(url):
            scarta(esiti, "pagina_generica"); continue
        stato_pagina, corpo = leggi_pagina(url)
        if stato_pagina == "falso":
            scarta(esiti, "link_falso_o_generico"); continue
        if stato_pagina != "ok":
            scarta(esiti, "pagina_non_accessibile_non_verificabile"); continue
        zona = localita_in_zona(c.get("localita"))
        if zona is None:
            scarta(esiti, "fuori_zona_o_localita_non_verificabile"); continue
        gruppo, termine = zona
        cn = _norm(corpo)
        inizio = cn[:300]
        if any(re.search(r"(^|\W)" + re.escape(c) + r"(\W|$)", inizio) for c in CITTA_FUORI_ZONA) \
                and not re.search(r"(^|\W)" + re.escape(termine) + r"(\W|$)", inizio):
            scarta(esiti, "pagina_di_altra_localita"); continue
        if termine not in cn:
            scarta(esiti, "pagina_non_corrisponde_alla_localita"); continue
        parole = [w for w in _norm(c.get("nome", "")).split() if len(w) >= 5]
        if parole and not any(w in cn for w in parole):
            scarta(esiti, "pagina_non_corrisponde_al_nome"); continue
        verifica_contatto(c, corpo)
        testo_stato = " ".join([c.get("testo_letto", ""), c.get("nome", "")]).lower()
        if any(m in testo_stato for m in ("scadut", "venduto", "affittato", "non piu' disponibile", "non più disponibile", "annuncio rimosso", "offline")):
            scarta(esiti, "scaduto_o_non_disponibile"); continue
        cat, motivo = classifica(c["cat_ricerca"], c)
        if cat.startswith("escluso"):
            scarta(esiti, cat); continue
        c["gruppo_zona"] = gruppo
        c["prova_verificata"] = prova_su_pagina(c, url, corpo) if cat in ("B", "C") else False
        c.update({"url": url, "categoria": cat, "motivo": motivo, "priorita": priorita(cat, c, True),
                  "stato_commerciale": stato_commerciale(cat, c, True), "link_stato": "verificato"})
        if P.opportunita_esistente(d, url):
            esiti["duplicati"] += 1
            continue
        esiti["verificato"].append(c)
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
        o.update({"stato": "nuovo", "stato_commerciale": c.get("stato_commerciale", "da_approfondire"),
                  "pagina_prova": c.get("pagina_prova"), "frase_prova": c.get("frase_prova"),
                  "categoria": c["categoria"], "categoria_nome": CATEGORIE.get(c["categoria"], {}).get("titolo", c["categoria"]),
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
    if cat == "A":
        voci = [o for o in salvate if o["categoria"] == "A"][:2]
        titolo = "JARVIS - A: IMMOBILI DA APPROFONDIRE (NON SONO CLIENTI)"
        intro = "Annunci di privati: nessun interesse dimostrato. Da valutare solo se vuoi."
    else:
        voci = [o for o in salvate if o["categoria"] == cat and o.get("stato_commerciale") == "interessante"]
        titolo = "JARVIS - " + cat + ": " + CATEGORIE[cat]["titolo"]
        intro = ""
    righe = [titolo]
    if intro:
        righe.append(intro)
    righe.append("")
    if voci:
        for o in voci:
            righe += [
                "- Soggetto: " + (o.get("tipo_soggetto") or "non identificato") + " | " + (o.get("titolo") or "non indicato"),
                "  Localita': " + (o.get("localita") or "non indicata"),
                "  Link verificato: " + o["fonte"],
                "  Prova della richiesta: " + (o.get("pagina_prova") or "nessuna"),
                "  Motivo: " + o["motivo"],
                "  Recapito pubblico: " + (o.get("contatto_pubblico") or "non disponibile"),
                "  Stato: " + o.get("stato", "nuovo") + " | Prossima azione: approvare il dossier e decidere se contattare",
                "",
            ]
    else:
        if cat == "A":
            righe.append("Nessun immobile da approfondire questa settimana.")
        else:
            righe.append("NESSUN CLIENTE VERIFICATO.")
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
        righe.append("Ricerche NON riuscite (non significa assenza di clienti): " + "; ".join(fallite) + ".")
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


MAX_PER_CATEGORIA = 3
PAROLE_D = ("b&b", "bed and breakfast", "affittacamere", "struttura", "hotel", "casa vacanze", "appartamenti turistici", "residence")


def invia_lungo(testo):
    """Il pacchetto puo' superare il limite di Telegram: lo spezza in blocchi."""
    for i in range(0, len(testo), 3500):
        invia(testo[i:i + 3500])


def categoria_telegram(o):
    """A, B, C, D. D = strutture e immobili con gestione esternalizzabile (dalla categoria A, per parole chiave)."""
    if o.get("categoria") in ("B", "C"):
        return o["categoria"]
    testo = " ".join([o.get("titolo", "") or "", o.get("osservato", "") or "", o.get("tipo_soggetto", "") or ""]).lower()
    if any(m in testo for m in PAROLE_D):
        return "D"
    return "A"


def scegli(salvate, cat):
    """Solo opportunita' con link verificato e motivo concreto. Mai riempire con annunci generici."""
    voci = []
    for o in salvate:
        if categoria_telegram(o) != cat or o.get("link_stato") != "verificato":
            continue
        if cat in ("B", "C"):
            if o.get("stato_commerciale") != "interessante":
                continue
        elif not o.get("segnali"):
            continue
        voci.append(o)
    voci.sort(key=lambda x: {"alta": 0, "media": 1, "bassa": 2}[x.get("priorita", "media")])
    return voci[:MAX_PER_CATEGORIA]


def formato_dossier(o, n, cat):
    """Dossier autonomo e copiabile, con le etichette che dossier_app.py sa leggere."""
    livello = ("link aperto e verificato; prova della richiesta: " + (o.get("pagina_prova") or "nessuna")
               if o.get("stato_commerciale") == "interessante" else
               "link aperto e verificato; nessuna prova di richiesta di gestione (da approfondire)")
    proposta = ("contattare solo dopo approvazione del pacchetto, tramite il recapito pubblico"
                if o.get("stato_commerciale") == "interessante" else
                "non contattare ora: approfondire l'immobile prima di qualunque messaggio")
    prove = ", ".join(o.get("segnali") or []) or "nessuna nel testo letto"
    return "\n".join([
        "DOSSIER OPPORTUNITA' n.%d - ID %d (categoria %s)" % (n, o["id"], cat),
        "ID opportunita': %d" % o["id"],
        "Categoria: " + cat + " - " + (CATEGORIE.get(o.get("categoria"), {}).get("titolo", "") if cat in ("B", "C") else "immobile in affitto"),
        "Nome immobile o struttura: " + (o.get("titolo") or "non indicato"),
        "Localita': " + (o.get("localita") or "non indicata"),
        "Link diretto verificato: " + o["fonte"],
        "Soggetto: " + (o.get("tipo_soggetto") or "sconosciuto"),
        "Recapiti pubblici: " + (o.get("contatto_pubblico") or "nessuno scritto nella pagina"),
        "Prove concrete raccolte: " + ("richiesta di gestione: " + (o.get("frase_prova") or "") if o.get("stato_commerciale") == "interessante" else "segnali osservati: " + prove),
        "Motivo dell'interesse commerciale: " + o["motivo"],
        "Livello di verifica: " + livello,
        "Proposta di contatto consigliata: " + proposta,
        "Azione successiva: approvare il pacchetto n.%d e decidere; nessun messaggio inviato" % n,
    ])


def messaggio_vuoto(cat):
    if cat in ("B", "C"):
        return "JARVIS - " + cat + ": NESSUN CLIENTE VERIFICATO."
    return "JARVIS - " + cat + ": nessuna opportunita' valida questa settimana."


def main():
    import operatore as OP
    try:
        d = P.carica()
    except P.ArchivioError as e:
        invia("JARVIS - ARCHIVIO NON RAGGIUNGIBILE: radar annullato, nessuna modifica salvata. " + str(e)[:150])
        log("archivio non raggiungibile: " + str(e))
        return
    stat = []
    candidati = raccogli(stat)
    esiti = valuta(candidati, d)
    try:
        salvate = salva(d, esiti, stat)
    except P.ArchivioError as e:
        invia("JARVIS - ARCHIVIO: salvataggio non riuscito, nessuna modifica. " + str(e)[:150])
        log("salvataggio non riuscito: " + str(e))
        return
    inviati = 0
    for cat in ("B", "C", "A", "D"):
        voci = scegli(salvate, cat)
        if not voci:
            invia(messaggio_vuoto(cat))
            continue
        for n, o in enumerate(voci, 1):
            try:
                OP.dossier(d, o["id"])
                P.salva(d)
            except Exception as e:
                o["dossier"] = "[pacchetto non generato: %s]" % str(e)[:80]
            invia(formato_dossier(o, n, cat))
            invia_lungo("PACCHETTO n.%d (ID %d)\n\n" % (n, o["id"]) + o.get("dossier", ""))
            inviati += 1
    log("ricerche: %d | candidati: %d | verificati: %d | salvate: %d | opportunita' inviate: %d | scartati: %s | duplicati: %d"
        % (len(stat), len(candidati), len(esiti["verificato"]), len(salvate), inviati, esiti["scartati"], esiti["duplicati"]))


if __name__ == "__main__":
    main()
