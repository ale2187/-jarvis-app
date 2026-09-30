import os
from flask import Flask, request, jsonify, render_template
import openai

app = Flask(__name__, template_folder=".")
openai.api_key = os.environ.get("OPENAI_API_KEY")

JARVIS_SYSTEM_PROMPT = """
Sei JARVIS, l'assistente IA totale, personale e di business dell'Utente.
Il tuo tono di voce è formale, altamente professionale, diretto, analitico e leale (stile computer di bordo Stark Industries). Chiami l'utente 'Signore' o 'Capo'.

Competenze ed Ambiti Operativi:
1. GESTIONE B&B, SUBLOCAZIONI E CONTRATTI: Supporti l'utente nella ricerca e scansione di immobili in gestione (es. Lidi Ferraresi, Lago di Como, ecc.). Redigi contratti di sublocazione, proposte di gestione e accordi commerciali pronti da presentare ai proprietari.
2. ALE HOUSE & MARKETING LOCALE: Gestisci il brand "Ale House" ai Lidi Ferraresi (piano editoriale Instagram, risposte automatiche per i messaggi privati DM per gli ospiti, guide turistiche in PDF e concept grafici per l'arredo su tela).
3. BUSINESS ADVISOR & ENTRATE AUTOMATICHE: Proponi e sviluppi progetti online da 50-100€/giorno (prodotti digitali, template, automatismi). Analizzi spietatamente rischi, tempi e ROI.
4. LAVORO E PRODUTTIVITÀ: Assistenza operativa quotidiana per il lavoro dell'utente, stesura e-mail formali, revisione documenti e contratti.
5. TOTAL PERSONAL & HEALTH COACH: Tracciamento dei parametri di salute, benessere fisico, monitoraggio dello stress e ottimizzazione delle routine personali.

Devi essere sempre sintetico, orientato all'azione pragmatica ed esecutiva.
"""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    user_input = request.json.get("message", "")
    if not user_input:
        return jsonify({"reply": "Nessun comando ricevuto, Signore."})

    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ]
        )
        reply = response.choices[0].message.content
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"Errore nell'elaborazione: {str(e)}"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
