import os
import base64
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)

JARVIS_SYSTEM_PROMPT = (
    "Sei J.A.R.V.I.S., l'intelligenza artificiale personale sviluppata per il Signor Alessandro. "
    "Il tuo tono di voce è estremamente formale, distinto, servizievole e con una sottile ironia britannica. "
    "Rivolgiti sempre ad Alessandro chiamandolo 'Signor Alessandro' o 'Signore'. "
    "Quando la conversazione inizia o ti viene chiesto uno stato, saluta dicendo: 'Buonasera Signor Alessandro' e chiedi come puoi essergli d'aiuto. "
    "Sii sintetico, incisivo, elegante ed estremamente operativo."
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
                        audioPlayer.play();
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

        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        reply_text = completion.choices[0].message.content

        audio_base64 = ""
        try:
            audio_response = client.audio.speech.create(
                model="tts-1",
                voice="onyx",
                input=reply_text
            )
            audio_base64 = base64.b64encode(audio_response.content).decode("utf-8")
        except Exception as tts_err:
            print("Errore TTS:", tts_err)

        return jsonify({"response": reply_text, "audio": audio_base64}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
