"""
JARVIS - Operatore commerciale. Dato un contatto dell'archivio, prepara il dossier completo:
analisi, motivo del contatto, lettera personalizzata, proposta di gestione completa,
proposta condivisa 70/30 con base esplicita, bozza di contratto da far verificare,
piano di primo contatto e follow-up, cosa devi fare tu.
NON invia messaggi, non prende impegni, non firma nulla. Prepara soltanto.

Uso:
  python3 operatore.py dossier --id 3
  python3 operatore.py stato --id 3 --stato contattato
  python3 operatore.py lista
"""
import sys, json, argparse
from datetime import date, timedelta

import progetti as P
import radar_gestione as G


def trova(d, id_):
    for o in d["opportunita"]:
        if o["id"] == id_:
            return o
    raise KeyError("id non trovato: %s" % id_)


def fatti(o):
    return {
        "categoria": o.get("categoria_nome") or o.get("categoria"),
        "stato_commerciale": o.get("stato_commerciale"),
        "soggetto": o.get("tipo_soggetto") or "non identificato",
        "nome": o.get("titolo") or "non indicato",
        "localita": o.get("localita") or o.get("zona") or "non indicata",
        "fonte": o["fonte"],
        "osservato": o.get("osservato") or "",
        "segnali": o.get("segnali") or [],
        "n_foto": o.get("n_foto"),
        "recapito_pubblico": o.get("contatto_pubblico") or "non disponibile",
        "pagina_prova": o.get("pagina_prova"),
        "frase_prova": o.get("frase_prova"),
    }


def prompt_dossier(o):
    f = fatti(o)
    incerto = ("Il contatto NON e' confermato come cliente interessato: scrivilo chiaramente in ANALISI e MOTIVO, "
               "non dichiarare che il proprietario ha difficolta' o che cerca un gestore." if o.get("stato_commerciale") != "interessante"
               else "Esiste una prova della richiesta (pagina_prova e frase_prova): citala testualmente.")
    return ("Prepara in italiano, in testo semplice senza asterischi, un dossier di acquisizione per Alessandro (host del B&B Ale House, "
            "Lido delle Nazioni: prenotazioni, check-in, pulizie, comunicazione con gli ospiti). Usa SOLO questi fatti, senza inventare "
            "numeri, recensioni, problemi del proprietario, prezzi o recapiti: " + json.dumps(f, ensure_ascii=False) + ". " + incerto + " "
            "Sezioni con titolo, in quest'ordine: "
            "ANALISI (cosa si sa dell'immobile o della societa', cosa NON si sa); "
            "MOTIVO (perche' potrebbe servire un gestore, o perche' va approfondito, senza certezze); "
            "LETTERA (personalizzata sull'osservazione concreta, 7 righe max, proposta di chiacchierata senza impegno, "
            "se non interessa basta un cenno); "
            "PROPOSTA GESTIONE COMPLETA (servizi inclusi, responsabilita' del gestore e del proprietario, nessuna cifra inventata); "
            "PROPOSTA CONDIVISA 70/30 (ipotesi: 70% proprietario e 30% gestore sulla base esplicita dei ricavi lordi di affitto meno "
            "i costi operativi documentati, come pulizie, commissioni delle piattaforme e utenze; le imposte non entrano nella base; "
            "e' un'ipotesi da negoziare, non un risultato); "
            "BOZZA CONTRATTO (solo i punti principali, con la dicitura: da sottoporre a commercialista e avvocato prima dell'uso); "
            "PIANO (primo contatto e follow-up a 7 e 14 giorni, cosa scrivere in ciascuno); "
            "COSA DEVI FARE TU (elenco numerato di azioni che solo Alessandro puo' compiere: verificare il link, inviare il messaggio, "
            "decidere). Non promettere guadagni.")


def dossier(d, id_):
    o = trova(d, id_)
    try:
        testo, _q = G._web_call(prompt_dossier(o), budget=90, max_out=2200)
        testo = testo.strip()
    except Exception as e:
        testo = "[dossier non generato: %s]" % str(e)[:80]
    o["dossier"] = testo
    o["data_dossier"] = date.today().isoformat()
    if "LETTERA" in testo and o.get("stato") in (None, "nuovo", "da_verificare"):
        o["stato"] = "lettera_preparata"
    o["prossimo_ricontatto"] = (date.today() + timedelta(days=7)).isoformat()
    return o


def main(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("dossier"); a.add_argument("--id", type=int, required=True)
    s = sub.add_parser("stato"); s.add_argument("--id", type=int, required=True); s.add_argument("--stato", required=True, choices=P.STATI)
    sub.add_parser("lista")
    args = p.parse_args(argv)
    d = P.carica()
    if args.cmd == "dossier":
        o = dossier(d, args.id)
        P.salva(d)
        print(o["dossier"])
    elif args.cmd == "stato":
        o = P.stato(d, args.id, args.stato)
        P.salva(d)
        print("id %d -> %s" % (o["id"], o["stato"]))
    elif args.cmd == "lista":
        for o in d["opportunita"]:
            print("%d | %s | %s | %s | %s" % (o["id"], o.get("stato", "nuovo"), o.get("stato_commerciale", ""), o["fonte"], o.get("titolo", "")))


if __name__ == "__main__":
    main(sys.argv[1:])
