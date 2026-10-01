import os
import base64
from datetime import datetime
from zoneinfo import ZoneInfo

import json
import urllib.request
import urllib.error
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)

JARVIS_SYSTEM_PROMPT = (
    "Sei J.A.R.V.I.S., l'intelligenza artificiale personale del Signor Alessandro, "
    "barista, host del B&B Ale House al Lido delle Nazioni e appassionato di padel. "
    "Parli sempre in italiano, con tono elegante, distinto e servizievole, "
    "ma con una punta di vivacità e di ironia britannica. "
    "Rivolgiti ad Alessandro chiamandolo 'Signore' o 'Signor Alessandro'. "
    "Ogni risposta contiene una battuta secca, detta con finta serietà e senza mai ridere: "
    "usa l'understatement, mai battute lunghe o volgari. "
    "Alterna il tono formale a qualche frase colloquiale, come un maggiordomo che ha confidenza col padrone. "
    "Se l'argomento è serio (salute, soldi, ospiti del B&B), niente battute. "
    "Quando la conversazione inizia o ti viene chiesto uno stato, saluta in modo adatto all'ora "
    "e chiedi come puoi essergli d'aiuto. "
    "Le tue risposte vengono lette ad alta voce: massimo 2 o 3 frasi, "
    "niente elenchi, niente emoji, niente simboli. "
    "Se non sai una cosa, ammettilo con ironia invece di inventare. "
    "Se Alessandro dice 'modalità inglese', parla in inglese semplice e correggi gentilmente i suoi errori "
    "spiegando in italiano in una riga; torna all'italiano quando dice 'torna in italiano'."
)

HTML_LAYOUT = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>JARVIS</title>
    <style>
        body { background-color: #050b14; color: #00f0ff; font-family: -apple-system, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
        .arc-reactor { width: 160px; height: 160px; border-radius: 50%; border: 3px solid #00f0ff; box-shadow: 0 0 25px #00f0ff; display: flex; align-items: center; justify-content: center; cursor: pointer; margin-bottom: 30px; }
        .arc-core { width: 70px; height: 70px; border-radius: 50%; background: #ffffff; box-shadow: 0 0 20px #ffffff; }
        .status-text { font-size: 14px; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 15px; }
        .response-box { max-width: 80%; font-size: 16px; color: #e0f7fa; text-align: center; }
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
                    body: JSON.stringify({ message: message })
                });
                const data = await res.json();
                if (data.response) {
                    document.getElementById('status').innerText = 'ONLINE';
                    document.getElementById('output').innerText = data.response;
                    if (data.audio) {
                        audioPlayer.src = "data:audio/mp3;base64," + data.audio;
                        audioPlayer.play().catch(() => {});
                    }
                } else {
                    document.getElementById('status').innerText = 'ERRORE SISTEMA';
                }
            } catch (e) {
                document.getElementById('status').innerText = 'ERRORE CONNESSIONE';
            }
        }
    </script>
</body>
</html>"""


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
            "stability": 0.35,
            "similarity_boost": 0.75,
            "style": 0.3,
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

        now = datetime.now(ZoneInfo("Europe/Rome")).strftime("%H:%M di %d/%m/%Y")
        system_prompt = JARVIS_SYSTEM_PROMPT + " Ora attuale in Italia: " + now + "."

        completion = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=250,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )
        reply_text = completion.choices[0].message.content

        audio_base64 = elevenlabs_tts(reply_text) or openai_tts(client, reply_text) or ""

        return jsonify({"response": reply_text, "audio": audio_base64}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
