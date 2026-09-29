import os
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>Jarvis AI</title>
    
    <!-- Configurazione PWA per iOS -->
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Jarvis">
    
    <!-- Icona per la schermata Home dell'iPhone -->
    <link rel="apple-touch-icon" href="https://img.icons8.com/color/512/iron-man.png">
    <link rel="icon" type="image/png" href="https://img.icons8.com/color/512/iron-man.png">

    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; display: flex; flex-direction: column; height: 100vh; box-sizing: border-box; }
        #chat { flex: 1; overflow-y: auto; margin-bottom: 20px; display: flex; flex-direction: column; gap: 10px; }
        .msg { padding: 12px 16px; border-radius: 12px; max-width: 80%; line-height: 1.4; }
        .user { background: #2563eb; align-self: flex-end; }
        .bot { background: #334155; align-self: flex-start; }
        .input-area { display: flex; gap: 10px; }
        input { flex: 1; padding: 14px; border-radius: 8px; border: none; background: #1e293b; color: white; font-size: 16px; }
        button { padding: 14px 20px; border-radius: 8px; border: none; background: #2563eb; color: white; font-weight: bold; font-size: 16px; cursor: pointer; }
    </style>
</head>
<body>
    <div id="chat">
        <div class="msg bot">Sistemi operativi. Come posso assisterla?</div>
    </div>
    <div class="input-area">
        <input type="text" id="userInput" placeholder="Scrivi a Jarvis..." onkeydown="if(event.key==='Enter') sendMsg()">
        <button onclick="sendMsg()">Invia</button>
    </div>
    <script>
        async function sendMsg() {
            const input = document.getElementById('userInput');
            const txt = input.value.trim();
            if (!txt) return;
            
            const chat = document.getElementById('chat');
            chat.innerHTML += `<div class="msg user">${txt}</div>`;
            input.value = '';
            chat.scrollTop = chat.scrollHeight;

            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: txt})
            });
            const data = await res.json();
            chat.innerHTML += `<div class="msg bot">${data.response}</div>`;
            chat.scrollTop = chat.scrollHeight;
        }
    </script>
</body>
</html>"""

SYSTEM_PROMPT = """
Sei Jarvis, un assistente virtuale altamente avanzato, efficiente, formale ma cordiale.
Fornisci risposte chiare, analitiche e orientate alla risoluzione dei problemi per la gestione immobiliare, HoReCa e attività operative quotidiane.
"""

@app.route("/")
def home():
    return HTML_TEMPLATE

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
