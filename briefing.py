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

def meteo_citta(nome, lat, lon):
    try:
        q = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "timezone": "Europe/Rome", "forecast_days": 1,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max"})
        d = http_json("https://api.open-meteo.com/v1/forecast?" + q)["daily"]
        return (f"{nome} oggi: minimo {d['temperature_2m_min'][0]:.0f} gradi, "
                f"massimo {d['temperature_2m_max'][0]:.0f} gradi, pioggia al {d['precipitation_probability_max'][0]}%, "
                f"vento fino a {d['wind_speed_10m_max'][0]:.0f} chilometri all'ora.")
    except Exception:
        return f"{nome}: meteo non disponibile."

def meteo():
    return meteo_citta("Como", 45.81, 9.09) + " " + meteo_citta("Lido delle Nazioni", 44.68, 12.26)

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
            if ds == oggi: out.append(f"Check-in oggi, {nome}")
            if de == oggi: out.append(f"Check-out oggi, {nome}")
            if ds == domani: out.append(f"Check-in domani, {nome}")
            if de == domani: out.append(f"Check-out domani, {nome}")
        return "; ".join(out) if out else "Nessun check-in o check-out oggi o domani."
    except Exception:
        return "Calendario Airbnb non raggiungibile."

giorni = ["lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica"]
compiti_ig = [
    "una storia di 10 secondi con il mare o il tramonto, con la domanda del giorno",
    "rispondi ai commenti e ai messaggi, e saluta 5 profili locali (10 minuti)",
    "pubblica il post della settimana con la didascalia del piano",
    "una storia dietro le quinte della casa, il giardino o il portico",
    "un Reel breve della casa o del giardino",
    "una storia con un consiglio locale, oppure ripubblica la foto di un ospite chiedendo il permesso",
    "guarda le statistiche di Instagram e mandane lo screenshot a JARVIS",
]
fatti = (f"Data: {giorni[now.weekday()]} {now.day} {now.month}. "
         f"Meteo: {meteo()} B&B Ale House: {ical_events()} "
         f"Compito Instagram di oggi: {compiti_ig[now.weekday()]}.")

def jarvis_testo():
    prompt = ("Sei J.A.R.V.I.S., maggiordomo AI britannico, ironico e asciutto, del Signor Alessandro "
              "(barista, host del B&B Ale House, giocatore di padel). Scrivi il buongiorno su Telegram: "
              "massimo 6 righe, in italiano, parti con il saluto 'Buongiorno, Signore', riassumi i fatti dati, "
              "chiudi con UNA battuta secca. Niente emoji, niente elenchi puntati, non inventare nulla.")
    body = json.dumps({"model": "gpt-4o-mini", "messages": [
        {"role": "system", "content": prompt}, {"role": "user", "content": fatti}]}).encode()
    r = http_json("https://api.openai.com/v1/chat/completions", body,
                  {"Content-Type": "application/json", "Authorization": "Bearer " + OPENAI_KEY})
    return r["choices"][0]["message"]["content"].strip()

def tts_audio(testo):
    try:
        body = json.dumps({
            "model": "gpt-4o-mini-tts",
            "voice": "cedar",
            "input": testo,
            "response_format": "opus",
            "instructions": "Speak Italian like a native speaker in a very fast, rapid-fire, relaxed conversation. "
                           "Words flowing and linked together, no pauses between words, never robotic. "
                           "Slightly bright, warm tone, spontaneous, with dry British-butler sarcasm."
        }).encode()
        req = urllib.request.Request("https://api.openai.com/v1/audio/speech",
                                    data=body,
                                    headers={"Content-Type": "application/json", 
                                            "Authorization": "Bearer " + OPENAI_KEY})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except Exception as e:
        print(f"TTS fallito: {e}")
        return None

try:
    testo = jarvis_testo() if OPENAI_KEY else "Buongiorno, Signore. " + fatti
except Exception:
    testo = "Buongiorno, Signore. " + fatti

audio_data = tts_audio(testo) if OPENAI_KEY else None

if audio_data:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"chat_id\"\r\n\r\n"
            f"{CHAT_ID}\r\n"
            f"--{boundary}\r\n"
            f"Content-Disposition: form-data; name=\"voice\"; filename=\"voice.ogg\"\r\n"
            f"Content-Type: audio/ogg\r\n\r\n").encode() + audio_data + \
           f"\r\n--{boundary}--\r\n".encode()
    
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/sendVoice",
                                data=body,
                                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
        print("Audio inviato.")
    except Exception as e:
        print(f"Vocale non inviato, ripiego a testo: {e}")
        http_json(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                  json.dumps({"chat_id": CHAT_ID, "text": testo}).encode(),
                  {"Content-Type": "application/json"})
else:
    http_json(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
              json.dumps({"chat_id": CHAT_ID, "text": testo}).encode(),
              {"Content-Type": "application/json"})
    print("Testo inviato.")
