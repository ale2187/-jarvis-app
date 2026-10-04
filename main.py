import os
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)

# Impostazioni della voce (ElevenLabs). Per una voce piu' teatrale: stability 0.35, style 0.3
VOICE_STABILITY = 0.55
VOICE_STYLE = 0.15
MAX_HISTORY = 12  # quanti messaggi precedenti ricorda JARVIS

JARVIS_SYSTEM_PROMPT = (
    "Sei J.A.R.V.I.S., l'intelligenza artificiale personale del Signor Alessandro, "
    "barista, host del B&B Ale House al Lido delle Nazioni e giocatore di padel (livello 3,8 su scala 0-7). "
    "Parli sempre in italiano, con tono elegante, asciutto e servizievole, come il JARVIS dei film: "
    "ironia britannica, sarcasmo gentile, mai volgare. "
    "Rivolgiti ad Alessandro chiamandolo 'Signore' o 'Signor Alessandro'. "
    "REGOLE DELL'IRONIA: in ogni risposta normale inserisci una battuta secca detta con finta serietà, "
    "usando l'understatement. Prendi in giro con garbo la sua puntualità, il padel, il B&B o le sue idee, "
    "ma resta sempre utile. Mai battute lunghe. "
    "Se l'argomento è serio (salute, soldi, contratti, ospiti del B&B), niente battute. "
    "Quando la conversazione inizia, saluta in modo adatto all'ora e chiedi come puoi essergli d'aiuto. "
    "RISPOSTE NORMALI: massimo 2 o 3 frasi, senza elenchi, emoji o simboli, perché vengono lette ad alta voce. "
    "DOCUMENTI: se Alessandro ti chiede un curriculum (per Como o per la Svizzera, in italiano o inglese), "
    "un contratto di property manager (gestione totale 100% o parziale 30% con spese divise) o una lettera, "
    "scrivi il testo completo e ordinato, senza il limite di frasi, e ricordagli che un contratto va "
    "fatto controllare da un professionista prima di usarlo. Prima di scrivere un CV chiedi ciò che ti manca "
    "(esperienze, lingue, date), senza inventare dati. "
    "Se non sai una cosa, ammettilo con ironia invece di inventare. "
    "MODALITA' INGLESE: se Alessandro dice 'modalita' inglese', parla in inglese semplice, a livello base, "
    "con frasi brevi, e correggi gentilmente i suoi errori spiegando in italiano in una riga. "
    "Torna all'italiano quando dice 'torna in italiano'."
)

HTML_LAYOUT = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>JARVIS</title>
    <style>
        body { background-color: #050b14; color: #00f0ff; font-family: -apple-system, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .arc-reactor { width: 160px; height: 160px; border-radius: 50%; border: 3px solid #00f0ff; box-shadow: 0 0 25px #00f0ff; display: flex; align-items: center; justify-content: center; cursor: pointer; margin-bottom: 30px; flex-shrink: 0; }
        .arc-core { width: 70px; height: 70px; border-radius: 50%; background: #ffffff; box-shadow: 0 0 20px #ffffff; }
        .status-text { font-size: 14px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 15px; }
        .response-box { max-width: 85%; max-height: 38vh; overflow-y: auto; white-space: pre-wrap; font-size: 16px; color: #e0f7fa; text-align: center; }
    </style>
</head>
<body>
    <div class="arc-reactor" onclick="startListening()"><div class="arc-core"></div></div>
    <div id="status" class="status-text">SYSTEM STANDBY</div>
    <div id="output" class="response-box">Tocca il Reattore Arc per attivare JARVIS</div>

    <script>
        const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        let recognition;
        let audioPlayer = new Audio();
        let history = [];

        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.lang = 'it-IT';
            recognition.onstart = () => { document.getElementById('status').innerText = 'ASCOLTO...'; };
            recognition.onresult = async (e) => {
                const text = e.results[0][0].transcript;
                document.getElementById('status').innerText = 'ELABORAZIONE...';
                document.getElementById('output').innerText = '"' + text + '"';
                await sendToJarvis(text);
            };
            recognition.onerror = () => { document.getElementById('status').innerText = 'ERRORE RILEVAMENTO'; };
        }

        function startListening() {
            // Sblocca l'audio su iPhone: deve partire da un tocco
            audioPlayer.src = SILENT_WAV;
            audioPlayer.play().catch(() => {});
            if (recognition) recognition.start();
        }

        async function sendToJarvis(message) {
            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message, history: history })
                });
                const data = await res.json();
                if (data.response) {
                    history.push({ role: 'user', content: message });
                    history.push({ role: 'assistant', content: data.response });
                    if (history.length > 24) { history = history.slice(-24); }
                    document.getElementById('status').innerText = 'ONLINE';
                    document.getElementById('output').innerText = data.response;
                    if (data.audio) {
                        audioPlayer.src = "data:audio/mp3;base64," + data.audio;
                        audioPlayer.play().catch(() => {});
                    }
                } else {
                    document.getElementById('status').innerText = 'ERRORE SISTEMA';
                    document.getElementById('output').innerText = data.error || '';
                }
            } catch (e) {
                document.getElementById('status').innerText = 'ERRORE CONNESSIONE';
            }
        }
    </script>
</body>
</html>"""


def text_for_voice(text):
    """Risposte lunghe (CV, contratti): la voce legge solo l'inizio, il resto resta a schermo."""
    if len(text) <= 500:
        return text
    head = text[:250]
    cut = max(head.rfind("."), head.rfind("!"), head.rfind("?"))
    if cut > 40:
        head = head[: cut + 1]
    return head + " Il testo completo e' sullo schermo, Signore."


def elevenlabs_tts(text):
    """Genera la voce con ElevenLabs. Restituisce l'audio in base64 o None se fallisce."""
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        print("ElevenLabs: ELEVENLABS_API_KEY o ELEVENLABS_VOICE_ID mancante")
        return None

    url = "https://api.elevenlabs.io/v1/text-to-speech/" + voice_id
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": VOICE_STABILITY,
            "similarity_boost": 0.75,
            "style": VOICE_STYLE,
            "use_speaker_boost": True,
        },
    }
    headers = {"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_bytes = resp.read()
        return base64.b64encode(audio_bytes).decode("utf-8")
    except urllib.error.HTTPError as err:
        print("Errore ElevenLabs", err.code, err.read().decode("utf-8", "ignore")[:300])
        return None
    except Exception as err:
        print("Errore ElevenLabs:", err)
        return None


def openai_tts(client, text):
    """Voce di riserva con OpenAI, se ElevenLabs non risponde."""
    try:
        audio_response = client.audio.speech.create(model="tts-1", voice="onyx", input=text)
        return base64.b64encode(audio_response.content).decode("utf-8")
    except Exception as err:
        print("Errore TTS OpenAI:", err)
        return None


@app.route("/", methods=["GET"])
def home():
    return render_template_string(HTML_LAYOUT)


@app.route("/chat", methods=["POST"])
def chat():
    try:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return jsonify({"error": "OPENAI_API_KEY mancante su Render"}), 500

        client = OpenAI(api_key=api_key)
        data = request.get_json() or {}
        user_message = data.get("message", "")

        if not user_message:
            return jsonify({"error": "Messaggio vuoto"}), 400

        now = datetime.now(ZoneInfo("Europe/Rome")).strftime("%H:%M del %d/%m/%Y")
        system_prompt = JARVIS_SYSTEM_PROMPT + " Ora attuale in Italia: " + now + "."

        messages = [{"role": "system", "content": system_prompt}]
        for item in (data.get("history") or [])[-MAX_HISTORY:]:
            if (
                isinstance(item, dict)
                and item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str)
            ):
                messages.append({"role": item["role"], "content": item["content"][:4000]})
        messages.append({"role": "user", "content": user_message})

        completion = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=1500,
            messages=messages,
        )
        reply_text = completion.choices[0].message.content

        speech = text_for_voice(reply_text)
        audio_base64 = elevenlabs_tts(speech) or openai_tts(client, speech) or ""

        return jsonify({"response": reply_text, "audio": audio_base64}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
