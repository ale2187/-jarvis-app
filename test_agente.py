"""Test dell'agente conversazionale. Modello, GitHub, siti e Telegram sono simulati. Eseguire: python3 test_agente.py"""
import os, sys, json, io, base64, re, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.update(GITHUB_TOKEN="t", GITHUB_REPO="ale2187/-jarvis-app", GITHUB_BRANCH="Dati", OPENAI_API_KEY="k",
                  PROGETTI_PATH="/tmp/ag_p.json", JARVIS_LAVORO="/tmp/ag_lavoro", TELEGRAM_TOKEN="x", TELEGRAM_CHAT_ID="1")
for f in ("/tmp/ag_p.json",):
    if os.path.exists(f): os.remove(f)
import shutil; shutil.rmtree("/tmp/ag_lavoro", ignore_errors=True)
import progetti as P, agente as AG
class RG(io.BytesIO):
    def __init__(self, status, data=b""):
        super().__init__(data); self.status=status
    def __enter__(self): return self
    def __exit__(self,*a): pass
class FakeGH:
    def __init__(self):
        self.ramo=True; self.content=None; self.sha=0; self.giu=False; self.conflitti=0; self.puts=[]
    def __call__(self, req, timeout=0):
        u=req.full_url; m=req.get_method()
        if "api.github.com" not in u:
            return None
        if self.giu: raise urllib.error.URLError("connessione persa")
        if "/git/ref/heads/" in u:
            return RG(200 if self.ramo else 404, b"{}")
        if "/contents/progetti.json" in u and m=="GET":
            if self.content is None: return RG(404, b"{}")
            return RG(200, json.dumps({"sha":str(self.sha),"content":base64.b64encode(self.content.encode()).decode()}).encode())
        if "/contents/progetti.json" in u and m=="PUT":
            body=json.loads(req.data.decode())
            self.puts.append(body)
            if self.conflitti>0:
                self.conflitti-=1; self.sha+=1; return RG(409, b"{}")
            if body.get("sha") is not None and str(body["sha"])!=str(self.sha):
                return RG(409, b"{}")
            self.content=base64.b64decode(body["content"]).decode(); self.sha+=1
            return RG(201, b"{}")
        return RG(404, b"{}")

gh = FakeGH()
CODA = []          # risposte scriptate del modello, una per passo
VISTI = []         # messaggi ricevuti dal modello (per verificare i risultati degli strumenti)
RICERCA = {"lista": []}
PAGINE = {"https://www.casevacanzelido.it/affitto/771": ("ok", "Bilocale vista lago Como in affitto. Contatti 351 770 5794. Localita Como.")}
class RX(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): pass
def _msg(testo=None, chiamate=None):
    m = {"role": "assistant", "content": testo}
    if chiamate: m["tool_calls"] = chiamate
    return {"choices": [{"message": m}]}
def _chiamata(nome, args, i):
    return {"id": "c%d" % i, "type": "function", "function": {"name": nome, "arguments": json.dumps(args)}}
def fake(req, timeout=0):
    u = req.full_url
    if "api.github.com" in u: return gh(req, timeout)
    if "/v1/responses" in u:
        return RX(json.dumps({"output": [{"type": "web_search_call", "action": {"query": "proprietari case vacanza lago di como"}},
                                         {"type": "message", "content": [{"type": "output_text", "text": json.dumps(RICERCA["lista"], ensure_ascii=False)}]}]}).encode())
    if "/v1/chat/completions" in u:
        VISTI.append(json.loads(req.data.decode())["messages"])
        if not CODA: raise urllib.error.URLError("modello non raggiungibile")
        return RX(json.dumps(CODA.pop(0)).encode())
    if "api.telegram.org" in u: return RX(b'{"ok":false}')
    if u in PAGINE: return RX(PAGINE[u][1].encode())
    raise urllib.error.HTTPError(u, 404, "nf", {}, None)
urllib.request.urlopen = fake
e = []
def ok(n, c): print(("OK  " if c else "KO  ") + n); e.append(bool(c))

# base: archivio con due schede
d = P._vuoto(); P.crea_progetto(d, "gestione-clienti", "G")
P.aggiungi_opportunita(d, "gestione-clienti", "Como", "https://www.larihome-esempio.it/collaborazioni/gestori", titolo="Larihome")
P.aggiungi_opportunita(d, "gestione-clienti", "Lido", "https://www.casevacanzelido.it/affitto/900", titolo="Bilocale Lido")
gh.content = json.dumps(d, ensure_ascii=False); gh.sha = 1

# T1 riassunto dell'archivio, senza dover dire quale strumento usare
CODA[:] = [_msg(chiamate=[_chiamata("riassumi_archivio", {}, 1)]), _msg("Hai 2 opportunita' salvate: 2 da verificare.")]
r = AG.run("come siamo messi con l'archivio? dimmi quante cose ho salvate")
ok("T1 riassunto archivio: usa lo strumento giusto e risponde", "2" in r["reply"] and r["azioni"][0]["strumento"] == "riassumi_archivio" and r["error"] is None)
ok("T1b il risultato dello strumento e' tornato al modello", any("opportunita_totali" in str(m.get("content")) for m in VISTI[-1] if m.get("role") == "tool"))

# T2 ricerca libera: proprietari di case vacanza sul Lago di Como
RICERCA["lista"] = [{"url": "https://www.casevacanzelido.it/affitto/771", "nome": "Bilocale vista lago", "localita": "Como",
                     "tipo": "privato", "testo_letto": "Bilocale in affitto, poche foto", "segnali": ["poche foto"], "n_foto": 3,
                     "lunghezza_descrizione": 120, "contatto_pubblico": "351 770 5794"}]
CODA[:] = [_msg(chiamate=[_chiamata("cerca_opportunita", {"zona": "lago_di_como", "categoria": "A"}, 2)]),
           _msg("Ho trovato 1 proprietario verificato sul Lago di Como e l'ho salvato in archivio.")]
r = AG.run("trovami proprietari di case vacanza sul lago di Como")
arc = json.loads(gh.content)
ok("T2 ricerca libera: lo strumento scelto dal modello salva la scheda verificata",
   any(o["fonte"] == "https://www.casevacanzelido.it/affitto/771" for o in arc["opportunita"]))
ok("T2b risposta coerente con il risultato", "1" in r["reply"] and "Lago" in r["reply"])

# T3 idea commerciale: il modello crea un file e prova a consegnarlo; senza Telegram l'errore viene dichiarato
PERCORSO = os.path.join("/tmp/ag_lavoro", "proposta_lago.md")
CODA[:] = [_msg(chiamate=[_chiamata("crea_file", {"nome": "proposta_lago.md", "contenuto": "# Proposta\nGestione completa."}, 3)]),
           _msg(chiamate=[_chiamata("consegna_file", {"percorso": PERCORSO}, 4)]),
           _msg("Ho preparato la proposta in proposta_lago.md. Non sono riuscito a consegnarla su Telegram perche' il canale non e' configurato in questo ambiente.")]
os.environ.pop("TELEGRAM_TOKEN"); os.environ.pop("TELEGRAM_CHAT_ID")
r = AG.run("sviluppami un'idea: gestione di case vacanza per host che non hanno tempo, e preparami la proposta")
ok("T3 il file esiste davvero nella cartella di lavoro", os.path.exists(PERCORSO) and "Gestione" in open(PERCORSO).read())
ok("T3b l'errore di consegna e' dichiarato, non nascosto", any(a["strumento"] == "consegna_file" and a["errore"] for a in r["azioni"]) and "consegn" in r["reply"].lower())
os.environ.update(TELEGRAM_TOKEN="x", TELEGRAM_CHAT_ID="1")

# T4 errore di uno strumento: il modello lo riceve e spiega
CODA[:] = [_msg(chiamate=[_chiamata("cerca_opportunita", {"zona": "pisa", "categoria": "A"}, 5)]),
           _msg("La zona Pisa non e' tra quelle che seguo: posso cercare sul Lago di Como o sui Lidi Ferraresi.")]
r = AG.run("cerca case a Pisa")
tool_msg = [m for m in VISTI[-1] if m.get("role") == "tool"]
ok("T4 errore dello strumento tornato al modello", tool_msg and "errore" in tool_msg[-1]["content"])
ok("T4b risposta che spiega l'errore e propone alternativa", "Pisa" in r["reply"] and any(a["errore"] for a in r["azioni"]))

# T5 preferenza ricordata nelle conversazioni successive
CODA[:] = [_msg(chiamate=[_chiamata("salva_preferenza", {"chiave": "tono", "valore": "diretto e senza giri di parole"}, 6)]),
           _msg("Preso: useremo un tono diretto.")]
AG.run("d'ora in poi parlami in modo diretto, senza giri di parole")
CODA[:] = [_msg("Ok.")]
AG.run("ciao")
sistema = [m for m in VISTI[-1] if m.get("role") == "system"][0]["content"]
ok("T5 preferenza salvata nell'archivio e riletta alla richiesta successiva", "diretto" in sistema and "diretto" in json.dumps(json.loads(gh.content).get("preferenze", {})))

# T6 immagini e video: dichiarato il limite, nessuna promessa
CODA[:] = [_msg(chiamate=[_chiamata("genera_media", {"tipo": "video", "descrizione": "Reel tour in barca nei Lidi"}, 7)]),
           _msg("Non posso ancora generare il video: ho preparato la sceneggiatura e le istruzioni.")]
r = AG.run("fammi un Reel sul tour in barca nei Lidi Ferraresi")
ok("T6 video: limite dichiarato, nessun file inventato", any(a["strumento"] == "genera_media" and a["errore"] for a in r["azioni"]) and "video" in r["reply"].lower())

# T7 instradamento: libere -> agente; comandi, business, calcio, notizie, media -> percorso precedente
casi = {"ciao, come va?": True, "trovami proprietari a Como": True, "lista": False, "crea un business per cani": False,
        "analisi calcio di oggi": False, "leggimi le notizie": False, "buongiorno jarvis": False, "mandalo su telegram": False,
        "invia su telegram la risposta": False}
ok("T7 instradamento corretto su tutti i casi", all(AG.puo_gestire(k) == v for k, v in casi.items()))
os.environ["JARVIS_AGENTE"] = "0"
ok("T7b agente spento: tutto torna al percorso precedente", AG.puo_gestire("ciao") is False)
os.environ["JARVIS_AGENTE"] = "1"

# T8 modello non raggiungibile: errore dichiarato, nessuna eccezione
CODA[:] = []
r = AG.run("trovami case a Como")
ok("T8 modello giu': risposta chiara, nessuna eccezione", "problema" in r["reply"] and r["error"] and "modello" in r["error"])

# T9 limite di passaggi: non gira all'infinito
CODA[:] = [_msg(chiamate=[_chiamata("riassumi_archivio", {}, 9)]) for _ in range(AG.MAX_PASSI + 2)]
r = AG.run("ripeti all'infinito")
ok("T9 limite di passaggi rispettato e dichiarato", r["error"] == "AGENTE limite passaggi" and len(r["azioni"]) == AG.MAX_PASSI)

# T10 nessuna chiave: messaggio chiaro
os.environ.pop("OPENAI_API_KEY"); r = AG.run("ciao"); os.environ["OPENAI_API_KEY"] = "k"
ok("T10 chiave mancante: messaggio chiaro", "chiave" in r["reply"])

# T11 archivio non raggiungibile: l'agente lo dichiara e non scrive
gh.giu = True; prima = gh.content
CODA[:] = [_msg(chiamate=[_chiamata("aggiorna_stato", {"id": 1, "stato": "contattato"}, 11)]), _msg("Non ho potuto aggiornare lo stato: l'archivio non e' raggiungibile, nessuna modifica salvata.")]
r = AG.run("segna la prima scheda come contattata")
gh.giu = False
ok("T11 archivio giu': nessuna scrittura e messaggio dichiarato", gh.content == prima and "nessuna modifica" in r["reply"])

print("\nRISULTATO AGENTE:", sum(e), "/", len(e))
