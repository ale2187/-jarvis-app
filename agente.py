"""
JARVIS - Agente conversazionale operativo.

Ciclo: comprensione -> scelta e uso degli strumenti -> verifica dei risultati -> risposta.
Il modello sceglie gli strumenti da solo (function calling). Nessun comando da ricordare.
Gli strumenti riusano il codice gia' esistente (archivio GitHub, radar, operatore, dossier).

Percorso precedente: resta intatto. puo_gestire() decide quando usare l'agente;
con JARVIS_AGENTE=0 l'agente e' disattivato e tutto torna al percorso precedente.
"""
import os, re, json, time, uuid, urllib.request, urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

import progetti as P
import radar_gestione as G
import operatore as OP
import dossier_app as DA

MODELLO = "gpt-4o-mini"
MAX_PASSI = 6
LAVORO = os.environ.get("JARVIS_LAVORO", os.path.join(os.path.dirname(os.path.abspath(__file__)), "lavoro"))

# Richieste che restano sul percorso precedente (ricerche rapide, business, calcio, notizie, media)
PERCORSO_PRECEDENTE = re.compile(
    r"crea un business|crea un'idea|business sostenibile|idea di business|pensa un business|"
    r"analisi calcio|analisi della giornata|partite di oggi|champions|serie a|"
    r"leggimi le notizie|notizie|cerca sul web|cerca online|cercami|ricerca web|"
    r"mandalo su telegram|invia su telegram|buongiorno|sveglia|foto|video", re.I)


def puo_gestire(messaggio):
    """True se la richiesta va all'agente. False = percorso precedente (comandi, business, calcio, notizie, media)."""
    if os.environ.get("JARVIS_AGENTE", "1") != "1":
        return False
    t = (messaggio or "").strip()
    if not t or DA.is_dossier(t) or DA.is_comando(t):
        return False
    return not PERCORSO_PRECEDENTE.search(t)


def _ora():
    return datetime.now(ZoneInfo("Europe/Rome")).strftime("%A %d/%m/%Y, ore %H:%M")


def _safe(nome):
    base = re.sub(r"[^A-Za-z0-9_.-]+", "_", nome or "file").strip("._") or "file"
    return base[:80]


# ---------------- strumenti (eseguono codice esistente) ----------------

def _leggi_archivio(stato=None, limite=30):
    d = P.carica()
    righe = []
    for o in d["opportunita"]:
        if stato and o.get("stato") != stato:
            continue
        righe.append({"id": o["id"], "stato": o.get("stato", "nuovo"), "categoria": o.get("categoria", ""),
                      "titolo": o.get("titolo", ""), "localita": o.get("localita", ""), "fonte": o["fonte"]})
    return {"totale": len(righe), "opportunita": righe[: int(limite or 30)]}


def _riassumi_archivio():
    d = P.carica()
    stati, cat = {}, {}
    for o in d["opportunita"]:
        stati[o.get("stato", "nuovo")] = stati.get(o.get("stato", "nuovo"), 0) + 1
        cat[o.get("categoria", "-")] = cat.get(o.get("categoria", "-"), 0) + 1
    return {"opportunita_totali": len(d["opportunita"]), "per_stato": stati, "per_categoria": cat,
            "ricerche_registrate": len(d.get("ricerche", []))}


def _cerca_opportunita(zona, categoria="A", richiesta_libera=""):
    gruppo = {"lago_di_como": "lago_di_como", "como": "lago_di_como", "lidi_ferraresi": "lidi_ferraresi", "lidi": "lidi_ferraresi"}.get((zona or "").lower())
    if not gruppo:
        return {"errore": "zona non riconosciuta: usare lago_di_como oppure lidi_ferraresi"}
    if categoria not in G.CATEGORIE:
        return {"errore": "categoria non valida: usare A, B o C"}
    prompt = G.prompt_ricerca(categoria, gruppo, G.GRUPPI_ZONA[gruppo], "portali")
    if richiesta_libera:
        prompt += " Richiesta dell'utente: " + richiesta_libera
    txt, query = G._web_call(prompt)
    lista = G.estrai_json(txt) or []
    for c in lista:
        c.update({"cat_ricerca": categoria, "gruppo_zona": gruppo, "gruppo_fonti": "portali"})
    d = P.carica()
    esiti = G.valuta(lista, d)
    salvate = G.salva(d, esiti, [{"nome": "%s | %s | agente" % (categoria, gruppo), "esito": "ok",
                                  "risultati": len(lista), "query": query}])
    return {"candidati_trovati": len(lista), "verificate_e_salvate": [
                {"id": o["id"], "titolo": o.get("titolo", ""), "localita": o.get("localita", ""), "fonte": o["fonte"],
                 "stato_commerciale": o.get("stato_commerciale", "")} for o in salvate],
            "scartate_per_motivo": esiti["scartati"], "query_eseguite": query}


def _cerca_web(domanda):
    txt, query = G._web_call("Rispondi in italiano usando la ricerca web. Cita il nome del sito fonte. "
                             "Non inventare dati: se non trovi un'informazione affidabile, dillo. Domanda: " + domanda,
                             budget=60, max_out=800)
    return {"risposta": txt, "query_eseguite": query}


def _verifica_pagina(url):
    stato, corpo = G.leggi_pagina(url)
    return {"stato": stato, "anteprima": corpo[:300]}


def _genera_dossier(id):
    d = P.carica()
    o = OP.dossier(d, int(id))
    P.salva(d)
    return {"id": o["id"], "dossier": (o.get("dossier") or "")[:3000], "stato": o.get("stato")}


def _aggiorna_stato(id, stato):
    d = P.carica()
    o = P.stato(d, int(id), stato)
    P.salva(d)
    return {"id": o["id"], "stato": o["stato"]}


def _importa_dossier(testo):
    return {"esito": DA.ingest(testo)}


def _crea_file(nome, contenuto):
    os.makedirs(LAVORO, exist_ok=True)
    nome = _safe(nome)
    percorso = os.path.join(LAVORO, nome)
    with open(percorso, "w", encoding="utf-8") as f:
        f.write(contenuto)
    return {"percorso": percorso, "byte": os.path.getsize(percorso)}


def _consegna_file(percorso):
    tok, chat = os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not os.path.exists(percorso):
        return {"errore": "file non trovato: " + percorso}
    if not tok or not chat:
        return {"errore": "Telegram non configurato: il file resta disponibile in " + percorso}
    bordo = uuid.uuid4().hex
    with open(percorso, "rb") as f:
        contenuto = f.read()
    corpo = (("--%s\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n%s\r\n" % (bordo, chat)).encode()
             + ("--%s\r\nContent-Disposition: form-data; name=\"document\"; filename=\"%s\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n" % (bordo, os.path.basename(percorso))).encode()
             + contenuto + ("\r\n--%s--\r\n" % bordo).encode())
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendDocument" % tok, data=corpo,
                                 headers={"Content-Type": "multipart/form-data; boundary=" + bordo})
    with urllib.request.urlopen(req, timeout=30) as r:
        ok = json.loads(r.read().decode()).get("ok")
    return {"consegnato_su_telegram": bool(ok)}


def _salva_preferenza(chiave, valore):
    d = P.carica()
    d.setdefault("preferenze", {})[chiave] = valore
    P.salva(d)
    return {"salvata": chiave}


def _leggi_preferenze():
    return {"preferenze": P.carica().get("preferenze", {})}


def _genera_media(tipo, descrizione):
    return {"errore": "generazione di %s non ancora integrata: nessun servizio di generazione configurato. "
                      "Posso prepararne il testo, la sceneggiatura e le istruzioni." % tipo}


STRUMENTI = {
    "leggi_archivio": (_leggi_archivio, {"type": "object", "properties": {
        "stato": {"type": "string", "description": "filtra per stato, opzionale"},
        "limite": {"type": "integer"}}}),
    "riassumi_archivio": (_riassumi_archivio, {"type": "object", "properties": {}}),
    "cerca_opportunita": (_cerca_opportunita, {"type": "object", "properties": {
        "zona": {"type": "string", "enum": ["lago_di_como", "lidi_ferraresi"]},
        "categoria": {"type": "string", "enum": ["A", "B", "C"], "description": "A proprietari con affitti, B cercano gestore, C societa'"},
        "richiesta_libera": {"type": "string"}}, "required": ["zona"]}),
    "cerca_web": (_cerca_web, {"type": "object", "properties": {"domanda": {"type": "string"}}, "required": ["domanda"]}),
    "verifica_pagina": (_verifica_pagina, {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}),
    "genera_dossier": (_genera_dossier, {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}),
    "aggiorna_stato": (_aggiorna_stato, {"type": "object", "properties": {
        "id": {"type": "integer"}, "stato": {"type": "string", "enum": P.STATI}}, "required": ["id", "stato"]}),
    "importa_dossier": (_importa_dossier, {"type": "object", "properties": {"testo": {"type": "string"}}, "required": ["testo"]}),
    "crea_file": (_crea_file, {"type": "object", "properties": {
        "nome": {"type": "string"}, "contenuto": {"type": "string"}}, "required": ["nome", "contenuto"]}),
    "consegna_file": (_consegna_file, {"type": "object", "properties": {"percorso": {"type": "string"}}, "required": ["percorso"]}),
    "salva_preferenza": (_salva_preferenza, {"type": "object", "properties": {
        "chiave": {"type": "string"}, "valore": {"type": "string"}}, "required": ["chiave", "valore"]}),
    "leggi_preferenze": (_leggi_preferenze, {"type": "object", "properties": {}}),
    "genera_media": (_genera_media, {"type": "object", "properties": {
        "tipo": {"type": "string", "enum": ["immagine", "video"]}, "descrizione": {"type": "string"}},
        "required": ["tipo", "descrizione"]}),
}


def _schemi():
    out = []
    for nome, (fn, parametri) in STRUMENTI.items():
        desc = (fn.__doc__ or "").strip() or nome.replace("_", " ")
        out.append({"type": "function", "function": {"name": nome, "description": desc, "parameters": parametri}})
    return out


SISTEMA = (
    "Sei JARVIS, l'assistente operativo personale del Signor Alessandro: barista, host del B&B Ale House al Lido delle Nazioni, "
    "cerca lavoro e sviluppa attivita' di gestione immobiliare. Parli in italiano, in modo chiaro e diretto, senza formule. "
    "Capisci richieste libere: scegli tu gli strumenti necessari, usali, controlla i risultati e poi rispondi. "
    "Regole: non inventare annunci, proprietari, contatti, numeri o fatti; se uno strumento restituisce un errore, dillo e proponi cosa fare. "
    "Non inviare mai messaggi a proprietari e non firmare accordi: prepara e attendi l'approvazione. "
    "Per immagini e video usa genera_media e spiega chiaramente il limite. "
    "Alla fine riferisci cosa hai fatto davvero: strumenti usati, risultati, file prodotti, cosa non e' riuscito. Ora: {ora}. {contesto}"
)


def _contesto():
    try:
        d = P.carica()
        pref = d.get("preferenze", {})
        base = "Opportunita' in archivio: %d." % len(d["opportunita"])
        return base + (" Preferenze: " + json.dumps(pref, ensure_ascii=False) if pref else "")
    except P.ArchivioError as e:
        return "Archivio non raggiungibile in questo momento (%s): dichiaralo se serve l'archivio." % str(e)[:120]


def _openai(messaggi, strumenti):
    payload = {"model": MODELLO, "messages": messaggi, "tools": strumenti, "max_tokens": 900}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + os.environ.get("OPENAI_API_KEY", "")})
    with urllib.request.urlopen(req, timeout=50) as r:
        return json.loads(r.read().decode())


def run(messaggio, storia=None):
    """Esegue il ciclo agente. Ritorna dict {reply, azioni, error}. Mai eccezioni verso il chiamante."""
    if not os.environ.get("OPENAI_API_KEY"):
        return {"reply": "Il motore non e' configurato: manca la chiave del modello.", "azioni": [], "error": "AGENTE chiave mancante"}
    msgs = [{"role": "system", "content": SISTEMA.format(ora=_ora(), contesto=_contesto())}]
    for m in (storia or [])[-10:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": messaggio})
    azioni = []
    schemi = _schemi()
    for _ in range(MAX_PASSI):
        try:
            risposta = _openai(msgs, schemi)
        except Exception as e:
            return {"reply": "Ho un problema con il motore di ragionamento, Signore: non ho completato la richiesta. (%s)" % str(e)[:120],
                    "azioni": azioni, "error": "AGENTE modello: " + str(e)[:120]}
        scelta = risposta["choices"][0]["message"]
        chiamate = scelta.get("tool_calls") or []
        if not chiamate:
            return {"reply": (scelta.get("content") or "").strip() or "Fatto.", "azioni": azioni, "error": None}
        msgs.append(scelta)
        for c in chiamate:
            nome = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if nome not in STRUMENTI:
                esito = {"errore": "strumento sconosciuto: " + nome}
            else:
                try:
                    esito = STRUMENTI[nome][0](**args)
                except Exception as e:
                    esito = {"errore": "%s: %s" % (type(e).__name__, str(e)[:200])}
            azioni.append({"strumento": nome, "errore": "errore" in esito if isinstance(esito, dict) else False})
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(esito, ensure_ascii=False, default=str)[:6000]})
    return {"reply": "Ho raggiunto il limite di passaggi per questa richiesta: ti riassumo cosa ho fatto finora nelle azioni registrate.",
            "azioni": azioni, "error": "AGENTE limite passaggi"}
