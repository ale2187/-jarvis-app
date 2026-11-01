"""
JARVIS app - riconosce un dossier incollato in chat e crea/aggiorna la scheda dell'opportunita'.
Gestisce anche il comando: "stato <id> <stato>" e "lista".
Non invia nulla ai proprietari: prepara il pacchetto e aspetta la tua approvazione.
"""
import re
import progetti as P
import operatore as OP

PROGETTO = "gestione-clienti"

ETICHETTE = {
    "id": r"ID opportunita'",
    "categoria": r"Categoria",
    "nome": r"Nome immobile o struttura",
    "localita": r"Localita'",
    "link": r"Link diretto verificato",
    "soggetto": r"Soggetto",
    "recapiti": r"Recapiti pubblici",
    "prove": r"Prove concrete raccolte",
    "motivo": r"Motivo dell'interesse commerciale",
    "livello": r"Livello di verifica",
    "proposta": r"Proposta di contatto consigliata",
    "azione": r"Azione successiva",
}

STATI_UTENTE = {
    "da verificare": "da_verificare", "pronto al contatto": "pronto_al_contatto", "pronto": "pronto_al_contatto",
    "contattato": "contattato", "risposta ricevuta": "risposta_ricevuta", "appuntamento": "appuntamento",
    "acquisito": "acquisito", "perso": "perso", "nuovo": "nuovo",
}


def is_dossier(testo):
    t = testo or ""
    return "Link diretto verificato:" in t or "DOSSIER OPPORTUNITA'" in t or "DOSSIER OPPORTUNITA’" in t


def is_comando(testo):
    t = (testo or "").strip().lower()
    return bool(re.match(r"^stato\s+\d+\s+", t)) or t in ("lista", "lista opportunita", "lista opportunità")


def parse_dossier(testo):
    out = {}
    for chiave, etichetta in ETICHETTE.items():
        m = re.search(r"^[\-\s•]*" + etichetta + r"\s*:\s*(.+)$", testo or "", re.M | re.I)
        if m:
            out[chiave] = m.group(1).strip()
    m = re.search(r"ID\s*(?:opportunit[aà])?\s*n?\.?\s*(\d+)", testo or "", re.I)
    if m and "id" not in out:
        out["id"] = m.group(1)
    if out.get("id") and not str(out["id"]).isdigit():
        mm = re.search(r"(\d+)", out["id"])
        out["id"] = mm.group(1) if mm else None
    return out


def _trova_per_link(d, link):
    return P.opportunita_esistente(d, link) if link else None


def ingest(testo):
    campi = parse_dossier(testo)
    link = (campi.get("link") or "").strip()
    if not link.startswith("http"):
        return "Il dossier non contiene un link diretto verificato: non posso creare la scheda. Controlla la riga 'Link diretto verificato'."
    d = P.carica()
    P.crea_progetto(d, PROGETTO, "Acquisizione clienti per gestione immobiliare e turistica")
    o = _trova_per_link(d, link)
    nuova = o is None
    if nuova:
        o = P.aggiungi_opportunita(d, PROGETTO, campi.get("localita", ""), link, titolo=campi.get("nome", ""))
        o["stato"] = "da_verificare"
    o.update({
        "titolo": campi.get("nome", o.get("titolo", "")), "localita": campi.get("localita", o.get("localita", "")),
        "tipo_soggetto": campi.get("soggetto", o.get("tipo_soggetto", "")), "contatto_pubblico": campi.get("recapiti"),
        "categoria_telegram": campi.get("categoria", ""), "prove_utente": campi.get("prove", ""),
        "motivo": campi.get("motivo", o.get("motivo", "")), "livello_verifica": campi.get("livello", ""),
        "proposta_contatto": campi.get("proposta", ""), "azione_successiva": campi.get("azione", ""),
        "dossier_utente": testo.strip(),
        "azioni": ["approvare il pacchetto", "inviare il primo messaggio (manuale, tu)",
                   "follow-up a 7 giorni", "follow-up a 14 giorni"],
    })
    if "pronto" not in (o.get("stato") or ""):
        o.setdefault("stato", "da_verificare")
    try:
        OP.dossier(d, o["id"])
        pacchetto = "pacchetto preparato in archivio"
    except Exception as e:
        pacchetto = "pacchetto non generato: " + str(e)[:80]
    P.salva(d)
    return ("Scheda ID %d %s.\nStato: %s\nLink: %s\n%s\nAzioni: %s"
            % (o["id"], "creata" if nuova else "aggiornata", o.get("stato"), link, pacchetto, "; ".join(o["azioni"])))


def comando(testo):
    t = testo.strip()
    if t.lower().startswith("lista"):
        d = P.carica()
        righe = [P.riepilogo(d, PROGETTO)]
        return "\n".join(righe)
    m = re.match(r"^stato\s+(\d+)\s+(.+)$", t, re.I)
    if not m:
        return "Comando non riconosciuto."
    id_, nome = int(m.group(1)), m.group(2).strip().lower()
    chiave = STATI_UTENTE.get(nome, nome.replace(" ", "_"))
    d = P.carica()
    try:
        o = P.stato(d, id_, chiave)
    except (ValueError, KeyError) as e:
        return "Non posso aggiornare: " + str(e)
    P.salva(d)
    return "ID %d -> %s" % (o["id"], o["stato"])


def gestisci(testo):
    if is_dossier(testo):
        return ingest(testo)
    return comando(testo)
