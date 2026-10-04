import os, sys, json, urllib.request
from datetime import datetime
from zoneinfo import ZoneTime

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
KEY = os.environ["OPENAI_API_KEY"]
mode = sys.argv[1] if len(sys.argv) > 1 else "padel"
oggi = datetime.now(ZoneTime("Europe/Rome")).strftime("%d/%m/%Y")

REGOLE = ("Oggi e' " + oggi + ". Cerca sul web informazioni REALI e AGGIORNATE. Non inventare nulla: "
          "includi solo risultati con un link vero trovato nella ricerca. Rispondi in italiano, testo semplice, "
          "senza markdown, senza asterischi, massimo 5 risultati. Per ogni risultato: titolo, dettagli utili, link. "
          "Se non trovi nulla di valido, scrivi solo: Nessuna novita' valida questa settimana.")

TASKS = {
 "padel": ("RADAR PADEL",
   "Trova tornei di padel nei prossimi 10-14 giorni entro circa 60 km da Como. "
   "Preferisci FIP Bronze, vanno bene anche TPRA. Livello 3,8 su scala 0-7. "
   "Indica data, circolo, livello, premio e link."),
 "lavoro": ("RADAR LAVORO",
   "Trova offerte di lavoro come barista o responsabile bar a Como e provincia, turni mattina 6-15. "
   "Indica azienda, luogo, link."),
 "case": ("RADAR CASE",
   "Trova annunci B&B o case affitti brevi, 60-70k euro oppure 100-110k, Como/Milano/Lido delle Nazioni. "
   "Indica prezzo, zona, metratura, link."),
}
titolo, compito = TASKS[mode]

def post(url, data, headers):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

try:
    r = post("https://api.openai.com/v1/chat/completions",
             {"model": "gpt-4o-mini", "messages": [
              {"role": "user", "content": REGOLE + " " + compito}]},
             {"Content-Type": "application/json", "Authorization": "Bearer " + KEY})
    testo = r["choices"][0]["message"]["content"].strip()
except:
    testo = "Ricerca non riuscita."

msg = titolo + "\n\n" + testo
post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
     {"chat_id": CHAT_ID, "text": msg[:4000]},
     {"Content-Type": "application/json"})
print("OK")
