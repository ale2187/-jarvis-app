import os, sys, json, re, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KEY = os.environ["OPENAI_API_KEY"]
mode = sys.argv[1] if len(sys.argv) > 1 else "padel"
oggi = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y")

BASE = ("Oggi e' " + oggi + ". Cerca sul web informazioni REALI e AGGIORNATE. Non inventare nulla. "
        "Rispondi in italiano, testo semplice, SENZA markdown: niente asterischi, niente cancelletti, niente grassetto. "
        "Scrivi i link come indirizzo completo su una riga a parte. Massimo 2500 caratteri in tutto. ")

REGOLE_RISULTATI = (BASE + "Includi solo risultati con un link vero trovato nella ricerca, massimo 5 risultati. "
          "Per ogni risultato: titolo, dettagli utili, link. "
          "Se non trovi nulla di valido, scrivi solo: Nessuna novita' valida questa settimana.")

REGOLE_CASE = (BASE + "Voglio SOLO annunci singoli di immobili IN VENDITA, ognuno con il suo link diretto all'annuncio. "
          "NON elencare portali, siti generici, siti di prenotazione vacanze (tipo booking, airbnb, bnblombardia, clickcase) "
          "ne' articoli di blog. Se non trovi annunci singoli reali, scrivi solo: Nessun annuncio valido questa settimana. "
          "Massimo 5 annunci.")

REGOLE_BUSINESS = (BASE + "Non promettere guadagni e non inventare numeri di vendita. "
          "Evita idee banali e gia' sature (curriculum, planner generici, quaderni a righe, diari della gratitudine). "
          "Cerca micro-nicchie specifiche. Per ogni idea includi almeno una fonte con link vero che mostra tendenza o domanda; "
          "se non la trovi, scrivilo chiaramente. Massimo 3 idee, brevi e concrete.")

TASKS = {
 "padel": (REGOLE_RISULTATI, "RADAR PADEL",
   "Trova tornei di padel nei prossimi 10-14 giorni entro circa 60 km da Como (anche Padel Resort e circoli della zona). "
   "Preferisci FIP Bronze, vanno bene anche TPRA. Sono ammessi tutti i premi, anche non in denaro (attrezzatura, viaggi, buoni spa). "
   "Il giocatore ha livello Playtomic 3,8 su scala 0-7: includi solo tornei il cui range di livello comprende 3,8 o che sono aperti a tutti. "
   "Indica data, circolo, categoria, livello, premio e link per iscriversi."),
 "lavoro": (REGOLE_RISULTATI, "RADAR LAVORO",
   "Trova offerte di lavoro recenti (ultime 2 settimane) come barista o responsabile/gestore di bar a Como, provincia di Como, "
   "Canton Ticino e dintorni in Svizzera. Preferisci turni di mattina circa dalle 6-8 alle 15-16. Indica azienda, luogo, orario se noto e link."),
 "case": (REGOLE_CASE, "RADAR CASE",
   "Cerca su immobiliare.it, idealista.it, casa.it, subito.it, casadaprivato.it e siti di agenzie annunci di vendita recenti di "
   "appartamenti, bilocali, B&B o piccole case, con prezzo fino a 120.000 euro (qualsiasi prezzo sotto questa cifra va bene), "
   "nelle zone di Milano, Como e provincia, Lido delle Nazioni e Comacchio. "
   "Metti per primi gli immobili in buono stato o ristrutturati; includi anche quelli da ristrutturare, che valuto io. "
   "Escludi box, garage, posti auto, terreni e magazzini: voglio solo abitazioni. "
   "Per ogni annuncio scrivi: tipo di immobile, stato (ristrutturato, buono, da ristrutturare), prezzo, zona, metratura e link diretto all'annuncio."),
 "gestione": (REGOLE_RISULTATI, "RADAR GESTIONE CASE",
   "Cerco clienti per un'attivita' di property manager (gestione di case vacanza, B&B e appartamenti in affitto breve). "
   "Zone: Lido delle Nazioni, Comacchio e Lidi Ferraresi, Como e Milano. "
   "Fai due sezioni. "
   "SEZIONE A - Proprietari che CERCANO un gestore per il proprio immobile: annunci recenti (ultime 3 settimane) in cui chi scrive possiede "
   "una casa e chiede aiuto, con parole tipo cerco gestore, cerco property manager, cercasi host, cerco chi gestisca il mio appartamento. "
   "ESCLUDI SEMPRE chi OFFRE servizi di gestione (agenzie, property manager, co-host, persone che si propongono o cercano appartamenti da gestire): "
   "sono concorrenti, non clienti. Se non trovi proprietari veri, scrivi: Nessun proprietario che cerca un gestore questa settimana. "
   "SEZIONE B - Possibili clienti da contattare: annunci di affitto vacanze pubblicati direttamente da privati "
   "(per esempio su clickcase.it, bnblombardia.it, casevacanza.it, subito.it) che sembrano trascurati: poche foto, descrizione scarsa, "
   "prezzi poco chiari, pochi dettagli. Per ognuno spiega in una riga cosa si potrebbe migliorare. "
   "Includi solo annunci singoli con link diretto, massimo 3 per sezione. "
   "Per ognuno: zona, tipo di immobile, cosa si nota, contatto solo se pubblicato dal proprietario, link."),
 "business": (REGOLE_BUSINESS, "RADAR BUSINESS",
   "Proponi 3 idee di prodotti che una persona in Italia puo' creare con l'aiuto dell'IA e vendere "
   "(libri low content o da colorare su Amazon KDP, template, guide, registri su Amazon, Etsy o Gumroad). "
   "Cerca sul web tendenze recenti e nicchie con poca concorrenza sul mercato italiano. "
   "La persona gestisce un B&B a Lido delle Nazioni, lavora come barista, gioca a padel e vive vicino a Como: "
   "privilegia idee legate a queste competenze, ma proponi anche altro se vale la pena. "
   "Per ogni idea scrivi: titolo concreto del primo prodotto, a chi serve, perche' potrebbe vendere, come crearlo in modo semplice, "
   "dove venderlo, la fonte con link, e cosa scrivere nella barra di ricerca di Amazon.it per verificare la domanda. "
   "Ricorda che testi e immagini creati con IA vanno dichiarati su Amazon KDP."),
}

if mode not in TASKS:
    print("Modalita' non valida:", mode, "- usa padel, lavoro, case, business o gestione")
    sys.exit(1)

regole, titolo, compito = TASKS[mode]

def pulisci(t):
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 \2", t)
    t = re.sub(r"[?&]utm_source=openai", "", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = t.replace("**", "").replace("*", "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def post(url, data, headers):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())

def cerca():
    for model in ("gpt-4.1", "gpt-4o", "gpt-4o-mini"):
        for tool in ("web_search_preview", "web_search"):
            try:
                r = post("https://api.openai.com/v1/responses",
                         {"model": model, "tools": [{"type": tool}], "input": regole + " " + compito},
                         {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
                testo = "".join(c.get("text", "") for o in r.get("output", []) if o.get("type") == "message"
                                for c in o.get("content", []) if c.get("type") == "output_text")
                if testo.strip():
                    print("Modello usato:", model, tool)
                    return pulisci(testo)
            except Exception as e:
                print("Errore con", model, tool, e)
    return "Ricerca non riuscita questa settimana."

msg = "JARVIS - " + titolo + "\n\n" + cerca()
post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
     {"chat_id": CHAT_ID, "text": msg[:4000], "disable_web_page_preview": True},
     {"Content-Type": "application/json"})
print("Inviato.")
