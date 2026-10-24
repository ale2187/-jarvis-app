import os, re, json, time, base64, random, threading, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify

app = Flask(__name__)

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_VOICE = os.environ.get("OPENAI_VOICE", "cedar")
CHAT_MODEL = "gpt-4o-mini"
MAX_HISTORY = 12
MAX_IMG = 7000000
MAX_FRAMES = 10
WEB_BUDGET = int(os.environ.get("WEB_BUDGET", "26"))
app.config["MAX_CONTENT_LENGTH"] = 9 * 1024 * 1024

TTS_INSTRUCTIONS = os.environ.get("TTS_INSTRUCTIONS") or (
    "Speak Italian like a native speaker in a very fast, rapid-fire, relaxed conversation, "
    "like two friends chatting. Words flowing and linked together, no pauses between words, "
    "never enunciating syllable by syllable, never robotic. Slightly bright, warm tone, "
    "spontaneous and casual, with a smirk in the voice and dry British-butler sarcasm. "
    "Deliver jokes quickly and deadpan. Speak with good volume and clear projection."
)

JARVIS_SYSTEM_PROMPT = (
    "Sei J.A.R.V.I.S., l'intelligenza artificiale personale del Signor Alessandro, "
    "barista, host del B&B Ale House al Lido delle Nazioni e giocatore di padel (livello 3,8 su scala 0-7). "
    "Il Signore vive a Capiago Intimiano (CO), vicino a Como; il suo B&B e' al Lido delle Nazioni. "
    "Cerca lavoro in Ticino e a Como e valuta di gestire case vacanza per conto di altri: ogni accordo di gestione "
    "va prima discusso con un commercialista. "
    "Parli sempre in italiano, con tono elegante, asciutto e servizievole, come il JARVIS dei film. "
    "Rivolgiti a lui con 'Signore' o 'Signor Alessandro'. "
    "IRONIA: sii marcatamente ironico. In quasi ogni risposta normale inserisci una battuta secca, "
    "sarcastica ma elegante, detta con finta serieta' e understatement. Punzecchia il Signore su puntualita', "
    "padel, B&B, idee improvvisate e caffe', ma resta sempre utile. La battuta va dopo la risposta utile, mai lunga. "
    "Se l'argomento e' serio (salute, soldi, contratti, ospiti del B&B, lavoro), niente battute. "
    "STILE: parla come in una conversazione tra due persone vere, frasi brevi, dirette, colloquiali, "
    "senza formule da assistente. Saluta in modo adatto all'ora quando la conversazione inizia. "
    "RISPOSTE NORMALI: massimo 2 o 3 frasi, senza elenchi, emoji o simboli, perche' vengono lette ad alta voce. "
    "ECCEZIONE: se ti chiede un curriculum (Como o Svizzera, italiano o inglese) o un contratto da property manager "
    "(gestione completa al 100% oppure a spese condivise al 30%), scrivi il documento completo, senza limite di frasi. "
    "Vale come eccezione anche per i messaggi ai proprietari e per le lettere di candidatura: scrivili completi. "
    "Se mancano dati, chiedili: non inventare mai. Ricorda che i contratti vanno controllati da un avvocato. "
    "Se dice 'modalita' inglese', parla in inglese semplice con frasi brevi e correggi i suoi errori con una riga in italiano; "
    "torna all'italiano quando dice 'torna in italiano'. "
    "FOTO: puoi analizzare foto e screenshot che il Signore invia con il pulsante della fotocamera. "
    "Descrivi cio' che vedi e dai un parere concreto in massimo 5 frasi brevi. Per un capo o un acquisto: taglio, materiali visibili, "
    "difetti, e se vedi il prezzo dici se ti pare adeguato; non puoi verificare i prezzi sul web, dillo. "
    "Per case o annunci: punti di forza, difetti, domande da fare al venditore. Per documenti o contratti: riassumi i punti importanti "
    "e segnala i rischi, ricordando che vanno controllati da un professionista. Non inventare mai cio' che non si vede. "
    "VIDEO: i video ti arrivano come fotogrammi in ordine di tempo, senza audio: dillo se serve e non inventare cio' che sta tra un fotogramma e l'altro. "
    "MESSAGGI AI PROPRIETARI: se il Signore ti manda l'annuncio di una casa (foto o testo) e chiede un messaggio per il proprietario, "
    "scrivi il messaggio completo, pronto da copiare, senza battute, in prima persona come Alessandro. Struttura: saluto (usa il nome se e' visibile), "
    "riferimento concreto all'annuncio (zona, metri quadri, posti letto), presentazione breve (Alessandro, vive al Lido delle Nazioni e gestisce il B&B Ale House: "
    "prenotazioni, ospiti, check-in, pulizie), proposta onesta e non insistente (qualche consiglio per rendere l'annuncio piu' ordinato e con piu' foto, "
    "oppure parlare della gestione per la prossima stagione, senza impegno), chiusura cortese con [numero di telefono]. "
    "Se l'annuncio chiede di non ricevere contatti pubblicitari, dillo nel messaggio e resta breve e rispettoso: se non interessa, basta un cenno e non lo disturbera' piu'. "
    "Non inventare difetti che non vedi, non promettere guadagni, non parlare di prezzi o commissioni. "
    "Ricordagli di scrivere una sola volta e solo dal modulo del sito. "
    "CANDIDATURE: se ti manda un'offerta di lavoro (testo o screenshot), scrivi una lettera di candidatura di circa 120 parole, in italiano formale, "
    "con domicilio a Capiago Intimiano (CO), esperienza da barista e gestione di un B&B. Non inventare titoli o anni di esperienza: usa [segnaposto] se mancano. "
    "WEB E LINK: non puoi aprire link. Se il Signore ha attivato il pulsante Web o chiede di cercare online, ti arriva una ricerca web; "
    "altrimenti, se chiede qualcosa di attuale, digli di toccare il pulsante Web e riformulare. "
    "Per case, tornei, lavoro, clienti e idee ci sono i radar su Telegram: lavoro lunedi' e mercoledi', lavoro sorella martedi' e sabato, "
    "gestione case giovedi', case e padel venerdi', business domenica. "
    "TELEGRAM: puo' dirti 'mandalo su Telegram' e la tua ultima risposta gli arriva su Telegram. "
    "BUSINESS: se ti chiede di creare o pensare un business, parte una procedura che gli manda il piano su Telegram dopo circa un minuto; non scriverlo tu in chat. "
    "NOTIZIE E CALCIO: se chiede le notizie o l'analisi del calcio, ti arriva una ricerca web con i dati. Il calcio e' solo analisi statistica, mai un esito sicuro. "
    "Sul calcio dei radar: Champions martedi' e mercoledi', Serie A il venerdi'; piano Instagram la domenica."
)

GIORNI = ["lunedi'", "martedi'", "mercoledi'", "giovedi'", "venerdi'", "sabato", "domenica"]
COMPITI_IG = [
    "una storia di 10 secondi con il mare o il tramonto",
    "rispondere ai commenti e ai messaggi e salutare 5 profili locali",
    "pubblicare il post della settimana",
    "una storia dietro le quinte della casa",
    "un Reel breve della casa o del giardino",
    "una storia con un consiglio locale",
    "guardare le statistiche di Instagram e mandarle a JARVIS",
]
RADAR_DEL_GIORNO = {
    0: "radar lavoro (alle 9)",
    1: "radar lavoro sorella, Milano e Svizzera (alle 9)",
    2: "radar lavoro (verso le 8:30)",
    3: "radar gestione case (verso le 8:30)",
    4: "radar case (alle 9) e radar padel (alle 9:30)",
    5: "radar lavoro sorella (alle 9)",
    6: "radar business (alle 18)",
}
WEB_WORDS = ("cerca sul web", "cerca online", "cerca su internet", "cercami", "ricerca web", "cerca in rete", "cerca in internet")
LONG_WORDS = ("curriculum", "cv", "contratto", "lettera", "candidatura", "messaggio per", "messaggio al", "scrivimi il messaggio")


def err_text(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            msg = json.loads(e.read().decode())["error"]["message"]
        except Exception:
            msg = ""
        return ("HTTP %s %s" % (e.code, msg))[:90]
    return (type(e).__name__ + " " + str(e))[:90]


def openai_post(path, payload, raw=False, timeout=25):
    req = urllib.request.Request(
        "https://api.openai.com/v1/" + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + OPENAI_KEY},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return body if raw else json.loads(body.decode())


def http_json(url, data=None, headers=None, timeout=6):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def text_for_voice(text):
    if len(text) <= 700:
        return text
    cut = text[:650]
    return cut.rsplit(" ", 1)[0] + "... il resto lo trova scritto sullo schermo, Signore."


def pulisci(t):
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 \2", t)
    t = re.sub(r"[?&]utm_source=openai", "", t)
    t = re.sub(r"^#+\s*", "", t, flags=re.M)
    t = t.replace("**", "").replace("*", "")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def meteo(lat, lon, nome):
    try:
        q = ("latitude=%s&longitude=%s&timezone=Europe%%2FRome&forecast_days=1&daily="
             "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max" % (lat, lon))
        d = http_json("https://api.open-meteo.com/v1/forecast?" + q, timeout=4)["daily"]
        return ("%s: min %.0f gradi, max %.0f gradi, pioggia %s%%, vento fino a %.0f km/h."
                % (nome, d["temperature_2m_min"][0], d["temperature_2m_max"][0],
                   d["precipitation_probability_max"][0], d["wind_speed_10m_max"][0]))
    except Exception:
        return ""


def morning_context():
    d = datetime.now(ZoneInfo("Europe/Rome"))
    parts = [meteo(45.81, 9.09, "Como"), meteo(44.68, 12.26, "Lido delle Nazioni")]
    meteo_txt = " ".join(p for p in parts if p) or "Meteo non disponibile."
    return ("BUONGIORNO: il Signore ti saluta al mattino. Rispondi con un buongiorno in massimo 5 frasi: giorno e data, "
            "meteo, cosa arriva oggi su Telegram dai radar, e una battuta secca finale. Dati reali: oggi e' "
            + GIORNI[d.weekday()] + " " + d.strftime("%d/%m/%Y") + ". Meteo: " + meteo_txt +
            " Radar di oggi: " + RADAR_DEL_GIORNO[d.weekday()] + ". Compito Instagram di oggi: " + COMPITI_IG[d.weekday()] + ". Non inventare altri dati.")


def clean_image(v):
    if isinstance(v, str) and v.startswith("data:image/") and len(v) < MAX_IMG:
        return v
    return None


def clean_images(d):
    out = []
    one = clean_image(d.get("image"))
    if one:
        out.append(one)
    many = d.get("images")
    if isinstance(many, list):
        for v in many[:MAX_FRAMES]:
            c = clean_image(v)
            if c:
                out.append(c)
    return out[:MAX_FRAMES]


def user_content(text, imgs):
    if not imgs:
        return text
    detail = "low" if len(imgs) > 1 else "auto"
    parts = [{"type": "text", "text": text}]
    for u in imgs:
        parts.append({"type": "image_url", "image_url": {"url": u, "detail": detail}})
    return parts


WEB_EXTRA = (" Hai la ricerca web attiva per questa risposta: usa i risultati per dare dati aggiornati, "
             "indica la fonte con il nome del sito, massimo 6 frasi, e dichiara se non trovi nulla di affidabile. Non inventare.")


def web_call(instr, inp, budget, max_out):
    t0 = time.time()
    last = "nessun risultato"
    for model in ("gpt-4.1", "gpt-4o-mini"):
        for tool in ("web_search_preview", "web_search"):
            left = budget - (time.time() - t0)
            if left < 6:
                raise RuntimeError("tempo scaduto " + last)
            try:
                r = openai_post("responses", {"model": model, "tools": [{"type": tool}], "instructions": instr,
                                              "input": inp, "max_output_tokens": max_out}, timeout=int(left))
                text = "".join(c.get("text", "") for o in r.get("output", []) if o.get("type") == "message"
                               for c in o.get("content", []) if c.get("type") == "output_text")
                if text.strip():
                    return pulisci(text)
            except Exception as e:
                last = err_text(e)
    raise RuntimeError(last)


def web_answer(system_text, history_msgs, user_msg, extra=None, max_out=700):
    inp = [{"role": m["role"], "content": m["content"]} for m in history_msgs]
    inp.append({"role": "user", "content": user_msg})
    return web_call(system_text + (extra or WEB_EXTRA), inp, WEB_BUDGET, max_out)


BUSINESS_WORDS = ("crea un business", "crea un'idea", "crea un idea", "idea di business", "pensa un business", "pensa a un business",
                  "nuovo business", "business sostenibile", "idea di startup", "crea una startup", "crea un'attivita", "crea un attivita")
NEWS_WORDS = ("notizie",)
CALCIO_WORDS = ("analisi calcio", "analisi della giornata", "partite di oggi", "analisi champions", "analisi serie a", "calcio di oggi")

TEMI_BUSINESS = ["prodotti digitali per host di B&B e case vacanza", "servizi locali potenziati dall'intelligenza artificiale",
                 "prodotti e servizi per chi viaggia con il cane", "contenuti e abbonamenti a basso costo",
                 "piccole nicchie su Amazon KDP o Etsy", "formazione breve e guide pratiche",
                 "servizi per piccoli locali e B&B della costa ferrarese"]

BUSINESS_PROMPT = (
    "Sei un consulente di business pratico e onesto. Crea UNA idea di business online sostenibile per Alessandro: barista, host del B&B Ale House "
    "al Lido delle Nazioni, vive a Capiago Intimiano (CO), parla italiano e poco inglese, budget iniziale basso (meno di 500 euro), "
    "nessuna partita IVA al momento (il piano deve dire quando servirebbe), circa 10 ore a settimana, usa JARVIS e strumenti di intelligenza artificiale. "
    "Sostenibile vuol dire: basso costo di partenza, ripetibile, non dipende da una sola piattaforma, margini reali, rischio contenuto, regge nel tempo. "
    "Cerca sul web tendenze e dati recenti per scegliere un'idea con domanda reale e concorrenza gestibile nel mercato italiano. "
    "Evita idee sature (planner generici, curriculum, diari, dropshipping) e non usare marchi o personaggi protetti. "
    "Spunto da seguire per questa volta: {tema}. Richiesta dell'utente: {richiesta}. "
    "Scrivi in testo semplice, senza markdown e senza asterischi. La prima riga deve essere: RIASSUNTO: una frase con l'idea. "
    "Poi, con questi titoli: IDEA; PER CHI E PERCHE' PAGHEREBBERO; COSA VENDI E A CHE PREZZO INDICATIVO (scrivi da verificare se non hai una fonte); "
    "COSTI DI PARTENZA; I PRIMI 7 GIORNI (una riga per giorno); COME VERIFICARE LA DOMANDA IN 2 MINUTI; RISCHI E LIMITI ONESTI; "
    "QUANDO SERVIREBBE LA PARTITA IVA E COSA CHIEDERE AL COMMERCIALISTA; COME PUO' AIUTARTI JARVIS; FONTI (solo il nome dei siti). "
    "Non promettere guadagni, non inventare numeri e non scrivere link. Massimo 3300 caratteri in tutto."
)

NEWS_PROMPT = (
    "Dammi 5 notizie brevi e utili per Alessandro, di oggi o degli ultimi giorni: 2 su affitti brevi e regole (CIN, tasse, Airbnb, Booking), "
    "2 su lavoro in Ticino e frontalieri (permessi, accordi fiscali Italia-Svizzera) o offerte, 1 su mutui, tassi e prezzi delle case a Como e Milano. "
    "Per ogni notizia: una frase e il nome del sito fonte. Se non trovi notizie recenti su un tema, dillo."
)
NEWS_EXTRA = " Hai la ricerca web attiva: usa solo notizie reali e recenti, non inventare, niente link, niente elenchi con simboli."

CALCIO_PROMPT = (
    "Analisi statistica delle partite di oggi e di domani di Serie A e di Champions League. Per le 3 o 4 partite piu' rilevanti: squadre, orario, "
    "classifica, forma nelle ultime 5 partite, gol fatti e subiti, assenze note e una frase su chi e' favorito secondo i dati e quanto la partita e' incerta. "
    "Se non ci sono partite, dillo. Chiudi con: sono statistiche informative, non consigli, nessun esito e' sicuro."
)
CALCIO_EXTRA = (" Hai la ricerca web attiva: usa solo dati che trovi e cita il sito fonte, non inventare statistiche, non dire mai che un esito e' sicuro "
                "o quasi sicuro, niente consigli di puntata ne' importi, niente link, massimo 1200 caratteri.")


def telegram_ready():
    return bool(os.environ.get("TELEGRAM_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def telegram_send(text):
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False, "Telegram non collegato: su Render mancano TELEGRAM_TOKEN e TELEGRAM_CHAT_ID"
    try:
        http_json("https://api.telegram.org/bot" + token + "/sendMessage",
                  data=json.dumps({"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True}).encode(),
                  headers={"Content-Type": "application/json"}, timeout=15)
        return True, None
    except Exception as e:
        return False, "TELEGRAM " + err_text(e)


def detect_task(low):
    if any(w in low for w in BUSINESS_WORDS):
        return "business"
    if any(w in low for w in CALCIO_WORDS):
        return "calcio"
    if any(w in low for w in NEWS_WORDS) and len(low) < 80:
        return "notizie"
    return None


def business_job(richiesta):
    try:
        prompt = BUSINESS_PROMPT.format(tema=random.choice(TEMI_BUSINESS), richiesta=richiesta or "nessuna richiesta particolare")
        text = web_call("Rispondi sempre in italiano. Hai la ricerca web attiva.",
                        [{"role": "user", "content": prompt}], 110, 1500)
        piano = re.sub(r"^\s*RIASSUNTO:", "In breve:", text.strip(), count=1)
        ok, err = telegram_send("PIANO BUSINESS DI JARVIS\n\n" + piano)
        print("business inviato:", ok, err)
    except Exception as e:
        telegram_send("Non sono riuscito a preparare il piano business: " + err_text(e) + ". Riprova tra poco.")


def run_task(task, msg, system, plain):
    if task == "business":
        if not telegram_ready():
            return {"reply": "Per mandarti il piano devo prima essere collegato a Telegram: su Render mancano TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.",
                    "error": None}
        threading.Thread(target=business_job, args=(msg,), daemon=True).start()
        return {"reply": "Ci lavoro, Signore. Tra un minuto ti arriva il piano su Telegram.", "error": None}
    try:
        if task == "notizie":
            return {"reply": web_answer(system, [], NEWS_PROMPT, extra=NEWS_EXTRA, max_out=800), "error": None}
        return {"reply": web_answer(system, [], CALCIO_PROMPT, extra=CALCIO_EXTRA, max_out=800), "error": None}
    except Exception as e:
        return {"reply": "Non sono riuscito a cercare ora, Signore. Riprovi tra poco.", "error": "WEB " + err_text(e)}


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    imgs = clean_images(data)
    hist = data.get("history") or []
    if imgs and not msg:
        msg = "Analizza questa immagine e dimmi cosa ne pensi."
    d = datetime.now(ZoneInfo("Europe/Rome"))
    system = (JARVIS_SYSTEM_PROMPT + " Ora attuale in Italia: " + GIORNI[d.weekday()] + " "
              + d.strftime("%d/%m/%Y, ore %H:%M") + ".")
    low = msg.lower()
    morning = (not imgs) and len(low) < 70 and any(w in low for w in ("buongiorno", "buon giorno", "sveglia", "buondi"))
    if morning:
        system += " " + morning_context()
    recent = hist[-MAX_HISTORY:]
    last_media = -1
    for i, h in enumerate(recent):
        if h.get("role") == "user" and clean_images(h):
            last_media = i
    messages = [{"role": "system", "content": system}]
    plain = []
    media_used = bool(imgs)
    for i, h in enumerate(recent):
        role, content = h.get("role"), h.get("content")
        if role in ("user", "assistant") and content:
            himgs = clean_images(h) if (role == "user" and i == last_media and not imgs) else []
            if himgs:
                media_used = True
            messages.append({"role": role, "content": user_content(content, himgs) if role == "user" else content})
            plain.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_content(msg, imgs)})
    if not imgs:
        task = detect_task(low)
        if task:
            return jsonify(run_task(task, msg, system, plain))
    use_web = (not imgs) and (bool(data.get("web")) or any(w in low for w in WEB_WORDS))
    web_note = ""
    if use_web:
        try:
            return jsonify({"reply": web_answer(system, plain, msg), "error": None})
        except Exception as e:
            web_note = "WEB " + err_text(e)
            messages[0]["content"] += " La ricerca web non e' riuscita: rispondi con quello che sai e dillo chiaramente."
    long_doc = any(w in low for w in LONG_WORDS)
    try:
        r = openai_post("chat/completions", {
            "model": CHAT_MODEL, "messages": messages,
            "max_tokens": 1500 if long_doc else (500 if media_used else 350)},
            timeout=50 if media_used else (20 if morning else 25))
        return jsonify({"reply": r["choices"][0]["message"]["content"].strip(), "error": web_note or None})
    except Exception as e:
        return jsonify({"reply": "Mi scusi, Signore, non riesco a ragionare in questo momento.",
                        "error": "CHAT " + err_text(e)})


@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {}
    t = text_for_voice((data.get("text") or "").strip())
    if not t:
        return jsonify({"audio_url": None, "error": "testo vuoto"})
    last = ""
    for payload in (
        {"model": "gpt-4o-mini-tts", "voice": OPENAI_VOICE, "input": t,
         "instructions": TTS_INSTRUCTIONS, "response_format": "mp3"},
        {"model": "tts-1", "voice": "onyx", "input": t, "response_format": "mp3"},
    ):
        try:
            raw = openai_post("audio/speech", payload, raw=True, timeout=25)
            return jsonify({"audio_url": "data:audio/mpeg;base64," + base64.b64encode(raw).decode(),
                            "error": None})
        except Exception as e:
            last = "VOCE " + err_text(e)
    return jsonify({"audio_url": None, "error": last})


@app.route("/telegram", methods=["POST"])
def telegram():
    text = ((request.get_json(silent=True) or {}).get("text") or "").strip()[:3500]
    if not text:
        return jsonify({"ok": False, "error": "testo vuoto"})
    ok, err = telegram_send("JARVIS\n\n" + text)
    return jsonify({"ok": ok, "error": err})


HTML = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>J.A.R.V.I.S.</title>
<style>*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;background:#02040a;color:#e0f4ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden}
body{background:radial-gradient(circle at 50% 42%,#0a1c33 0%,#050b16 50%,#010206 100%)}
#app{position:relative;display:flex;flex-direction:column;height:100%;padding:calc(env(safe-area-inset-top,0px) + 10px) 12px calc(env(safe-area-inset-bottom,0px) + 10px);gap:8px}
#app::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.05;background-image:linear-gradient(#00e5ff 1px,transparent 1px),linear-gradient(90deg,#00e5ff 1px,transparent 1px);background-size:38px 38px}
#top{position:relative;text-align:center;z-index:2}
#title{font-size:13px;font-weight:300;letter-spacing:9px;color:#bfefff;text-shadow:0 0 14px rgba(0,229,255,.7);padding-left:9px}
#status{margin-top:3px;font-size:10px;letter-spacing:4px;color:#19e3ff;text-transform:uppercase;min-height:13px}
#err{margin-top:2px;font-size:11px;color:#ff9a9a;min-height:12px;word-break:break-word}
#stage{position:relative;flex:1;min-height:0;display:flex;align-items:center;justify-content:center}
#reactor{--c:#19e3ff;--o:#ff8a2a;--k:1;--b:3.2s;--s:min(98vw,54vh);position:relative;width:var(--s);height:var(--s);cursor:pointer;color:var(--c);transition:color .5s;-webkit-tap-highlight-color:transparent}
#reactor.listen{--c:#3dffb5;--k:.55;--b:1s}
#reactor.think{--c:#ffc247;--o:#ff5a36;--k:.2;--b:.6s}
#reactor.speak{--c:#aeeaff;--k:.5;--b:.55s}
.ring{position:absolute;inset:0;animation:spin calc(var(--t) * var(--k)) linear infinite}
.ring.rev{animation-direction:reverse}
.ring svg{width:100%;height:100%;display:block;overflow:visible}
.r1{--t:140s}.r2{--t:46s}.r3{--t:80s}.r4{--t:30s;filter:drop-shadow(0 0 4px currentColor)}.r5{--t:55s}.r6{--t:16s;filter:drop-shadow(0 0 5px var(--o))}.r7{--t:90s}.r8{--t:7s}
@keyframes spin{to{transform:rotate(360deg)}}
.cc{stroke:currentColor;fill:none}
.oc{stroke:var(--o);fill:none}
.of{fill:var(--o)}
.tx{font:3.1px ui-monospace,Menlo,monospace;fill:currentColor;opacity:.6;letter-spacing:.6px}
#core{position:absolute;top:50%;left:50%;width:15%;height:15%;margin:-7.5% 0 0 -7.5%;border-radius:50%;background:radial-gradient(circle,#fff 0%,#fff 8%,currentColor 24%,rgba(2,14,30,.92) 62%,rgba(2,14,30,0) 74%);box-shadow:0 0 30px 6px currentColor;animation:beat var(--b) ease-in-out infinite}
#core::before{content:"";position:absolute;inset:-26%;border-radius:50%;border:1.5px solid currentColor;opacity:.8}
#core::after{content:"";position:absolute;inset:-58%;border-radius:50%;border:1px dashed var(--o);opacity:.7}
@keyframes beat{0%,100%{transform:scale(1);opacity:.95}50%{transform:scale(1.12);opacity:1}}
.wave{position:absolute;inset:20%;border:1.5px solid currentColor;border-radius:50%;opacity:0}
#reactor.listen .wave,#reactor.speak .wave{animation:ripple 2.4s ease-out infinite}
#reactor .w2{animation-delay:.8s!important}
#reactor .w3{animation-delay:1.6s!important}
@keyframes ripple{0%{transform:scale(.85);opacity:.7}100%{transform:scale(1.5);opacity:0}}
.fl{position:absolute;width:9px;height:9px;margin:-4.5px;border-radius:50%;background:#fff;box-shadow:0 0 10px 4px currentColor,0 0 26px 9px currentColor;animation:tw 4s ease-in-out infinite}
.fl.o{color:var(--o);box-shadow:0 0 10px 4px var(--o),0 0 26px 9px var(--o)}
#sparks{position:absolute;inset:0;pointer-events:none}
.sp{position:absolute;border-radius:50%;background:currentColor;box-shadow:0 0 6px currentColor;animation:tw 3s ease-in-out infinite}
.sp.so{background:var(--o);box-shadow:0 0 6px var(--o)}
@keyframes tw{0%,100%{opacity:.12}50%{opacity:1}}
.dat{position:absolute;font:8px/1.6 ui-monospace,Menlo,monospace;color:var(--o);opacity:.7;letter-spacing:.5px;pointer-events:none;animation:tw 5s ease-in-out infinite}
.dl{left:-1%;top:32%}.dr{right:-1%;bottom:28%;text-align:right}
#grab{position:relative;height:16px;margin-bottom:-6px;display:flex;align-items:center;justify-content:center;cursor:pointer;z-index:2}
#grab span{display:block;width:44px;height:4px;border-radius:2px;background:rgba(0,229,255,.5)}
#chat{position:relative;height:15vh;min-height:76px;overflow-y:auto;border:1px solid rgba(0,229,255,.25);border-radius:12px;padding:8px 10px;background:rgba(4,12,26,.72);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);font-size:13px;line-height:1.45}
#chat.big{height:55vh}
.m{margin:5px 0}.u{text-align:right;color:#7fefff}.a{color:#d6f1ff}
.m img{display:block;max-width:80px;max-height:80px;border-radius:8px;margin:0 0 4px auto;border:1px solid rgba(0,229,255,.4)}
#chip{position:relative;display:none;align-items:center;gap:10px;padding:5px 10px;border:1px solid rgba(0,229,255,.35);border-radius:10px;background:rgba(6,16,32,.8);font-size:12px;color:#9fe8ff}
#chip.on{display:flex}
#chip img{width:32px;height:32px;object-fit:cover;border-radius:6px}
#chip button{margin-left:auto;background:none;border:none;color:#ff9a9a;font-size:20px;padding:0 6px}
#bar{position:relative;display:flex;gap:6px;align-items:stretch}
#photo,#web{width:38px;height:38px;flex:0 0 38px;background:#0b1830;color:#19e3ff;border:1px solid rgba(0,229,255,.4);border-radius:10px;display:flex;align-items:center;justify-content:center}
#photo svg,#web svg{width:18px;height:18px}
#web.on{color:#ffc247;border-color:#ffc247;box-shadow:0 0 10px rgba(255,194,71,.5)}
#txt{flex:1;min-width:0;height:38px;background:#0b1830;border:1px solid rgba(0,229,255,.35);border-radius:10px;color:#e0f4ff;padding:0 10px;font-size:16px;font-family:inherit}
#send{height:38px;background:linear-gradient(135deg,#19e3ff,#35a8ff);color:#04101f;border:none;border-radius:10px;padding:0 14px;font-weight:700;font-size:13px}
#file{display:none}
.tg{display:inline-block;margin-top:3px;background:none;border:1px solid rgba(0,229,255,.35);color:#7fefff;border-radius:8px;font-size:10px;padding:2px 7px}
.badge{display:block;text-align:right;font-size:10px;color:#9fe8ff;margin-bottom:2px}
</style>
</head>
<body>
<div id="app">
  <div id="top"><div id="title">J.A.R.V.I.S.</div><div id="status">ONLINE</div><div id="err"></div></div>
  <div id="stage">
    <div id="reactor">
      <div class="wave w1"></div><div class="wave w2"></div><div class="wave w3"></div>
      <div class="ring r1" id="r1"></div>
      <div class="ring r2 rev" id="r2"></div>
      <div class="ring r3" id="r3"></div>
      <div class="ring r4" id="r4"></div>
      <div class="ring r5 rev" id="r5"></div>
      <div class="ring r6" id="r6"></div>
      <div class="ring r7 rev" id="r7"></div>
      <div class="ring r8" id="r8"></div>
      <div id="core"></div>
      <div class="fl" style="left:21%;top:33%"></div>
      <div class="fl" style="left:50%;top:86%"></div>
      <div class="fl o" style="left:78%;top:27%"></div>
      <div class="dat dl">SYS 99.2<br>NAV 44.68N<br>MEM 0xA7F3<br>LINK OK</div>
      <div class="dat dr">PWR 98.6<br>12.26E<br>RADAR 07<br>CORE 1962</div>
      <div id="sparks"></div>
    </div>
  </div>
  <div id="grab"><span></span></div>
  <div id="chat"></div>
  <div id="chip"><img id="chipimg" alt=""><span id="chiptxt">Pronto: scrivi o parla, poi invia</span><button id="chipx" type="button">&times;</button></div>
  <div id="bar">
    <button id="photo" type="button" aria-label="Foto o video"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="3.5"/></svg></button>
    <button id="web" type="button" aria-label="Ricerca web"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/></svg></button>
    <input id="file" type="file" accept="image/*,video/*">
    <input id="txt" type="text" placeholder="Scrivi un messaggio..." autocomplete="off">
    <button id="send" type="button">Invia</button>
  </div>
</div>
<script>
(function () {
"use strict";
var MAXF = 10;
var statusEl = document.getElementById("status");
var errEl = document.getElementById("err");
var reactorEl = document.getElementById("reactor");
var chatEl = document.getElementById("chat");
var txtEl = document.getElementById("txt");
var fileEl = document.getElementById("file");
var chipEl = document.getElementById("chip");
var chipImg = document.getElementById("chipimg");
var chipTxt = document.getElementById("chiptxt");
var webBtn = document.getElementById("web");
var convo = [];
var busy = false;
var listening = false;
var wantListen = false;
var recognition = null;
var heard = "";
var base = "";
var silenceTimer = null;
var player = new Audio();
var unlocked = false;
var job = 0;
var pending = null;
var webOn = false;
var TG_RE = /(mand|invi)\w*[^.]{0,30}telegram|telegram[^.]{0,30}(mand|invi)/i;

function tk(r1, r2, a, cls, w, op) {
  var c = Math.cos(a), s = Math.sin(a);
  return '<line class="' + cls + '" x1="' + (r1 * c).toFixed(2) + '" y1="' + (r1 * s).toFixed(2) + '" x2="' + (r2 * c).toFixed(2) + '" y2="' + (r2 * s).toFixed(2) + '" stroke-width="' + w + '" opacity="' + op + '"/>';
}
function sv(inner) { return '<svg viewBox="-100 -100 200 200">' + inner + '</svg>'; }
function buildRings() {
  var i, a, t, big, org;
  t = '<circle class="cc" r="98.5" stroke-width="0.3" opacity="0.5"/>';
  for (i = 0; i < 120; i++) {
    a = i * 3 * Math.PI / 180;
    big = (i % 10 === 0);
    org = (i >= 36 && i <= 52);
    t += tk(98, big ? 92 : (org ? 93.5 : 95.5), a, org ? "oc" : "cc", (big || org) ? 0.9 : 0.4, big ? 0.9 : 0.65);
  }
  document.getElementById("r1").innerHTML = sv(t);
  t = '<circle class="oc" r="89" stroke-width="1.6" stroke-dasharray="90 14 30 10 60 14 20 10 31.5" opacity="0.9"/>' +
      '<circle class="oc" r="86" stroke-width="0.3" opacity="0.5"/>';
  [200, 215, 330, 20, 70, 250].forEach(function (d) {
    t += '<rect class="of" x="86.5" y="-0.8" width="5" height="1.6" transform="rotate(' + d + ')"/>';
  });
  document.getElementById("r2").innerHTML = sv(t);
  var str = "01101001 SYS 0xA7F3 NAV 44.68N 12.26E PWR 98.6 LINK OK 1962.2 // 0110 JARVIS ONLINE ";
  document.getElementById("r3").innerHTML = sv('<defs><path id="tp" d="M -83 0 A 83 83 0 1 1 83 0 A 83 83 0 1 1 -83 0"/></defs>' +
      '<text class="tx"><textPath href="#tp">' + str + str + str + '</textPath></text>');
  document.getElementById("r4").innerHTML = sv('<circle class="cc" r="74" stroke-width="5" stroke-dasharray="68 12 38 12 90 12.5" opacity="0.95"/>' +
      '<circle class="cc" r="69" stroke-width="0.5" opacity="0.6"/>');
  t = '<circle class="cc" r="64" stroke-width="0.4" opacity="0.7"/>';
  for (i = 0; i < 90; i++) {
    a = i * 4 * Math.PI / 180;
    t += (i % 6 === 0) ? tk(64, 59.5, a, "cc", 0.6, 0.9) : tk(64, 62.2, a, "cc", 0.35, 0.6);
  }
  document.getElementById("r5").innerHTML = sv(t);
  document.getElementById("r6").innerHTML = sv('<defs><linearGradient id="og" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#ff8a2a" stop-opacity="0"/><stop offset="1" stop-color="#ffb347"/></linearGradient></defs>' +
      '<path d="M 29 -50.2 A 58 58 0 0 1 37.3 44.4" fill="none" stroke="url(#og)" stroke-width="3.2" stroke-linecap="round"/>');
  t = '<circle class="cc" r="46" stroke-width="0.8" opacity="0.9"/><circle class="cc" r="40" stroke-width="0.3" stroke-dasharray="2 3" opacity="0.6"/>';
  for (i = 0; i < 4; i++) { t += tk(46, 30, i * Math.PI / 2, "cc", 0.7, 0.8); }
  for (i = 0; i < 48; i++) { t += tk(46, 44, i * 7.5 * Math.PI / 180, "cc", 0.3, 0.7); }
  document.getElementById("r7").innerHTML = sv(t);
  document.getElementById("r8").innerHTML = sv('<line class="oc" x1="0" y1="0" x2="40" y2="0" stroke-width="0.9"/>' +
      '<circle class="of" cx="40" cy="0" r="1.6"/><circle class="oc" r="3" stroke-width="0.6"/>');
  var sp = document.getElementById("sparks");
  for (i = 0; i < 22; i++) {
    var d = document.createElement("span");
    var ang = Math.random() * 6.283;
    var rad = 0.25 + Math.random() * 0.75;
    var sz = (1 + Math.random() * 2.4).toFixed(1) + "px";
    d.className = "sp" + (Math.random() < 0.45 ? " so" : "");
    d.style.left = (50 + Math.cos(ang) * rad * 50).toFixed(1) + "%";
    d.style.top = (50 + Math.sin(ang) * rad * 50).toFixed(1) + "%";
    d.style.width = sz;
    d.style.height = sz;
    d.style.animationDelay = (Math.random() * 4).toFixed(2) + "s";
    sp.appendChild(d);
  }
}
function setStatus(s, state) {
  statusEl.textContent = s;
  reactorEl.className = state || "";
}
function idle() {
  busy = false;
  listening = false;
  setStatus("ONLINE", "");
}
function setWeb(on) {
  webOn = on;
  if (on) { webBtn.classList.add("on"); } else { webBtn.classList.remove("on"); }
}
function lastAssistant() {
  var i;
  for (i = convo.length - 1; i >= 0; i--) { if (convo[i].role === "assistant") return convo[i].content; }
  return "";
}
function addMsg(role, text, img, badge, noBtn) {
  var d = document.createElement("div");
  d.className = "m " + (role === "user" ? "u" : "a");
  if (img) {
    var im = document.createElement("img");
    im.src = img;
    d.appendChild(im);
  }
  if (badge) {
    var b = document.createElement("span");
    b.className = "badge";
    b.textContent = badge;
    d.appendChild(b);
  }
  var s = document.createElement("span");
  s.textContent = text;
  d.appendChild(s);
  if (role !== "user" && !noBtn) {
    var br = document.createElement("div");
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tg";
    btn.textContent = "Invia su Telegram";
    btn.addEventListener("click", function () { sendToTelegram(text); });
    br.appendChild(btn);
    d.appendChild(br);
  }
  chatEl.appendChild(d);
  chatEl.scrollTop = chatEl.scrollHeight;
}
function unlockAudio() {
  if (unlocked) return;
  unlocked = true;
  player.src = "data:audio/wav;base64,UklGRiYAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQIAAAAAAA==";
  player.play().catch(function () {});
}
function post(url, body, ms) {
  var ctrl = new AbortController();
  var timer = setTimeout(function () { ctrl.abort(); }, ms);
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: ctrl.signal
  }).then(function (r) { clearTimeout(timer); return r.json(); })
    .catch(function (e) { clearTimeout(timer); throw e; });
}
function splitSpeech(text) {
  var t = text.replace(/https?:\/\/\S+/g, "").replace(/\s+/g, " ").trim();
  var sentences = t.match(/[^.!?]+[.!?]*/g) || [t];
  var chunks = [];
  var cur = "";
  sentences.forEach(function (s) {
    s = s.trim();
    if (!s) return;
    if (cur && (cur + " " + s).length > 420) { chunks.push(cur); cur = s; }
    else { cur = cur ? cur + " " + s : s; }
  });
  if (cur) chunks.push(cur);
  var MAXC = 4;
  if (chunks.length > MAXC) {
    chunks = chunks.slice(0, MAXC);
    chunks[MAXC - 1] += " Il resto lo trova scritto sullo schermo, Signore.";
  }
  return chunks;
}
function speak(text, myJob) {
  var chunks = splitSpeech(text);
  if (!chunks.length) { idle(); return; }
  setStatus("PREPARO LA VOCE...", "think");
  function fetchChunk(k) {
    return post("/tts", { text: chunks[k] }, 30000).then(function (d) {
      if (!d.audio_url) { throw new Error(d.error || "voce non disponibile"); }
      return d.audio_url;
    });
  }
  function playIndex(k, p) {
    p.then(function (url) {
      if (myJob !== job) return;
      var pre = (k + 1 < chunks.length) ? fetchChunk(k + 1) : null;
      if (pre) pre.catch(function () {});
      player.onended = function () {
        if (myJob !== job) return;
        if (pre) { playIndex(k + 1, pre); } else { idle(); }
      };
      player.onerror = function () { errEl.textContent = "il telefono non riproduce l'audio"; idle(); };
      player.src = url;
      setStatus("PARLA", "speak");
      player.play().catch(function () {
        errEl.textContent = "audio bloccato dal telefono, tocca il reattore e riprova";
        idle();
      });
    }).catch(function (e) {
      if (myJob !== job) return;
      errEl.textContent = String((e && e.message) || "la voce ha impiegato troppo");
      idle();
    });
  }
  playIndex(0, fetchChunk(0));
}
function historyForServer() {
  var lastMedia = -1;
  var i;
  for (i = 0; i < convo.length; i++) { if (convo[i].images) lastMedia = i; }
  var out = [];
  var from = Math.max(0, convo.length - 12);
  for (i = from; i < convo.length; i++) {
    var e = { role: convo[i].role, content: convo[i].content };
    if (i === lastMedia) e.images = convo[i].images;
    out.push(e);
  }
  return out;
}
function clearPending() {
  pending = null;
  chipEl.classList.remove("on");
  chipImg.removeAttribute("src");
  fileEl.value = "";
}
function sendToTelegram(text) {
  if (!text) { errEl.textContent = "non c'e' niente da inviare"; return; }
  errEl.textContent = "";
  post("/telegram", { text: text }, 20000).then(function (d) {
    if (d.ok) { addMsg("assistant", "Inviato su Telegram, Signore.", null, null, true); }
    else { errEl.textContent = d.error || "invio non riuscito"; }
  }).catch(function () { errEl.textContent = "invio non riuscito"; });
}
function sendMessage(text) {
  text = (text || "").trim();
  if (busy) return;
  if (text && TG_RE.test(text) && !pending) {
    txtEl.value = "";
    addMsg("user", text, null, null, true);
    sendToTelegram(lastAssistant());
    idle();
    return;
  }
  var media = pending;
  if (!text && !media) return;
  busy = true;
  job += 1;
  var myJob = job;
  errEl.textContent = "";
  txtEl.value = "";
  var isVideo = !!(media && media.video);
  var shown = text || (isVideo ? "Analizza questo video." : (media ? "Analizza questa immagine." : ""));
  var sent = text;
  if (isVideo) {
    sent = (text || "Analizza questo video e dimmi cosa ne pensi.") +
      " [Sono " + media.imgs.length + " fotogrammi in ordine, estratti da un video di circa " + Math.round(media.dur) + " secondi, senza audio]";
  }
  addMsg("user", shown, media ? media.imgs[0] : null, isVideo ? ("video, " + media.imgs.length + " fotogrammi") : null, true);
  clearPending();
  var useWeb = webOn && !media;
  setStatus(useWeb ? "CERCO SUL WEB..." : "ELABORO...", "think");
  var body = { message: sent, history: historyForServer(), web: useWeb };
  if (media) body.images = media.imgs;
  setWeb(false);
  post("/chat", body, media ? 65000 : (useWeb ? 50000 : 40000))
    .then(function (d) {
      if (myJob !== job) return;
      addMsg("assistant", d.reply);
      if (d.error) { errEl.textContent = d.error; }
      var u = { role: "user", content: sent };
      if (media) u.images = media.imgs;
      convo.push(u);
      convo.push({ role: "assistant", content: d.reply });
      if (d.error && d.error.indexOf("CHAT") === 0) { idle(); return; }
      speak(d.reply, myJob);
    })
    .catch(function () {
      if (myJob !== job) return;
      errEl.textContent = "il server non risponde (si sta svegliando?), riprova tra un minuto";
      idle();
    });
}
function readImage(file, cb) {
  var reader = new FileReader();
  reader.onload = function () {
    var img = new Image();
    img.onload = function () {
      var s = Math.min(1, 1280 / Math.max(img.width, img.height));
      var c = document.createElement("canvas");
      c.width = Math.max(1, Math.round(img.width * s));
      c.height = Math.max(1, Math.round(img.height * s));
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      cb(c.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = function () { cb(null); };
    img.src = reader.result;
  };
  reader.onerror = function () { cb(null); };
  reader.readAsDataURL(file);
}
function extractFrames(file, cb) {
  var url = URL.createObjectURL(file);
  var v = document.createElement("video");
  v.muted = true;
  v.playsInline = true;
  v.preload = "auto";
  v.setAttribute("playsinline", "");
  v.style.cssText = "position:fixed;left:-9999px;top:0;width:2px;height:2px;";
  document.body.appendChild(v);
  var frames = [];
  var done = false;
  var guard = null;
  function finish(res) {
    if (done) return;
    done = true;
    clearTimeout(guard);
    try { URL.revokeObjectURL(url); } catch (e) {}
    if (v.parentNode) v.parentNode.removeChild(v);
    cb(res);
  }
  guard = setTimeout(function () {
    finish(frames.length ? { imgs: frames, dur: v.duration || 0 } : null);
  }, 45000);
  v.onerror = function () { finish(null); };
  v.onloadedmetadata = function () {
    var dur = v.duration;
    if (!isFinite(dur) || dur <= 0) { finish(null); return; }
    var n = Math.min(MAXF, Math.max(4, Math.ceil(dur / 3)));
    var times = [];
    var i;
    for (i = 0; i < n; i++) { times.push(dur * (i + 0.5) / n); }
    var k = 0;
    var c = document.createElement("canvas");
    function grab() {
      if (k >= times.length) { finish({ imgs: frames, dur: dur }); return; }
      v.currentTime = times[k];
    }
    v.onseeked = function () {
      var sc = Math.min(1, 640 / Math.max(v.videoWidth || 640, v.videoHeight || 640));
      c.width = Math.max(1, Math.round((v.videoWidth || 640) * sc));
      c.height = Math.max(1, Math.round((v.videoHeight || 360) * sc));
      c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
      frames.push(c.toDataURL("image/jpeg", 0.7));
      k += 1;
      grab();
    };
    grab();
  };
  v.src = url;
}
function resetSilence() {
  clearTimeout(silenceTimer);
  if (heard.trim()) { silenceTimer = setTimeout(finishListening, 3500); }
}
function finishListening() {
  clearTimeout(silenceTimer);
  wantListen = false;
  try { recognition.stop(); } catch (e) {}
  var t = heard;
  heard = "";
  base = "";
  if (t.trim()) { sendMessage(t); } else { idle(); }
}
function initRecognition() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  recognition = new SR();
  recognition.lang = "it-IT";
  recognition.interimResults = true;
  recognition.continuous = true;
  recognition.onstart = function () { listening = true; setStatus("TI ASCOLTO... TOCCA PER INVIARE", "listen"); };
  recognition.onresult = function (e) {
    var fin = "";
    var interim = "";
    var i;
    for (i = 0; i < e.results.length; i++) {
      if (e.results[i].isFinal) { fin += e.results[i][0].transcript + " "; }
      else { interim += e.results[i][0].transcript; }
    }
    heard = (base + " " + fin + interim).replace(/\s+/g, " ").trim();
    txtEl.value = heard;
    resetSilence();
  };
  recognition.onerror = function (ev) {
    if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
      wantListen = false;
      errEl.textContent = "microfono non consentito";
    }
  };
  recognition.onend = function () {
    listening = false;
    if (wantListen && !busy) {
      base = heard;
      setTimeout(function () {
        if (wantListen && !busy) { try { recognition.start(); } catch (e) {} }
      }, 200);
    } else if (!busy) {
      idle();
    }
  };
}
reactorEl.addEventListener("click", function () {
  unlockAudio();
  if (busy) {
    job += 1;
    player.pause();
    idle();
    return;
  }
  if (!recognition) { alert("Il microfono non e' supportato qui, usa la scrittura."); return; }
  if (wantListen) { finishListening(); return; }
  heard = "";
  base = "";
  wantListen = true;
  try { recognition.start(); } catch (e) { wantListen = false; idle(); }
});
document.getElementById("send").addEventListener("click", function () { unlockAudio(); sendMessage(txtEl.value); });
txtEl.addEventListener("keydown", function (e) { if (e.key === "Enter") { unlockAudio(); sendMessage(txtEl.value); } });
document.getElementById("photo").addEventListener("click", function () { fileEl.click(); });
webBtn.addEventListener("click", function () { setWeb(!webOn); });
document.getElementById("chipx").addEventListener("click", clearPending);
document.getElementById("grab").addEventListener("click", function () {
  if (chatEl.classList.contains("big")) { chatEl.classList.remove("big"); } else { chatEl.classList.add("big"); }
  chatEl.scrollTop = chatEl.scrollHeight;
});
fileEl.addEventListener("change", function () {
  var f = fileEl.files && fileEl.files[0];
  if (!f) return;
  errEl.textContent = "";
  if (f.type && f.type.indexOf("video/") === 0) {
    chipTxt.textContent = "Leggo il video...";
    chipEl.classList.add("on");
    extractFrames(f, function (res) {
      if (!res || !res.imgs.length) {
        chipEl.classList.remove("on");
        errEl.textContent = "non riesco a leggere questo video, prova con uno piu' corto";
        return;
      }
      pending = { imgs: res.imgs, video: true, dur: res.dur };
      chipImg.src = res.imgs[0];
      chipTxt.textContent = "Video pronto: " + res.imgs.length + " fotogrammi, scrivi o parla e invia";
    });
    return;
  }
  readImage(f, function (data) {
    if (!data) { errEl.textContent = "non riesco a leggere questa foto"; return; }
    pending = { imgs: [data], video: false, dur: 0 };
    chipImg.src = data;
    chipTxt.textContent = "Foto pronta: scrivi o parla e invia";
    chipEl.classList.add("on");
  });
});
buildRings();
initRecognition();
})();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return HTML


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
