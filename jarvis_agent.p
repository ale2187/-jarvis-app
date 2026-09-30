import os
from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI

app = Flask(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

JARVIS_SYSTEM_PROMPT = """
Sei JARVIS, l'assistente IA totale, personale e professionale.
Il tuo tono di voce è formale, altamente efficiente, brillante e sintetico.
Devi rispondere sempre in modo chiaro e diretto.
"""

# Determina la cartella in cui si trova esattamente questo file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route("/")
def index():
    try:
        html_path = os.path.join(BASE_DIR, "index.html")
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        return render_template_string(html_content)
    except Exception as e:
        return f"Errore nel caricamento dell'interfaccia: {str(e)}", 500

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.json or {}
        user_message = data.get("message", "")
        
        if not user_message:
            return jsonify({"response": "Nessun messaggio ricevuto."}), 400

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )
        
        reply = completion.choices[0].message.content
        return jsonify({"response": reply})

    except Exception as e:
        return jsonify({"response": f"Errore interno del sistema: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
