import os
import base64
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

# Configurazione Client OpenAI
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

JARVIS_SYSTEM_PROMPT = """
Sei JARVIS, l'assistente IA operativo di Alessandro.
Il tuo tono di voce è formale, cinematografico, sintetico ed efficiente.
Rispondi in modo diretto senza preamboli inutili.
"""

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online", "message": "JARVIS System Operational"}), 200

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json() or {}
        user_message = data.get("message", "")

        if not user_message:
            return jsonify({"error": "Nessun messaggio fornito"}), 400

        # 1. Chiamata a GPT-4o
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        reply_text = completion.choices[0].message.content

        # 2. Generazione Audio Nativo OpenAI (Voce Onyx)
        audio_response = client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=reply_text
        )

        # 3. Conversione in Base64 per la PWA
        audio_base64 = base64.b64encode(audio_response.content).decode("utf-8")

        return jsonify({
            "response": reply_text,
            "audio": audio_base64
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
