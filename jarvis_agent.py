import os
from flask import Flask, render_template_string, request, jsonify
from openai import OpenAI

app = Flask(__name__)

SYSTEM_PROMPT = """
Sei Jarvis, un assistente virtuale altamente avanzato, efficiente, formale ma cordiale.
Fornisci risposte chiare, analitiche e orientate alla risoluzione dei problemi per la gestione immobiliare, HoReCa e attività operative quotidiane.
"""

@app.route("/")
def home():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return render_template_string(f.read())
    except Exception as e:
        return f"Errore caricamento interfaccia: {str(e)}", 500

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json or {}
    user_message = data.get("message", "")
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"response": "Errore: OPENAI_API_KEY non configurata nelle Environment Variables su Render."}), 400
    
    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        reply = completion.choices[0].message.content
        return jsonify({"response": reply})
    except Exception as e:
        return jsonify({"response": f"Errore durante l'elaborazione dell'IA: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
