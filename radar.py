import os, sys, json, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KEY = os.environ["OPENAI_API_KEY"]
mode = sys.argv[1] if len(sys.argv) > 1 else "padel"
oggi = datetime.now(ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y")

REGOLE = ("Oggi e' " + oggi + ". Cerca sul web informazioni REALI e AGGIORNATE. Non inventare nulla: "
          "includi solo risultati con un link vero trovato nella ricerca. Rispondi in italiano, testo semplice, "
          "senza markdown, senza asterischi, massimo 5 risultati. Per ogni risultato: titolo, dettagli utili, link. "
          "Se non trovi nulla di valido, scrivi solo: Nessuna novita' valida questa settimana.")

TASKS = {
 "padel": ("RADAR PADEL",
   "Trova tornei di padel nei prossimi 10-14 giorni entro circa 60 km da Como (anche Padel Resort e circoli della zona). "
   "Preferisci FIP Bronze, vanno bene anche TPRA. Sono ammessi tutti i premi, anche non in denaro (attrezzatura, viaggi, buoni spa). "
   "Il giocatore ha livello Playtomic 3,8 su scala 0-7: includi solo tornei il cui range di livello comprende 3,8 o che sono aperti a tutti. "
   "Indica data, circolo, categoria, livello, premio e link per iscriversi."),
 "lavoro": ("RADAR LAVORO",
   "Trova offerte di lavoro recenti (ultime 2 settimane) come barista o responsabile/gestore di bar a Como, provincia di Como, "
   "Canton Ticino e dintorni in Svizzera. Preferisci turni di mattina circa dalle 6-8 alle 15-16. Indica azienda, luogo, orario se noto e link."),
 "case": ("RADAR CASE",
   "Trova annunci recenti di B&B o piccole case/appartamenti adatti ad attivita' di affitti brevi, gia' pronti da abitare, "
   "tra 60.000 e 70.000 euro oppure tra 100.000 e 110.000 euro, nelle zone di Como, Milano e Lido delle Nazioni (Comacchio). "
   "Indica prezzo, zona, metratura e link all'annuncio."),
}
titolo, compito = TASKS[mode]

def post(url, data, headers):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

def cerca():
    for tool in ("web_search_preview", "web_search"):
        try:
            r = post("https://api.openai.com/v1/responses",
                     {"model": "gpt-4o-mini", "tools": [{"type": tool}], "input": REGOLE + " " + compito},
                     {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
            testo = "".join(c.get("text", "") for o in r.get("output", []) if o.get("type") == "message"
                            for c in o.get("content", []) if c.get("type") == "output_text")
            if testo.strip():
                return testo.strip()
        except Exception as e:
            print("Errore con", tool, e)
    return "Ricerca non riuscita questa settimana."

msg = "JARVIS - " + titolo + "\n\n" + cerca()
post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
     {"chat_id": CHAT_ID, "text": msg[:4000], "disable_web_page_preview": True},
     {"Content-Type": "application/json"})
print("Inviato.")
