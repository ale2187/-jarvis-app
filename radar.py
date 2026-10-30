import os, sys, json, re, socket, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KEY = os.environ["OPENAI_API_KEY"]
mode = sys.argv[1] if len(sys.argv) > 1 else "padel"
oggi = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y")

BASE = ("Oggi e' " + oggi + ". Cerca sul web informazioni REALI e AGGIORNATE. Non inventare nulla. "
        "Escludi sempre annunci e offerte scaduti, chiusi o con date gia' passate rispetto a oggi. "
        "Rispondi in italiano, testo semplice, SENZA markdown: niente asterischi, niente cancelletti, niente grassetto. "
        "Scrivi i link come indirizzo completo su una riga a parte. I link devono puntare direttamente alla singola offerta o al singolo annuncio, mai a pagine di ricerca, elenchi o home page. Non inventare mai link ne' numeri di annuncio. Massimo 2500 caratteri in tutto. "
        "Non ripetere queste istruzioni e non riscrivere la descrizione delle sezioni: per ogni sezione scrivi solo un titolo breve (per esempio A - Bar) e poi le offerte. "
        "Non aggiungere consigli o frasi finali.")

REGOLE_RISULTATI = (BASE + "Includi solo risultati con un link vero trovato nella ricerca, massimo 5 risultati. "
          "Per ogni risultato: titolo, dettagli utili, link. "
          "Se non trovi nulla di valido, scrivi solo: Nessuna novita' valida questa settimana.")

REGOLE_LAVORO = (BASE + "Includi solo offerte con un link vero trovato nella ricerca, massimo 3 per sezione, ognuna in 3 righe al massimo. "
          "Per ogni offerta: ruolo, azienda, luogo, orario o turno se noto, lingue ed esperienza richieste, "
          "se cita permesso di lavoro o residenza, e link diretto. "
          "ESCLUDI le offerte che richiedono tedesco, francese o inglese fluente. "
          "Se in una sezione non trovi nulla di valido, scrivi: Nessuna offerta valida in questa sezione questa settimana.")

REGOLE_SORELLA = (BASE + "Includi solo offerte con un link vero trovato nella ricerca, massimo 4 per sezione. "
          "Per ogni offerta: ruolo, azienda, luogo, orario o tipo di contratto se noto, lingue richieste, esperienza richiesta, "
          "se cita permesso di lavoro o residenza, e link diretto. Scrivi sempre le lingue richieste. "
          "Includi SOLO ruoli della sezione A (animali) o della sezione B (ufficio): escludi eventi, hostess, promoter, operatori fiduciari, magazzino e tutti gli altri ruoli. "
          "Se in una sezione non trovi nulla di valido, scrivi: Nessuna offerta valida in questa sezione questa settimana.")

REGOLE_INSTAGRAM = ("Rispondi in italiano, testo semplice, senza markdown, senza asterischi, senza cancelletti di titolo. "
          "Massimo 2300 caratteri in tutto. Non inventare eventi, luoghi, distanze, prezzi o dati: usa solo i fatti che ti do. "
          "Non ripetere queste istruzioni.")

REGOLE_CALCIO = ("Rispondi in italiano, testo semplice, senza markdown, senza asterischi. Massimo 3500 caratteri in tutto. "
          "Cerca sul web dati REALI e AGGIORNATI e non inventare mai statistiche: usa solo numeri che trovi e scrivi il nome del sito fonte. "
          "Non scrivere mai che un esito e' sicuro o quasi sicuro. Non dare consigli di puntata ne' importi. Non ripetere queste istruzioni.")

REGOLE_GESTIONE = REGOLE_RISULTATI.replace("Massimo 2500 caratteri in tutto", "Massimo 3600 caratteri in tutto").replace("massimo 5 risultati", "massimo 4 risultati")

REGOLE_CLIENTI = (BASE.replace("Massimo 2500 caratteri in tutto", "Massimo 3600 caratteri in tutto") +
          "Includi solo strutture con un link vero alla loro pagina o al loro annuncio, massimo 4. "
          "Per ognuna: nome, localita', link, perche' potrebbe essere un cliente (basato solo su cio' che leggi: per esempio non cita gli animali, li vieta o li accetta senza servizi; scrivi da verificare), "
          "contatto pubblico solo se e' scritto nella loro pagina, e un MESSAGGIO PRONTO di 3 o 4 righe. "
          "Se non trovi strutture adatte scrivi solo: Nessuna struttura adatta questa settimana.")

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
 "lavoro": (REGOLE_LAVORO, "RADAR LAVORO",
   "Cerco lavoro in Canton Ticino (Svizzera italiana) e dintorni di Como. Parlo italiano e poco inglese. "
   "Fai due sezioni. "
   "SEZIONE A - Bar: offerte recenti (ultime 2 settimane) come barista, addetto al bar o responsabile/gestore di bar, "
   "in Ticino (Lugano, Mendrisio, Chiasso, Locarno, Bellinzona) e a Como e provincia. Preferisco turni di mattina circa dalle 6-8 alle 15-16. "
   "SEZIONE B - Lavori senza esperienza specifica: offerte in cui si puo' iniziare anche senza esperienza nel settore, "
   "con italiano sufficiente: supermercato e negozi (per esempio Lidl Svizzera, Coop, Migros, Aldi Suisse), magazzino e logistica, "
   "ristorazione e hotel, vendita. "
   "SEZIONE C - TIM Business e vendite B2B, NON in negozio: offerte recenti come consulente commerciale, agente di commercio o promoter "
   "per TIM Business e per le Agenzie Partner TIM Business (telefonia aziendale, centralini cloud, cybersecurity), e per operatori simili "
   "(Vodafone Business, WindTre Business, Fastweb Business), in azienda, sul territorio o a eventi. "
   "Zone: Como e provincia, Lecco, Varese e Milano. "
   "Per ogni offerta scrivi: se e' lavoro dipendente o con partita IVA (agente, Enasarco), se c'e' un fisso mensile e a quanto, "
   "come funzionano le provvigioni, e se chiedono pagamenti per formazione o materiali. "
   "Cerca su jobs.ch, indeed.ch, indeed.it, job-room.ch, sui siti carriera delle aziende e su altri siti di annunci."),
 "sorella_it": (REGOLE_SORELLA, "RADAR LAVORO SORELLA - MILANO",
   "Cerco lavoro per una persona che parla italiano e abita nella zona di San Giuliano Milanese. "
   "Zona: Milano e provincia, con priorita' ai comuni vicini a San Giuliano Milanese (San Donato Milanese, Melegnano, Peschiera Borromeo, "
   "Opera, Locate di Triulzi, Paullo, Mediglia, Rozzano) e a Milano citta'. "
   "Fai due sezioni. "
   "SEZIONE A - Animali: offerte recenti (ultime 2 settimane) come dog sitter, toelettatore o toelettatrice, addetto a pensione o centro per cani, "
   "negozio di animali, assistente in clinica veterinaria, canile o rifugio, e altri lavori con cani e animali. "
   "SEZIONE B - Ufficio: offerte recenti (ultime 2 settimane) come receptionist, segretaria, impiegata amministrativa, impiegata back office, "
   "data entry, anche part-time o da casa. "
   "Cerca su indeed.it, infojobs.it, subito.it, jooble.org e sui siti carriera delle aziende."),
 "sorella_ch": (REGOLE_SORELLA, "RADAR LAVORO SORELLA - SVIZZERA",
   "Cerco lavoro per una persona che parla italiano. "
   "Zona: Svizzera, preferibilmente Canton Ticino e zone di lingua italiana (Lugano, Mendrisio, Chiasso, Locarno, Bellinzona). "
   "Fai due sezioni. "
   "SEZIONE A - Animali: offerte recenti (ultime 2 settimane) come dog sitter, toelettatore o toelettatrice, addetto a pensione o centro per cani, "
   "negozio di animali, assistente in clinica veterinaria, rifugio, e altri lavori con cani e animali. "
   "SEZIONE B - Ufficio: offerte recenti (ultime 2 settimane) come receptionist, segretaria, impiegata amministrativa, impiegata back office, "
   "data entry, anche part-time. "
   "Cerca su jobs.ch, indeed.ch, job-room.ch e sui siti carriera delle aziende ticinesi."),
 "instagram": (REGOLE_INSTAGRAM, "PIANO INSTAGRAM DELLA SETTIMANA",
   "Prepara il piano Instagram della prossima settimana per il profilo della casa vacanze Ale House, al Lido delle Nazioni (Comacchio, Delta del Po). "
   "Fatti veri della casa: villetta con giardino privato, portico con barbecue e tende bianche, casetta in legno in giardino, animali benvenuti, "
   "tramonti sul mare, bici e natura del Delta del Po, prenotazione su Airbnb (link in bio). La casa riapre alle prenotazioni in primavera, "
   "quindi in questo periodo l'obiettivo e' farsi conoscere e raccogliere prenotazioni anticipate. "
   "Scrivi: 3 POST (per ognuno: quale foto usare tra portico, giardino, interni, spiaggia al tramonto; didascalia di 2 o 3 righe pronta da copiare; "
   "8 hashtag locali e pertinenti), 4 idee di STORIE (una riga ciascuna), 1 idea di REEL breve (3 inquadrature) e 1 compito di interazione per la settimana "
   "(per esempio commentare e salutare 5 profili locali). Tono caldo e semplice, senza esagerare con le emoji. "
   "Valorizza l'angolo 'vacanze con il cane' e il giardino privato, che sono i punti piu' distintivi."),
 "champions": (REGOLE_CALCIO, "CALCIO - CHAMPIONS LEAGUE DI OGGI",
   "Cerca le partite di Champions League di oggi (di solito alle 18:45 e alle 21:00). "
   "Se oggi non ci sono partite di Champions League, scrivi solo: Oggi non ci sono partite di Champions League. "
   "Per ogni partita scrivi: squadre, orario, posizione in classifica nella competizione, forma nelle ultime 5 partite, gol fatti e subiti, "
   "assenze o squalifiche note, ultimi scontri diretti se disponibili. Poi una riga di lettura: quale squadra e' favorita secondo i dati e quanto la partita e' incerta. "
   "Se ci sono piu' partite, in fondo elenca le 3 con il favorito piu' netto secondo i dati, precisando che favorito non vuol dire sicuro. "
   "Chiudi con questa frase: Sono statistiche informative, non consigli: nessun esito e' sicuro."),
 "seriea": (REGOLE_CALCIO, "CALCIO - SERIE A, GIORNATA",
   "Cerca le partite della prossima giornata di Serie A (di solito da venerdi' a domenica, con eventuali anticipi e posticipi). "
   "Per le 4 partite piu' rilevanti scrivi il dettaglio: squadre, giorno e orario, posizione in classifica, forma nelle ultime 5 partite, gol fatti e subiti, "
   "assenze o squalifiche note, ultimi scontri diretti se disponibili, e una riga di lettura su chi e' favorito secondo i dati e quanto la partita e' incerta. "
   "Per le altre partite scrivi una sola riga con squadre, giorno e orario. "
   "In fondo elenca le 3 partite con il favorito piu' netto secondo i dati, precisando che favorito non vuol dire sicuro. "
   "Chiudi con questa frase: Sono statistiche informative, non consigli: nessun esito e' sicuro."),
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
   "Includi solo annunci singoli con link diretto, massimo 2 per sezione. "
   "Per ognuno scrivi: zona, tipo di immobile, cosa si nota, contatto solo se pubblicato dal proprietario, link, e poi un MESSAGGIO PRONTO da inviare, "
            "di 3 o 4 righe, scritto a nome di Alessandro (vive al Lido delle Nazioni e gestisce il B&B Ale House), che rispetti eventuali richieste dell'annuncio "
            "(per esempio no contatti pubblicitari), senza promettere guadagni e senza parlare di prezzi o commissioni. Se un annuncio non e' adatto, non scrivere il messaggio."),
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

def _case(zona):
    return ("Cerca su immobiliare.it, idealista.it, casa.it, subito.it, casadaprivato.it e siti di agenzie annunci di vendita recenti di "
            "appartamenti, bilocali, trilocali o piccole case, con prezzo fino a 120.000 euro (qualsiasi prezzo sotto questa cifra va bene), "
            "SOLO in questa zona: " + zona + ". Non includere altre zone. "
            "Metti per primi gli immobili in buono stato o ristrutturati; includi anche quelli da ristrutturare, che valuto io. "
            "Escludi box, garage, posti auto, terreni e magazzini: voglio solo abitazioni. "
            "Per ogni annuncio scrivi: tipo di immobile, stato (ristrutturato, buono, da ristrutturare), prezzo, zona, metratura e link diretto all'annuncio.")


def _gestione(zona):
    return ("Cerco clienti per un'attivita' di property manager (gestione di case vacanza, B&B e appartamenti in affitto breve). "
            "Zona, SOLO questa: " + zona + ". "
            "Fai due sezioni. "
            "SEZIONE A - Proprietari che CERCANO un gestore per il proprio immobile: annunci recenti (ultime 3 settimane) in cui chi scrive possiede "
            "una casa e chiede aiuto, con parole tipo cerco gestore, cerco property manager, cercasi host, cerco chi gestisca il mio appartamento. "
            "ESCLUDI SEMPRE chi OFFRE servizi di gestione (agenzie, property manager, co-host, persone che si propongono o cercano appartamenti da gestire): "
            "sono concorrenti, non clienti. Se non trovi proprietari veri, scrivi: Nessun proprietario che cerca un gestore questa settimana. "
            "SEZIONE B - Possibili clienti da contattare: annunci di affitto vacanze pubblicati direttamente da privati "
            "(per esempio su clickcase.it, bnblombardia.it, casadaprivato.it, casevacanza.it, subito.it) che sembrano trascurati: poche foto, descrizione disordinata o scarsa, "
            "prezzi poco chiari, pochi dettagli, oppure aggiornati da molti mesi. Per ognuno spiega in una riga cosa si potrebbe migliorare. "
            "Includi solo annunci singoli con link diretto, massimo 2 per sezione. "
            "Per ognuno scrivi: zona, tipo di immobile, cosa si nota, contatto solo se pubblicato dal proprietario, link, e poi un MESSAGGIO PRONTO da inviare, "
            "di 3 o 4 righe, scritto a nome di Alessandro (vive al Lido delle Nazioni e gestisce il B&B Ale House), che rispetti eventuali richieste dell'annuncio "
            "(per esempio no contatti pubblicitari), senza promettere guadagni e senza parlare di prezzi o commissioni. Se un annuncio non e' adatto, non scrivere il messaggio.")


def _clienti(zona):
    return ("Cerco possibili clienti per un servizio di consulenza per B&B, case vacanza e affittacamere che vogliono accogliere meglio gli ospiti con cani (pet friendly): "
            "regole della casa, testi dell'annuncio, foto, servizi per i cani, Instagram. "
            "Zona, SOLO questa: " + zona + ". "
            "Cerca strutture (B&B, case vacanza, affittacamere, piccoli hotel, agriturismi) di gestori privati o piccole realta' locali, con pagina propria o annuncio su portali: "
            "preferisci quelle che non citano gli animali, che li vietano o che li accettano senza offrire nulla di speciale. Evita grandi catene e hotel di lusso. "
            "Il MESSAGGIO PRONTO deve proporre una breve chiacchierata o una prima analisi gratuita dell'annuncio per attirare ospiti con cani, a nome di Alessandro "
            "(vive al Lido delle Nazioni, gestisce il B&B Ale House, villetta con giardino dove i cani sono benvenuti), senza promettere risultati, senza prezzi, "
            "in tono rispettoso, e con la frase finale che se non interessa basta un cenno.")


ZONA_COMO = "Como e provincia (per esempio Capiago Intimiano, Villa Guardia, Montorfano, Cantu', Erba, Cernobbio, Lurate Caccivio, Mariano Comense, Appiano Gentile)"
ZONA_LIDI = "Lidi Ferraresi e Comacchio (Lido delle Nazioni, Lido di Volano, Lido degli Estensi, Lido di Spina, Porto Garibaldi)"
TASKS.pop("case", None)
TASKS.pop("gestione", None)
TASKS["case_como"] = (REGOLE_CASE, "RADAR CASE - COMO", _case(ZONA_COMO))
TASKS["case_lido"] = (REGOLE_CASE, "RADAR CASE - LIDI FERRARESI", _case(ZONA_LIDI))
TASKS["gestione_como"] = (REGOLE_GESTIONE, "RADAR GESTIONE - COMO", _gestione(ZONA_COMO))
TASKS["gestione_lido"] = (REGOLE_GESTIONE, "RADAR GESTIONE - LIDI FERRARESI", _gestione(ZONA_LIDI))

TASKS["clienti_lido"] = (REGOLE_CLIENTI, "CLIENTI PET FRIENDLY - LIDI FERRARESI", _clienti(ZONA_LIDI))
TASKS["clienti_como"] = (REGOLE_CLIENTI, "CLIENTI PET FRIENDLY - COMO", _clienti(ZONA_COMO))

RUNS = {"property": ["case_como", "case_lido"], "sorella": ["sorella_it", "sorella_ch"], "case": ["case_como", "case_lido"], "gestione": ["gestione_como", "gestione_lido"], "clienti": ["clienti_lido", "clienti_como"]}

if mode not in TASKS and mode not in RUNS:
    print("Modalita' non valida:", mode, "- usa padel, lavoro, case, property, business, gestione, sorella, instagram, champions, seriea o clienti")
    sys.exit(1)


def pulisci(t):
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 \2", t)
    t = re.sub(r"[?&]utm_source=openai", "", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = t.replace("**", "").replace("*", "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

URL_RE = re.compile(r'https?://[^\s<>"\)\]]+')
FALSI_RE = re.compile(r'(123456|654321|987654|000000|111111|example\.)', re.I)
BOUNDARY_RE = re.compile(r'^\s*(\d+[\.\)]\s|SEZIONE\b|[A-C]\s-\s)', re.I)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


def check_url(u):
    u = u.rstrip(".,;:")
    low = u.lower()
    if FALSI_RE.search(low):
        return "falso"
    if "indeed." in low and not ("jk=" in low or "/viewjob" in low or "/rc/clk" in low or "/pagead" in low):
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


def filtra(testo):
    chunks, cur = [], []
    for r in testo.split("\n"):
        if BOUNDARY_RE.match(r) and cur:
            chunks.append("\n".join(cur))
            cur = []
        cur.append(r)
    if cur:
        chunks.append("\n".join(cur))
    out, scartati = [], 0
    for c in chunks:
        urls = URL_RE.findall(c)
        if not urls:
            out.append(c)
            continue
        stati = [check_url(u) for u in urls[:4]]
        if "falso" in stati:
            scartati += 1
            continue
        if "bloccato" in stati:
            c = c.rstrip() + "\n(link non verificabile dal radar: controllalo tu)\n"
        out.append(c)
    res = "\n".join(out).strip()
    if scartati:
        res += "\n\nScartate %d offerte con link falso o generico." % scartati
    return res


def post(url, data, headers):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())

def cerca(regole, compito):
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

for key in RUNS.get(mode, [mode]):
    regole, titolo, compito = TASKS[key]
    testo = cerca(regole, compito)
    if key not in ("business", "instagram", "champions", "seriea"):
        testo = filtra(testo)
    msg = "JARVIS - " + titolo + "\n\n" + testo
    if key.startswith("case_"):
        try:
            import progetti as _pj
            _d = _pj.carica()
            _pj.crea_progetto(_d, "property-manager", "Property Manager - Como, Lidi Ferraresi")
            _r = _pj.registra_ricerca(_d, "property-manager", "case", "Como" if key == "case_como" else "Lidi Ferraresi", testo)
            _pj.salva(_d)
            print("archivio:", _r)
        except Exception as _e:
            print("archivio non aggiornato:", _e)
    post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
         {"chat_id": CHAT_ID, "text": msg[:4000], "disable_web_page_preview": True},
         {"Content-Type": "application/json"})
    print("Inviato:", key)
