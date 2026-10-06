import os, json, base64, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify

app = Flask(__name__)

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_VOICE = os.environ.get("OPENAI_VOICE", "cedar")
CHAT_MODEL = "gpt-4o-mini"
MAX_HISTORY = 12

TTS_INSTRUCTIONS = os.environ.get("TTS_INSTRUCTIONS") or (
    "Speak Italian like a native speaker in a very fast, rapid-fire, relaxed conversation, "
    "like two friends chatting. Words flowing and linked together, no pauses between words, "
    "never enunciating syllable by syllable, never robotic. Slightly bright, warm tone, "
    "spontaneous and casual, with a smirk in the voice and dry British-butler sarcasm. "
    "Deliver jokes quickly and deadpan."
)

JARVIS_SYSTEM_PROMPT = (
    "Sei J.A.R.V.I.S., l'intelligenza artificiale personale del Signor Alessandro, "
    "barista, host del B&B Ale House al Lido delle Nazioni e giocatore di padel (livello 3,8 su scala 0-7). "
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
    "Se mancano dati, chiedili: non inventare mai. Ricorda che i contratti vanno controllati da un avvocato. "
    "Se dice 'modalita' inglese', parla in inglese semplice con frasi brevi e correggi i suoi errori con una riga in italiano; "
    "torna all'italiano quando dice 'torna in italiano'. "
    "Non puoi ancora analizzare foto o link, ne' cercare sul web durante la conversazione: se te lo chiede, dillo con "
    "ironia e ricorda che gli avvisi su tornei, lavoro e case arrivano su Telegram."
)


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


def text_for_voice(text):
    if len(text) <= 300:
        return text
    cut = text[:250]
    return cut.rsplit(" ", 1)[0] + "... il resto lo trova scritto sullo schermo, Signore."


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    hist = data.get("history") or []
    now = datetime.now(ZoneInfo("Europe/Rome")).strftime("%A %d/%m/%Y, ore %H:%M")
    messages = [{"role": "system", "content": JARVIS_SYSTEM_PROMPT + " Ora attuale in Italia: " + now + "."}]
    for h in hist[-MAX_HISTORY:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": msg})
    low = msg.lower()
    long_doc = any(w in low for w in ("curriculum", "cv", "contratto"))
    try:
        r = openai_post("chat/completions", {
            "model": CHAT_MODEL, "messages": messages,
            "max_tokens": 1500 if long_doc else 350}, timeout=25)
        return jsonify({"reply": r["choices"][0]["message"]["content"].strip(), "error": None})
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


HTML = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>J.A.R.V.I.S.</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;background:#050a14;color:#e0f4ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden}
#app{display:flex;flex-direction:column;height:100%;padding:calc(env(safe-area-inset-top,0px) + 16px) 16px calc(env(safe-area-inset-bottom,0px) + 16px);gap:14px}
#status{text-align:center;font-size:12px;letter-spacing:3px;color:#00e5ff;text-transform:uppercase;min-height:16px}
#err{text-align:center;font-size:11px;color:#ff9a9a;min-height:14px;word-break:break-word}
#stage{flex:1;display:flex;align-items:center;justify-content:center}
#reactor{position:relative;width:160px;height:160px;cursor:pointer;-webkit-tap-highlight-color:transparent}
#ring{position:absolute;inset:0;border:4px solid #00e5ff;border-radius:50%;box-shadow:0 0 30px rgba(0,229,255,.8),inset 0 0 20px rgba(0,229,255,.2)}
#core{position:absolute;top:50%;left:50%;width:70px;height:70px;margin:-35px 0 0 -35px;border-radius:50%;background:radial-gradient(circle at 30% 30%,#fff,#88ddff);box-shadow:0 0 40px rgba(136,221,255,.9)}
.pulse{animation:pulse 1s infinite}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
#chat{max-height:34%;overflow-y:auto;border:1px solid rgba(0,229,255,.25);border-radius:10px;padding:10px;background:rgba(5,10,20,.7);font-size:14px;line-height:1.5}
.m{margin:6px 0}.u{text-align:right;color:#00e5ff}.a{color:#cdeeff}
#bar{display:flex;gap:8px}
#txt{flex:1;background:#101a30;border:1px solid rgba(0,229,255,.3);border-radius:8px;color:#e0f4ff;padding:10px;font-size:16px;font-family:inherit}
#send{background:#00e5ff;color:#050a14;border:none;border-radius:8px;padding:0 16px;font-weight:700;font-size:14px}
</style>
</head>
<body>
<div id="app">
  <div id="status">ONLINE</div>
  <div id="err"></div>
  <div id="stage"><div id="reactor"><div id="ring"></div><div id="core"></div></div></div>
  <div id="chat"></div>
  <div id="bar">
    <input id="txt" type="text" placeholder="Scrivi un messaggio..." autocomplete="off">
    <button id="send">Invia</button>
  </div>
</div>
<script>
var statusEl = document.getElementById("status");
var errEl = document.getElementById("err");
var ringEl = document.getElementById("ring");
var chatEl = document.getElementById("chat");
var txtEl = document.getElementById("txt");
var history = [];
var busy = false;
var listening = false;
var recognition = null;
var player = new Audio();
var unlocked = false;
var job = 0;

function setStatus(s, pulsing) {
  statusEl.textContent = s;
  if (pulsing) { ringEl.classList.add("pulse"); } else { ringEl.classList.remove("pulse"); }
}
function idle() {
  busy = false;
  listening = false;
  setStatus("ONLINE", false);
}
function addMsg(role, text) {
  var d = document.createElement("div");
  d.className = "m " + (role === "user" ? "u" : "a");
  d.textContent = text;
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
function speak(text, myJob) {
  setStatus("PREPARO LA VOCE...", true);
  post("/tts", { text: text }, 30000)
    .then(function (d) {
      if (myJob !== job) return;
      if (!d.audio_url) {
        errEl.textContent = d.error || "voce non disponibile";
        idle();
        return;
      }
      player.onended = idle;
      player.onerror = function () { errEl.textContent = "il telefono non riproduce l'audio"; idle(); };
      player.src = d.audio_url;
      setStatus("PARLA", true);
      player.play().catch(function (e) {
        errEl.textContent = "audio bloccato dal telefono, tocca il reattore e riprova";
        idle();
      });
    })
    .catch(function () {
      if (myJob !== job) return;
      errEl.textContent = "la voce ha impiegato troppo";
      idle();
    });
}
function sendMessage(text) {
  text = (text || "").trim();
  if (!text || busy) return;
  busy = true;
  job += 1;
  var myJob = job;
  errEl.textContent = "";
  txtEl.value = "";
  addMsg("user", text);
  setStatus("ELABORO...", true);
  post("/chat", { message: text, history: history.slice(-12) }, 40000)
    .then(function (d) {
      if (myJob !== job) return;
      addMsg("assistant", d.reply);
      if (d.error) { errEl.textContent = d.error; idle(); return; }
      history.push({ role: "user", content: text });
      history.push({ role: "assistant", content: d.reply });
      speak(d.reply, myJob);
    })
    .catch(function () {
      if (myJob !== job) return;
      errEl.textContent = "il server non risponde (si sta svegliando?), riprova tra un minuto";
      idle();
    });
}
function initRecognition() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  recognition = new SR();
  recognition.lang = "it-IT";
  recognition.interimResults = false;
  recognition.onstart = function () { listening = true; setStatus("TI ASCOLTO...", true); };
  recognition.onresult = function (e) {
    sendMessage(e.results[e.results.length - 1][0].transcript);
  };
  recognition.onerror = function () { if (!busy) idle(); };
  recognition.onend = function () { listening = false; if (!busy) idle(); };
}
document.getElementById("reactor").addEventListener("click", function () {
  unlockAudio();
  if (busy) {
    job += 1;
    player.pause();
    idle();
    return;
  }
  if (!recognition) { alert("Il microfono non e' supportato qui, usa la scrittura."); return; }
  if (listening) { recognition.stop(); return; }
  try { recognition.start(); } catch (e) { idle(); }
});
document.getElementById("send").addEventListener("click", function () { unlockAudio(); sendMessage(txtEl.value); });
txtEl.addEventListener("keydown", function (e) { if (e.key === "Enter") { unlockAudio(); sendMessage(txtEl.value); } });
initRecognition();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return HTML


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
