import os, json, base64, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request, jsonify

app = Flask(__name__)

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_VOICE = os.environ.get("OPENAI_VOICE", "cedar")
CHAT_MODEL = "gpt-4o-mini"
MAX_HISTORY = 12
MAX_IMG = 7000000
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
    "FOTO: puoi analizzare foto e screenshot che il Signore invia con il pulsante della fotocamera. "
    "Descrivi cio' che vedi e dai un parere concreto in massimo 5 frasi brevi. Per un capo o un acquisto: taglio, materiali visibili, "
    "difetti, e se vedi il prezzo dici se ti pare adeguato; non puoi verificare i prezzi sul web, dillo. "
    "Per case o annunci: punti di forza, difetti, domande da fare al venditore. Per documenti o contratti: riassumi i punti importanti "
    "e segnala i rischi, ricordando che vanno controllati da un professionista. Non inventare mai cio' che non si vede. "
    "LINK E WEB: non puoi aprire link ne' cercare sul web durante la conversazione. Se il Signore ti chiede di cercare case, tornei, "
    "lavoro o clienti, rispondi con ironia che ci pensa il radar e manda tutto su Telegram: case e padel il venerdi', "
    "lavoro il mercoledi', gestione case il giovedi', idee di business la domenica."

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


def clean_image(v):
    if isinstance(v, str) and v.startswith("data:image/") and len(v) < MAX_IMG:
        return v
    return None


def user_content(text, image):
    if not image:
        return text
    return [{"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image, "detail": "auto"}}]


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    image = clean_image(data.get("image"))
    hist = data.get("history") or []
    if image and not msg:
        msg = "Analizza questa immagine e dimmi cosa ne pensi."
    now = datetime.now(ZoneInfo("Europe/Rome")).strftime("%A %d/%m/%Y, ore %H:%M")
    messages = [{"role": "system", "content": JARVIS_SYSTEM_PROMPT + " Ora attuale in Italia: " + now + "."}]
    img_used = bool(image)
    recent = hist[-MAX_HISTORY:]
    last_img_idx = -1
    for i, h in enumerate(recent):
        if h.get("role") == "user" and clean_image(h.get("image")):
            last_img_idx = i
    for i, h in enumerate(recent):
        if h.get("role") in ("user", "assistant") and h.get("content"):
            himg = clean_image(h.get("image")) if (i == last_img_idx and not image) else None
            if himg:
                img_used = True
            messages.append({"role": h["role"],
                             "content": user_content(h["content"], himg) if h["role"] == "user" else h["content"]})
    messages.append({"role": "user", "content": user_content(msg, image)})
    low = msg.lower()
    long_doc = any(w in low for w in ("curriculum", "cv", "contratto"))
    try:
        r = openai_post("chat/completions", {
            "model": CHAT_MODEL, "messages": messages,
            "max_tokens": 1500 if long_doc else (500 if img_used else 350)},
            timeout=50 if img_used else 25)
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
html,body{height:100%;background:#040913;color:#e0f4ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden}
body{background:radial-gradient(circle at 50% 36%,#0c2745 0%,#071428 45%,#030710 100%)}
#app{position:relative;display:flex;flex-direction:column;height:100%;padding:calc(env(safe-area-inset-top,0px) + 14px) 14px calc(env(safe-area-inset-bottom,0px) + 14px);gap:10px}
#app::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.07;background-image:linear-gradient(#00e5ff 1px,transparent 1px),linear-gradient(90deg,#00e5ff 1px,transparent 1px);background-size:38px 38px}
#top{position:relative;text-align:center}
#title{font-size:15px;font-weight:300;letter-spacing:9px;color:#bfefff;text-shadow:0 0 14px rgba(0,229,255,.7);padding-left:9px}
#status{margin-top:5px;font-size:11px;letter-spacing:4px;color:#00e5ff;text-transform:uppercase;min-height:14px}
#err{margin-top:3px;font-size:11px;color:#ff9a9a;min-height:13px;word-break:break-word}
#stage{position:relative;flex:1;min-height:0;display:flex;align-items:center;justify-content:center}
#reactor{--s:min(66vw,38vh,310px);--k:1;--b:3s;position:relative;width:var(--s);height:var(--s);cursor:pointer;color:#00e5ff;transition:color .5s;-webkit-tap-highlight-color:transparent}
#reactor.listen{color:#35ffc2;--k:.5;--b:1s}
#reactor.think{color:#ffc247;--k:.18;--b:.6s}
#reactor.speak{color:#9fe8ff;--k:.45;--b:.55s}
.ring{position:absolute;inset:0;animation:spin calc(var(--t) * var(--k)) linear infinite;filter:drop-shadow(0 0 5px currentColor)}
.ring svg{width:100%;height:100%;display:block;overflow:visible}
.r1{--t:70s}.r2{--t:26s;animation-direction:reverse}.r3{--t:14s}
@keyframes spin{to{transform:rotate(360deg)}}
#core{position:absolute;top:50%;left:50%;width:21%;height:21%;margin:-10.5% 0 0 -10.5%;border-radius:50%;background:radial-gradient(circle at 35% 32%,#fff 0%,currentColor 70%);box-shadow:0 0 28px currentColor,0 0 80px currentColor;animation:beat var(--b) ease-in-out infinite}
@keyframes beat{0%,100%{transform:scale(1);opacity:.95}50%{transform:scale(1.14);opacity:1}}
.wave{position:absolute;inset:14%;border:2px solid currentColor;border-radius:50%;opacity:0}
#reactor.listen .wave,#reactor.speak .wave{animation:ripple 2.4s ease-out infinite}
#reactor .w2{animation-delay:.8s!important}
#reactor .w3{animation-delay:1.6s!important}
@keyframes ripple{0%{transform:scale(.85);opacity:.75}100%{transform:scale(1.6);opacity:0}}
#chat{position:relative;max-height:30%;overflow-y:auto;border:1px solid rgba(0,229,255,.28);border-radius:12px;padding:10px;background:rgba(6,16,32,.68);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);font-size:14px;line-height:1.5}
.m{margin:6px 0}.u{text-align:right;color:#7fefff}.a{color:#d6f1ff}
.m img{display:block;max-width:110px;max-height:110px;border-radius:8px;margin:0 0 4px auto;border:1px solid rgba(0,229,255,.4)}
#chip{position:relative;display:none;align-items:center;gap:10px;padding:6px 10px;border:1px solid rgba(0,229,255,.35);border-radius:10px;background:rgba(6,16,32,.8);font-size:12px;color:#9fe8ff}
#chip.on{display:flex}
#chip img{width:38px;height:38px;object-fit:cover;border-radius:6px}
#chip button{margin-left:auto;background:none;border:none;color:#ff9a9a;font-size:20px;padding:0 6px}
#bar{position:relative;display:flex;gap:8px;align-items:stretch}
#photo{width:46px;background:#0d1b33;color:#00e5ff;border:1px solid rgba(0,229,255,.4);border-radius:10px;display:flex;align-items:center;justify-content:center}
#txt{flex:1;min-width:0;background:#0d1b33;border:1px solid rgba(0,229,255,.35);border-radius:10px;color:#e0f4ff;padding:11px;font-size:16px;font-family:inherit}
#send{background:linear-gradient(135deg,#00e5ff,#35a8ff);color:#04101f;border:none;border-radius:10px;padding:0 18px;font-weight:700;font-size:14px}
#file{display:none}
</style>
</head>
<body>
<div id="app">
  <div id="top"><div id="title">J.A.R.V.I.S.</div><div id="status">ONLINE</div><div id="err"></div></div>
  <div id="stage">
    <div id="reactor">
      <div class="wave w1"></div><div class="wave w2"></div><div class="wave w3"></div>
      <div class="ring r1" id="r1"></div>
      <div class="ring r2" id="r2"></div>
      <div class="ring r3" id="r3"></div>
      <div id="core"></div>
    </div>
  </div>
  <div id="chat"></div>
  <div id="chip"><img id="chipimg" alt=""><span>Foto pronta: scrivi o parla, poi invia</span><button id="chipx" type="button">&times;</button></div>
  <div id="bar">
    <button id="photo" type="button" aria-label="Foto"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L17 6h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="3.5"/></svg></button>
    <input id="file" type="file" accept="image/*">
    <input id="txt" type="text" placeholder="Scrivi un messaggio..." autocomplete="off">
    <button id="send" type="button">Invia</button>
  </div>
</div>
<script>
(function () {
"use strict";
var statusEl = document.getElementById("status");
var errEl = document.getElementById("err");
var reactorEl = document.getElementById("reactor");
var chatEl = document.getElementById("chat");
var txtEl = document.getElementById("txt");
var fileEl = document.getElementById("file");
var chipEl = document.getElementById("chip");
var chipImg = document.getElementById("chipimg");
var convo = [];
var busy = false;
var listening = false;
var recognition = null;
var player = new Audio();
var unlocked = false;
var job = 0;
var pendingImage = null;

function buildRings() {
  var t = "";
  var i, a, long, r2, x1, y1, x2, y2;
  for (i = 0; i < 72; i++) {
    a = i * 5 * Math.PI / 180;
    long = (i % 6 === 0);
    r2 = long ? 41.5 : 44.5;
    x1 = (47 * Math.cos(a)).toFixed(2); y1 = (47 * Math.sin(a)).toFixed(2);
    x2 = (r2 * Math.cos(a)).toFixed(2); y2 = (r2 * Math.sin(a)).toFixed(2);
    t += '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="currentColor" stroke-width="' + (long ? 0.9 : 0.5) + '" opacity="' + (long ? 0.95 : 0.55) + '"/>';
  }
  document.getElementById("r1").innerHTML = '<svg viewBox="-50 -50 100 100">' + t + '</svg>';
  document.getElementById("r2").innerHTML = '<svg viewBox="-50 -50 100 100">' +
    '<circle r="39" fill="none" stroke="currentColor" stroke-width="2.2" stroke-dasharray="52 14 10 14 24 14" opacity="0.9"/>' +
    '<circle r="35.5" fill="none" stroke="currentColor" stroke-width="0.4" opacity="0.5"/></svg>';
  document.getElementById("r3").innerHTML = '<svg viewBox="-50 -50 100 100">' +
    '<circle r="29" fill="none" stroke="currentColor" stroke-width="4.5" stroke-dasharray="52 12.4" opacity="0.9"/>' +
    '<circle r="22" fill="none" stroke="currentColor" stroke-width="0.6" opacity="0.6"/></svg>';
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
function addMsg(role, text, img) {
  var d = document.createElement("div");
  d.className = "m " + (role === "user" ? "u" : "a");
  if (img) {
    var im = document.createElement("img");
    im.src = img;
    d.appendChild(im);
  }
  var s = document.createElement("span");
  s.textContent = text;
  d.appendChild(s);
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
  setStatus("PREPARO LA VOCE...", "think");
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
      setStatus("PARLA", "speak");
      player.play().catch(function () {
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
function historyForServer() {
  var lastImg = -1;
  var i;
  for (i = 0; i < convo.length; i++) { if (convo[i].image) lastImg = i; }
  var out = [];
  var from = Math.max(0, convo.length - 12);
  for (i = from; i < convo.length; i++) {
    var e = { role: convo[i].role, content: convo[i].content };
    if (i === lastImg) e.image = convo[i].image;
    out.push(e);
  }
  return out;
}
function clearPhoto() {
  pendingImage = null;
  chipEl.classList.remove("on");
  chipImg.removeAttribute("src");
  fileEl.value = "";
}
function sendMessage(text) {
  text = (text || "").trim();
  var image = pendingImage;
  if ((!text && !image) || busy) return;
  busy = true;
  job += 1;
  var myJob = job;
  errEl.textContent = "";
  txtEl.value = "";
  var shown = text || "Analizza questa immagine.";
  addMsg("user", shown, image);
  clearPhoto();
  setStatus("ELABORO...", "think");
  var body = { message: text, history: historyForServer() };
  if (image) body.image = image;
  post("/chat", body, image ? 65000 : 40000)
    .then(function (d) {
      if (myJob !== job) return;
      addMsg("assistant", d.reply);
      if (d.error) { errEl.textContent = d.error; idle(); return; }
      var u = { role: "user", content: shown };
      if (image) u.image = image;
      convo.push(u);
      convo.push({ role: "assistant", content: d.reply });
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
      var maxSide = 1280;
      var s = Math.min(1, maxSide / Math.max(img.width, img.height));
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
function initRecognition() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  recognition = new SR();
  recognition.lang = "it-IT";
  recognition.interimResults = false;
  recognition.onstart = function () { listening = true; setStatus("TI ASCOLTO...", "listen"); };
  recognition.onresult = function (e) {
    sendMessage(e.results[e.results.length - 1][0].transcript);
  };
  recognition.onerror = function () { if (!busy) idle(); };
  recognition.onend = function () { listening = false; if (!busy) idle(); };
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
  if (listening) { recognition.stop(); return; }
  try { recognition.start(); } catch (e) { idle(); }
});
document.getElementById("send").addEventListener("click", function () { unlockAudio(); sendMessage(txtEl.value); });
txtEl.addEventListener("keydown", function (e) { if (e.key === "Enter") { unlockAudio(); sendMessage(txtEl.value); } });
document.getElementById("photo").addEventListener("click", function () { fileEl.click(); });
document.getElementById("chipx").addEventListener("click", clearPhoto);
fileEl.addEventListener("change", function () {
  var f = fileEl.files && fileEl.files[0];
  if (!f) return;
  errEl.textContent = "";
  readImage(f, function (data) {
    if (!data) { errEl.textContent = "non riesco a leggere questa foto"; return; }
    pendingImage = data;
    chipImg.src = data;
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
