"""
JARVIS - Radar acquisizione clienti per gestione immobiliare e turistica.
Modulo INDIPENDENTE da radar.py (che resta invariato, per gli immobili da acquistare).

Cosa fa:
1. Cerca sul web (ricerca pubblica, nessun accesso riservato) proprietari e strutture
   che potrebbero avere bisogno di un property manager, nelle zone prioritarie.
2. Per ogni risultato verifica il link e classifica la categoria:
   - proprietario_cerca_gestore      -> priorita' alta
   - annuncio_poco_curato            -> priorita' alta
   - casa_gestita_proprietario       -> priorita' media
   - agenzia_concorrente             -> ESCLUSA
   - immobile_in_vendita             -> ESCLUSA (ci pensa radar.py)
   - non_pertinente                  -> ESCLUSA
3. Salva ogni opportunita' in progetti.json (senza duplicati) con stato, fonte, data,
   categoria, priorita', motivo, prossima azione e lettera di acquisizione.
4. Manda su Telegram un riepilogo. Non invia nulla ai proprietari: prepara, tu invii.

Non inventa: se un dato non c'e' nel testo letto, non lo scrive.
Uso:  python3 radar_gestione.py   (senza argomenti)
Variabili: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, OPENAI_API_KEY (opzionale: JARVIS_DRY=1 per stampare senza inviare)
"""
import os, re, sys, json, socket, urllib.request, urllib.error
from datetime import date

import progetti as P

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KEY = os.environ.get("OPENAI_API_KEY", "")
DRY = os.environ.get("JARVIS_DRY") == "1"
PROGETTO = "gestione-clienti"
PROGETTO_TITOLO = "Acquisizione clienti per gestione immobiliare e turistica"

ZONE = {
    "lido": "Lido delle Nazioni, Comacchio, Lido di Volano, Lido di Pomposa, Lido degli Estensi, Lido di Spina, Porto Garibaldi (Lidi Ferraresi)",
    "como": "Como centro e provincia di Como (Capiago Intimiano, Cantu', Montorfano, Erba, Cernobbio)",
}

CATEGORIE_CLIENTE = {"proprietario_cerca_gestore": "alta", "casa_sfitta_o_poco_affittata": "alta",
                     "annuncio_poco_curato": "alta", "casa_gestita_proprietario": "media"}
CATEGORIE_ESCLUSE = {"agenzia_concorrente", "immobile_in_vendita", "non_pertinente"}

URL_RE = re.compile(r'https?://[^\s<>"\)\]]+')
FALSI_RE = re.compile(r'(123456|654321|987654|000000|111111|example\.)', re.I)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

AGENZIA_MARKERS = ("agenzia", "property manager", "gestiamo", "il nostro servizio", "offriamo il servizio", "gestione completa per proprietari",
                   "affidaci", "gestione per proprietari", "channel manager", "servizi di gestione per")
SFITTA_MARKERS = ("ripubblicat", "ribassat", "prezzo ribassato", "ribasso", "offerta speciale", "da tempo", "disponibile da", "ultimo minuto", "sconto")
VENDITA_MARKERS = ("in vendita", "vendesi", "prezzo di vendita", "compravendita")
CERCA_MARKERS = ("cerco gestore", "cerchiamo gestore", "cerco property", "cercasi gestore", "cerco qualcuno che gestisca",
                 "cerco chi gestisca", "cercasi host", "cerco co-host", "cerco persona per gestire", "gestore cercasi")
GESTITA_MARKERS = ("affitto", "affittasi", "vacanze", "casa vacanze", "b&b", "bed and breakfast", "per ospiti", "prenota", "soggiorno")


def log(*a):
    print(*a, flush=True)


def check_url(u):
    """Verifica il link: 'ok', 'falso' (inesistente/generico) o 'bloccato' (il sito non risponde al controllo)."""
    u = u.rstrip(".,;:")
    low = u.lower()
    if FALSI_RE.search(low):
        return "falso"
    if "immobiliare.it" in low and not re.search(r"/annunci/\d{6,}", low):
        return "falso"
    if "subito.it" in low and not re.search(r"-\d{6,}\.htm", low):
        return "falso"
    if "idealista." in low and not re.search(r"/immobile/\d{5,}", low):
        return "falso"
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=8) as r:
            return "ok" if r.status < 400 else "bloccato"
    except urllib.error.HTTPError as e:
        return "falso" if e.code in (404, 410) else "bloccato"
    except urllib.error.URLError as e:
        return "falso" if isinstance(e.reason, socket.gaierror) else "bloccato"
    except Exception:
        return "bloccato"


def classifica(c):
    """Classificazione deterministica sul testo che il modello ha letto dalla pagina.
    Restituisce (categoria, motivo). Usa SOLO il testo fornito, non inventa."""
    testo = " ".join([c.get("testo_letto", ""), c.get("tipo_fonte", ""), c.get("nome", "")]).lower()
    if any(m in testo for m in AGENZIA_MARKERS):
        return "agenzia_concorrente", "offre gia' un servizio di gestione o si presenta come agenzia"
    if any(m in testo for m in CERCA_MARKERS):
        return "proprietario_cerca_gestore", "chiede esplicitamente un gestore o un host per il proprio immobile"
    if any(m in testo for m in VENDITA_MARKERS) and not any(m in testo for m in GESTITA_MARKERS):
        return "immobile_in_vendita", "annuncio di vendita, non di gestione"
    if any(m in testo for m in SFITTA_MARKERS):
        return "casa_sfitta_o_poco_affittata", "annuncio di affitto ripubblicato, con prezzo sceso o da tempo senza prenotazioni"
    if any(m in testo for m in GESTITA_MARKERS):
        n_foto = c.get("n_foto")
        lunghezza = c.get("lunghezza_descrizione")
        poco = (isinstance(n_foto, int) and n_foto <= 3) or (isinstance(lunghezza, int) and lunghezza < 300)
        if poco:
            return "annuncio_poco_curato", "annuncio pubblico del proprietario con " + (
                ("%d foto" % n_foto if isinstance(n_foto, int) else "poche foto") +
                (" e descrizione breve" if isinstance(lunghezza, int) and lunghezza < 300 else ""))
        return "casa_gestita_proprietario", "casa in affitto gestita direttamente dal proprietario"
    return "non_pertinente", "nessun segnale di gestione nel testo letto"


def priorita(categoria):
    return CATEGORIE_CLIENTE.get(categoria, "bassa")


def _web_call(prompt, budget=110):
    import time
    t0 = time.time()
    last = "nessun risultato"
    for model in ("gpt-4.1", "gpt-4o-mini"):
        for tool in ("web_search_preview", "web_search"):
            left = budget - (time.time() - t0)
            if left < 6:
                raise RuntimeError("tempo scaduto " + last)
            try:
                body = json.dumps({"model": model, "tools": [{"type": tool}],
                                   "input": prompt, "max_output_tokens": 1800}).encode()
                req = urllib.request.Request("https://api.openai.com/v1/responses", data=body,
                                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
                with urllib.request.urlopen(req, timeout=int(left)) as r:
                    j = json.loads(r.read().decode())
                txt = "".join(c.get("text", "") for o in j.get("output", []) if o.get("type") == "message"
                              for c in o.get("content", []) if c.get("type") == "output_text")
                if txt.strip():
                    return txt
            except Exception as e:
                last = str(e)[:90]
    raise RuntimeError(last)


def prompt_ricerca(zona_nome):
    return ("Cerca sul web, solo su pagine pubbliche, proprietari e strutture ricettive di questa zona: " + zona_nome + ". "
            "Cerca ANNUNCI PRIVATI DI AFFITTO (vacanze, settimanali, stagionali, brevi) pubblicati direttamente dal proprietario, "
            "su portali immobiliari, siti locali e annunci pubblici, nella zona indicata. "
            "Cerca soprattutto case che sembrano sfitte o poco affittate: annunci vecchi, ripubblicati, con prezzo che scende, con poche foto o descrizione breve. "
            "Cerca anche proprietari che chiedono un gestore o un host. "
            "Escludi annunci di vendita e agenzie o property manager che offrono gia' gestione. "
            "Rispondi SOLO con un array JSON, nessun testo prima o dopo. Ogni elemento: "
            "{\"url\": link diretto alla pagina pubblica, \"nome\": nome dell'immobile o dell'attivita' se scritto, "
            "\"localita\": localita' scritta nella pagina, "
            "\"testo_letto\": una frase breve copiata o parafrasata da cio' che hai letto nella pagina, "
            "\"tipo_fonte\": tipo di pagina (annuncio privato, sito di struttura, portale), "
            "\"n_foto\": numero di foto visibili se lo leggi, altrimenti null, "
            "\"lunghezza_descrizione\": lunghezza in caratteri della descrizione se la leggi, altrimenti null}. "
            "Massimo 6 elementi. Se non trovi nulla di pertinente, rispondi con []. Non inventare link ne' dati.")


def estrai_json(txt):
    a, b = txt.find("["), txt.rfind("]")
    if a < 0 or b < a:
        return []
    try:
        v = json.loads(txt[a:b + 1])
        return v if isinstance(v, list) else []
    except Exception:
        return []


def prompt_lettera(o):
    fatti = {"nome": o.get("nome", ""), "localita": o.get("localita", ""), "fonte": o["fonte"],
             "osservato": o.get("testo_letto", ""), "n_foto": o.get("n_foto"), "categoria": o["categoria"], "motivo": o["motivo"]}
    return ("Scrivi una lettera di proposta di gestione immobiliare, in italiano, a nome di Alessandro (host del B&B Ale House al Lido delle Nazioni, "
            "esperienza nell'accoglienza degli ospiti, prenotazioni, check-in, pulizie e comunicazione). "
            "Usa SOLO questi fatti osservati, senza inventare numeri, recensioni, problemi o recapiti: " + json.dumps(fatti, ensure_ascii=False) + ". "
            "Indica un'osservazione concreta sull'annuncio, una proposta di chiacchierata senza impegno, e che se non interessa basta un cenno. "
            "Niente promesse di guadagno, niente prezzi o commissioni, massimo 7 righe, testo semplice senza asterischi.")


def lettera_per(o):
    try:
        txt = _web_call(prompt_lettera(o), budget=40)
        return re.sub(r"\*+", "", txt).strip()
    except Exception as e:
        return "[lettera non generata: %s]" % str(e)[:60]


def raccogli():
    candidati = []
    for chiave, nome in ZONE.items():
        try:
            txt = _web_call(prompt_ricerca(nome))
            trovati = estrai_json(txt)
            for c in trovati:
                c["zona"] = chiave
            candidati += trovati
            log("zona %s: %d candidati dal modello" % (chiave, len(trovati)))
        except Exception as e:
            log("zona %s: ricerca non riuscita (%s)" % (chiave, str(e)[:80]))
    return candidati


def valuta(candidati, d):
    """Verifica link, classifica, esclude, deduplica. Ritorna (accettate, scartate_per_categoria, duplicati, falsi)."""
    accettate, scartate, duplicati, falsi = [], {}, 0, 0
    visti = set()
    for c in candidati:
        url = (c.get("url") or "").strip()
        if not url.startswith("http"):
            falsi += 1
            continue
        k = P.normalizza(url)
        if k in visti:
            continue
        visti.add(k)
        stato_link = check_url(url)
        if stato_link != "ok":
            # link non verificato o falso: non entra mai in lista ne' in archivio
            falsi += 1
            continue
        cat, motivo = classifica(c)
        if cat in CATEGORIE_ESCLUSE:
            scartate[cat] = scartate.get(cat, 0) + 1
            continue
        c.update({"url": url, "categoria": cat, "motivo": motivo, "priorita": priorita(cat), "link_stato": "verificato"})
        if P.opportunita_esistente(d, url):
            duplicati += 1
            continue
        accettate.append(c)
    return accettate, scartate, duplicati, falsi


def salva(d, accettate, scartate, duplicati, falsi):
    P.crea_progetto(d, PROGETTO, PROGETTO_TITOLO, nota="Radar acquisizione clienti: proprietari e strutture da proporre per la gestione")
    salvate = []
    for c in accettate:
        o = P.aggiungi_opportunita(d, PROGETTO, c["zona"], c["url"], titolo=c.get("nome", ""),
                                   info_mancanti=["prezzo", "recapito del proprietario", "stato reale della struttura"])
        if not o:
            continue
        o.update({"categoria": c["categoria"], "priorita": c["priorita"], "motivo": c["motivo"],
                  "localita": c.get("localita", ""), "osservato": c.get("testo_letto", ""),
                  "link_stato": c["link_stato"], "prossima_azione": "verificare la pagina e decidere se inviare la lettera",
                  "lettera": lettera_per(o)})
        salvate.append(o)
    d["ricerche"].append({"data": P.ora(), "progetto": PROGETTO, "modalita": "gestione_clienti",
                          "zona": "lido+como", "link_trovati": [o["fonte"] for o in salvate],
                          "nuove_opportunita": [o["id"] for o in salvate],
                          "scartate_per_categoria": scartate, "duplicati": duplicati, "link_falsi": falsi,
                          "testo": ""})
    P.salva(d)
    return salvate


def messaggio(salvate, scartate, duplicati, falsi):
    if not salvate:
        base = "Nessuna opportunita' di gestione verificabile questa settimana."
    else:
        righe = ["Opportunita' di gestione da valutare: %d" % len(salvate), ""]
        for i, o in enumerate(sorted(salvate, key=lambda x: {"alta": 0, "media": 1, "bassa": 2}[x["priorita"]]), 1):
            proposta = ("Proposta: gestione dell'affitto (prenotazioni, ospiti, pulizie) se fatica ad affittare."
                        if o["categoria"] in ("casa_sfitta_o_poco_affittata", "annuncio_poco_curato", "casa_gestita_proprietario")
                        else "Proposta: chiedere se cerca un gestore.")
            righe += [
                "%d. [%s] %s, %s" % (i, o["priorita"].upper(), o.get("titolo") or "struttura", o.get("localita") or o["zona"]),
                "Tipo: " + o["categoria"].replace("_", " "),
                "Perche': " + o["motivo"],
                "Link (" + o["link_stato"] + "): " + o["fonte"],
                proposta,
                "Lettera pronta nell'archivio (id %d)." % o["id"],
                "",
            ]
        base = "\n".join(righe).strip()
    extra = []
    if scartate:
        extra.append("Scartate per categoria: " + ", ".join("%s %d" % (k.replace("_", " "), v) for k, v in scartate.items()) + ".")
    if duplicati:
        extra.append("Gia' in archivio: %d." % duplicati)
    if falsi:
        extra.append("Link non verificati o falsi scartati: %d." % falsi)
    return "JARVIS - RADAR GESTIONE CLIENTI\n\n" + base + ("\n\n" + " ".join(extra) if extra else "")


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
    candidati = raccogli()
    accettate, scartate, duplicati, falsi = valuta(candidati, d)
    salvate = salva(d, accettate, scartate, duplicati, falsi)
    invia(messaggio(salvate, scartate, duplicati, falsi))
    log("salvate: %d | scartate per categoria: %s | duplicati: %d | link falsi: %d" % (len(salvate), scartate, duplicati, falsi))


if __name__ == "__main__":
    main()
