mkdir -p /mnt/user-data/outputs/archivio && cat > /mnt/user-data/outputs/archivio/archivio.py << 'EOF'
"""
JARVIS - Archivio operativo.
File separato dal radar: non modifica radar.py né radar.yml.
Registra opportunità (immobili, attività, proprietari), con stato, fonte,
date, messaggi e controllo dei duplicati.

Uso:
  python3 archivio.py aggiungi --tipo immobile --nome "..." --zona "..." --fonte "https://..." --nota "..."
  python3 archivio.py stato --id 3 --stato contattato
  python3 archivio.py lista [--stato nuovo]
  python3 archivio.py duplicato --fonte "https://..."
"""
import argparse, json, os, sys, uuid
from datetime import datetime, date
from zoneinfo import ZoneInfo

PATH = os.environ.get("ARCHIVIO_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "archivio.json"))
STATI = ["nuovo", "da_verificare", "selezionato", "contattato", "risposta_ricevuta",
         "trattativa", "acquisito", "non_interessato"]
TIPI = ["immobile", "attivita", "proprietario", "altro"]
ORA = lambda: datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="minutes")


def carica():
    if not os.path.exists(PATH):
        return {"versione": 1, "opportunita": [], "prossimo_id": 1}
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


def salva(d):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def normalizza_fonte(fonte):
    f = (fonte or "").strip().lower().rstrip("/")
    f = f.replace("https://", "").replace("http://", "").replace("www.", "")
    return f.split("?")[0]


def trova_duplicato(d, fonte):
    chiave = normalizza_fonte(fonte)
    if not chiave:
        return None
    for o in d["opportunita"]:
        if normalizza_fonte(o.get("fonte", "")) == chiave:
            return o
    return None


def aggiungi(d, tipo, nome, zona, fonte, nota="", verificato=False):
    if tipo not in TIPI:
        raise ValueError("tipo non valido: " + tipo)
    dup = trova_duplicato(d, fonte)
    if dup:
        return dup, False
    o = {
        "id": d["prossimo_id"], "uid": uuid.uuid4().hex[:8], "tipo": tipo, "nome": nome,
        "zona": zona, "fonte": fonte, "data_verifica": date.today().isoformat(),
        "stato": "da_verificare" if not verificato else "nuovo",
        "primo_contatto": None, "prossimo_ricontatto": None,
        "messaggi": [], "note": [nota] if nota else [], "creato": ORA(),
    }
    d["prossimo_id"] += 1
    d["opportunita"].append(o)
    return o, True


def cambia_stato(d, id_, stato):
    if stato not in STATI:
        raise ValueError("stato non valido: " + stato)
    for o in d["opportunita"]:
        if o["id"] == id_:
            o["stato"] = stato
            if stato == "contattato" and not o["primo_contatto"]:
                o["primo_contatto"] = date.today().isoformat()
            return o
    raise KeyError("id non trovato: %s" % id_)


def main(argv):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("aggiungi")
    a.add_argument("--tipo", required=True, choices=TIPI)
    a.add_argument("--nome", required=True)
    a.add_argument("--zona", default="")
    a.add_argument("--fonte", required=True)
    a.add_argument("--nota", default="")
    s = sub.add_parser("stato")
    s.add_argument("--id", type=int, required=True)
    s.add_argument("--stato", required=True, choices=STATI)
    l = sub.add_parser("lista")
    l.add_argument("--stato", choices=STATI)
    dd = sub.add_parser("duplicato")
    dd.add_argument("--fonte", required=True)
    args = p.parse_args(argv)
    d = carica()
    if args.cmd == "aggiungi":
        o, nuovo = aggiungi(d, args.tipo, args.nome, args.zona, args.fonte, args.nota)
        if nuovo:
            salva(d)
            print("aggiunto id %d (stato %s)" % (o["id"], o["stato"]))
        else:
            print("gia' presente come id %d: non duplicato" % o["id"])
    elif args.cmd == "stato":
        o = cambia_stato(d, args.id, args.stato)
        salva(d)
        print("id %d -> %s" % (o["id"], o["stato"]))
    elif args.cmd == "lista":
        for o in d["opportunita"]:
            if args.stato and o["stato"] != args.stato:
                continue
            print("%d | %s | %s | %s | %s" % (o["id"], o["stato"], o["tipo"], o["nome"], o["zona"]))
    elif args.cmd == "duplicato":
        o = trova_duplicato(d, args.fonte)
        print("duplicato: id %d" % o["id"] if o else "nessun duplicato")


if __name__ == "__main__":
    main(sys.argv[1:])
EOF
cd /mnt/user-data/outputs/archivio && python3 -m py_compile archivio.py && echo SINTASSI_OK
export ARCHIVIO_PATH=/tmp/test_archivio.json; rm -f $ARCHIVIO_PATH
python3 archivio.py aggiungi --tipo immobile --nome "Bilocale Montorfano" --zona "Montorfano" --fonte "https://www.immobiliare.it/annunci/123456789/" --nota "prova"
python3 archivio.py aggiungi --tipo immobile --nome "Stesso annuncio" --zona "Montorfano" --fonte "https://immobiliare.it/annunci/123456789"
python3 archivio.py aggiungi --tipo attivita --nome "Gelateria X" --zona "Lido delle Nazioni" --fonte "https://www.facebook.com/gelateriax"
python3 archivio.py stato --id 1 --stato contattato
python3 archivio.py lista
python3 archivio.py duplicato --fonte "http://www.immobiliare.it/annunci/123456789/"
python3 archivio.py aggiungi --tipo tipo_sbagliato --nome x --fonte y 2>&1 | tail -1
unset ARCHIVIO_PATH; rm -f /tmp/test_archivio.json
cd /mnt/user-data/outputs && ls archivio/
