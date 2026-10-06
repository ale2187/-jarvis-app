import os, json, threading, io
from flask import Flask, render_template_string, request, jsonify
from openai import OpenAI
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

OPENAI_VOICE = os.environ.get("OPENAI_VOICE", "cedar")
MAX_HISTORY = 12

JARVIS_SYSTEM_PROMPT = (
    "Sei J.A.R.V.I.S., l'intelligenza artificiale personale del Signor Alessandro, "
    "barista, host del B&B Ale House al Lido delle Nazioni e giocatore di padel (livello 3,8 su scala 0-7). "
    "Parli sempre in italiano, con tono elegante, asciutto e servizievole, come il JARVIS dei film: "
    "ironia britannica, sarcasmo gentile, mai volgare. "
    "Rivolgiti ad Alessandro chiamandolo 'Signore' o 'Signor Alessandro'. "
    "REGOLE DELL'IRONIA: sii marcatamente ironico. In quasi ogni risposta normale inserisci una battuta secca, "
    "sarcastica ma elegante, detta con finta serietà e understatement. "
    "Punzecchia apertamente il Signore su puntualità, padel (livello 3,8 compreso), B&B, idee improvvisate e caffè. "
    "La battuta va dopo la risposta utile, mai lunga. Se la battuta non viene bene, saltala. "
    "Se l'argomento è serio (salute, soldi, contratti, ospiti del B&B, lavoro), niente battute. "
    "Quando la conversazione inizia, saluta in modo adatto all'ora e chiedi come puoi essergli d'aiuto. "
    "RISPOSTE NORMALI: massimo 2 o 3 frasi, senza elenchi, emoji o simboli. "
    "MODALITA' INGLESE: se Alessandro dice 'modalita' inglese', parla in inglese semplice, con frasi brevi."
)

HTML = """<!DOCTYPE html>
<html lang="it"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>J.A.R.V.I.S.</title><script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
<style>*{margin:0;padding:0;box-sizing:border-box}html,body{height:100%;background:#0a0e27;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;overflow:hidden;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}#app{display:flex;flex-direction:column;height:100%;padding:20px;gap:20px}.status{text-align:center;font-size:12px;color:#00d4ff;text-transform:uppercase;letter-spacing:2px}.reactor-container{display:flex;justify-content:center;flex:1;align-items:center}.reactor{position:relative;width:120px;height:120px;cursor:pointer;touch-action:manipulation}.reactor-outer{position:absolute;top:0;left:0;width:100%;height:100%;border:3px solid #00d4ff;border-radius:50%;box-shadow:0 0 30px rgba(0,212,255,0.8),inset 0 0 20px rgba(0,212,255,0.2)}.reactor-core{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:60px;height:60px;background:radial-gradient(circle at 30% 30%,#ffffff,#88ddff);border-radius:50%;box-shadow:0 0 40px rgba(136,221,255,0.9)}.pulsing{animation:pulse 1s infinite}@keyframes pulse{0%{box-shadow:0 0 40px rgba(136,221,255,0.9),inset 0 0 20px rgba(0,212,255,0.3)}50%{box-shadow:0 0 60px rgba(136,221,255,1),inset 0 0 30px rgba(0,212,255,0.5)}100%{box-shadow:0 0 40px rgba(136,221,255,0.9),inset 0 0 20px rgba(0,212,255,0.3)}}.chat-history{flex:0 1 auto;overflow-y:auto;border:1px solid #00d4ff40;border-radius:8px;padding:12px;background:rgba(10,14,39,0.7);font-size:13px;line-height:1.5}.message{margin:8px 0;padding:6px}.message-user{text-align:right;color:#00d4ff}.message-assistant{color:#b0e0e6}.input-area{display:flex;gap:8px;align-items:flex-end}textarea{flex:1;background:#1a1f3a;border:1px solid #00d4ff40;border-radius:6px;color:#e0e0e0;padding:8px;font-size:13px;resize:vertical;max-height:80px;font-family:inherit}textarea:focus{outline:none;border-color:#00d4ff;box-shadow:0 0 10px rgba(0,212,255,0.3)}button{background:#00d4ff;color:#0a0e27;border:none;border-radius:6px;padding:8px 12px;font-weight:bold;cursor:pointer;font-size:12px;transition:all 0.3s;touch-action:manipulation}button:active{transform:scale(0.95);box-shadow:0 0 15px rgba(0,212,255,0.6)}button:disabled{opacity:0.5;cursor:not-allowed}</style>
</head><body><div id="app">
<div class="status" v-text="status"></div>
<div class="reactor-container"><div class="reactor" @click="toggleListening">
<div class="reactor-outer" ref="reactorOuter"></div><div class="reactor-core" ref="reactorCore"></div></div></div>
<div class="chat-history"><div v-for="(msg,i) in history" :key="i" :class="['message',msg.role==='user'?'message-user':'message-assistant']" v-text="msg.content"></div></div>
<div class="input-area"><textarea v-model="userInput" placeholder="Scrivi un messaggio..." @keydown.enter.ctrl="sendMessage" rows="2"></textarea>
<button @click="sendMessage" :disabled="isProcessing || !userInput.trim()" style="white-space:nowrap;">Invia</button></div></div>
<script>const{createApp,ref,reactive}=Vue;createApp({setup(){const userInput=ref(""),history=reactive([]),isListening=ref(!1),isProcessing=ref(!1),status=ref("ONLINE - REALTIME"),reactorOuter=ref(null),reactorCore=ref(null);let recognition,audioContext;const initSpeechRecognition=()=>{const SpeechRecognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SpeechRecognition){alert("Speech Recognition non supportato.");return}recognition=new SpeechRecognition,recognition.lang="it-IT",recognition.interimResults=!1,recognition.onstart=()=>{isListening.value=!0,reactorOuter.value.classList.add("pulsing"),status.value="IN ASCOLTO..."},recognition.onresult=event=>{const transcript=event.results[event.results.length-1][0].transcript;userInput.value=transcript,sendMessage()},recognition.onerror=()=>resetReactor(),recognition.onend=()=>resetReactor()},resetReactor=()=>{isListening.value=!1,isProcessing.value=!1,reactorOuter.value&&reactorOuter.value.classList.remove("pulsing"),status.value="ONLINE - REALTIME"},toggleListening=async()=>{if(isProcessing.value)return;if(!audioContext){audioContext=new(window.AudioContext||window.webkitAudioContext);const osc=audioContext.createOscillator(),gain=audioContext.createGain();gain.gain.value=0,osc.connect(gain),gain.connect(audioContext.destination),osc.start(),osc.stop()}isListening.value?recognition?.stop():recognition?.start(),resetReactor()},sendMessage=async()=>{const msg=userInput.value.trim();if(!msg||isProcessing.value)return;isProcessing.value=!0,userInput.value="",history.push({role:"user",content:msg}),status.value="ELABORANDO...";try{const response=await fetch("/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:msg,history:history.slice(0,-1)})}),data=await response.json();history.push({role:"assistant",content:data.reply}),data.audio_url?(new Audio(data.audio_url)).onended=resetReactor:resetReactor()}catch(error){console.error("Error:",error),history.push({role:"assistant",content:"Errore nella comunicazione."}),resetReactor()}finally{isProcessing.value=!1}};return initSpeechRecognition(),{userInput,history,isListening,isProcessing,status,reactorOuter,reactorCore,toggleListening,sendMessage}}}).mount('#app');</script></body></html>
"""

@app.route('/')
def index():
    return HTML

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    msg = data.get('message', '')
    hist = data.get('history', [])
    
    messages = [{"role": "system", "content": JARVIS_SYSTEM_PROMPT}]
    for h in hist[-MAX_HISTORY:]:
        messages.append(h)
    messages.append({"role": "user", "content": msg})
    
    try:
        # Chat istantaneo
        r = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages, max_tokens=200
        )
        reply = r.choices[0].message.content.strip()
        
        # Audio in parallelo (non aspetta)
        def gen_audio():
            try:
                with client.audio.speech.with_streaming_response.create(
                    model="gpt-4o-mini-tts", voice=OPENAI_VOICE, input=reply,
                    instructions="Speak Italian fast, natural, like JARVIS in the movie. Bright, witty tone."
                ) as resp:
                    return resp.content
            except:
                return None
        
        audio_bytes = gen_audio()
        audio_b64 = __import__('base64').b64encode(audio_bytes).decode() if audio_bytes else None
        
        return jsonify({
            "reply": reply,
            "audio_url": f"data:audio/wav;base64,{audio_b64}" if audio_b64 else None
        })
    except Exception as e:
        return jsonify({"reply": f"Errore: {str(e)}", "audio_url": None}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
