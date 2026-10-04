import os, json, re, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ICAL_URL = os.environ.get("AIRBNB_ICAL_URL", "")
FORCE = os.environ.get("FORCE", "") == "1"

now = datetime.now(ZoneInfo("Europe/Rome"))
if now.hour != 7 and not FORCE:
    print("Non sono le 7 a Roma, esco.")
    sys.exit(0)

def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def meteo():
    try:
        q = urllib.parse.urlencode({
            "latitude": 44.68, "longitude": 12.26, "timezone": "Europe/Rome", "forecast_days": 1,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max"})
        d = http_json("https://api.open-meteo.com/v1/forecast?" + q)["daily"]
        return (f"Lido delle Nazioni oggi: min {d['temperature_2m_min'][0]:.0f} gradi, "
                f"max {d['temperature_2m_max'][0]:.0f} gradi, pioggia {d['precipitation_probability_max'][0]}%, "
                f"vento fino a {d['wind_speed_10m_max'][0]:.0f} km/h.")
    except Exception:
        return "Meteo non disponibile."

def ical_events():
    if not ICAL_URL:
        return "Calendario Airbnb non collegato."
    try:
        raw = urllib.request.urlopen(ICAL_URL, timeout=30).read().decode("utf-8", "ignore")
        raw = re.sub(r"\r?\n[ \t]", "", raw)
        oggi, domani = now.date(), now.date() + timedelta(days=1)
        out = []
        for ev in raw.split("BEGIN:VEVENT")[1:]:
            def val(k):
                m = re.search(rf"^{k}[^:\n]*:(.*)$", ev, re.M)
                return m.group(1).strip() if m else ""
            s, e = val("DTSTART")[:8], val("DTEND")[:8]
            if not (s and e):
                continue
            ds = datetime.strptime(s, "%Y%m%d").date()
            de = datetime.strptime(e, "%Y%m%d").date()
            nome = val("SUMMARY") or "Prenotazione"
            if ds == oggi: out.append(f"CHECK-IN oggi ({nome})")
            if de == oggi: out.append(f"CHECK-OUT oggi ({nome})")
            if ds == domani: out.append(f"check-in domani ({nome})")
            if de == domani: out.append(f"check-out domani ({nome})")
        return "; ".join(out) if out else "Nessun check-in o check-out oggi o domani."
    except Exception:
        return "Calendario Airbnb non raggiungibile."

giorni = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
fatti = (f"Data: {giorni[now.weekday()]} {now.day}/{now.month}/{now.year}. "
         f"Meteo: {meteo()} B&B Ale House: {ical_events()}")

def jarvis_testo():
    prompt = ("Sei J.A.R.V.I.S., maggiordomo AI britannico, ironico e asciutto, del Signor Alessandro "
              "(barista, host del B&B Ale House, giocatore di padel). Scrivi il buongiorno su Telegram: "
              "massimo 5 righe, in italiano, parti con il saluto 'Buongiorno, Signore', riassumi i fatti dati, "
              "chiudi con UNA battuta secca. Niente emoji, niente elenchi puntati, non inventare nulla.")
    body = json.dumps({"model": "gpt-4o-mini", "messages": [
        {"role": "system", "content": prompt}, {"role": "user", "content": fatti}]}).encode()
    r = http_json("https://api.openai.com/v1/chat/completions", body,
                  {"Content-Type": "application/json", "Authorization": "Bearer " + OPENAI_KEY})
    return r["choices"][0]["message"]["content"].strip()

try:
    testo = jarvis_testo() if OPENAI_KEY else "Buongiorno, Signore.\n" + fatti
except Exception:
    testo = "Buongiorno, Signore.\n" + fatti

http_json(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
          json.dumps({"chat_id": CHAT_ID, "text": testo}).encode(),
          {"Content-Type": "application/json"})
print("Inviato.")
