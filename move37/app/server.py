#!/usr/bin/env python3
"""Move 37 — applicazione locale.

Si avvia con `avvia-mac.command` o `avvia-windows.bat`, oppure a mano:

    python move37/app/server.py

Apre il browser su http://127.0.0.1:8737 e resta in ascolto solo su questa
macchina: non è raggiungibile dalla rete, e l'audio delle riunioni non lascia
mai il computer perché la trascrizione gira in locale.

Usa solo la libreria standard per il web server, così l'unica cosa da
installare resta ciò che serve ai tool (anthropic, python-docx, faster-whisper).
"""

import http.server
import json
import os
import pathlib
import shutil
import socketserver
import sys
import tempfile
import threading
import traceback
import uuid
import webbrowser

APP = pathlib.Path(__file__).parent
TOOLS = APP.parent / "tools"
sys.path.insert(0, str(TOOLS))

CONFIG = pathlib.Path.home() / ".move37" / "config.json"
LAVORI = APP / "lavori"
PORTA = int(os.environ.get("MOVE37_PORTA", "8737"))

jobs = {}
_lock = threading.Lock()


# --- configurazione -------------------------------------------------------------

def leggi_config():
    if CONFIG.exists():
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def salva_config(dati):
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(dati, indent=2), encoding="utf-8")
    try:
        CONFIG.chmod(0o600)  # la chiave la legge solo l'utente
    except OSError:
        pass


def applica_chiave():
    """La chiave salvata diventa variabile d'ambiente per l'SDK Anthropic."""
    chiave = leggi_config().get("api_key", "").strip()
    if chiave:
        os.environ["ANTHROPIC_API_KEY"] = chiave
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# --- lavori in background -------------------------------------------------------

def nuovo_job(titolo):
    jid = uuid.uuid4().hex[:12]
    with _lock:
        jobs[jid] = {"stato": "in corso", "titolo": titolo, "log": [], "file": [], "errore": None}
    return jid


def log(jid, riga):
    with _lock:
        jobs[jid]["log"].append(riga)


def concludi(jid, file=None, errore=None):
    with _lock:
        jobs[jid]["stato"] = "errore" if errore else "fatto"
        jobs[jid]["errore"] = errore
        if file:
            jobs[jid]["file"] = file


def in_background(jid, funzione):
    def esegui():
        try:
            funzione()
        except SystemExit as e:  # i tool usano sys.exit per gli errori attesi
            concludi(jid, errore=str(e) or "Operazione interrotta.")
        except Exception as e:
            concludi(jid, errore=f"{type(e).__name__}: {e}")
            traceback.print_exc()

    threading.Thread(target=esegui, daemon=True).start()


def cartella_job(jid):
    d = LAVORI / jid
    d.mkdir(parents=True, exist_ok=True)
    return d


def elenco_file(d):
    return sorted(p.name for p in d.iterdir() if p.is_file())


# --- le tre operazioni ----------------------------------------------------------

def fai_verbale(jid, azienda, data, presenti, testo, audio, effort, whisper):
    import _common as c
    import verbale as V

    d = cartella_job(jid)
    if audio:
        log(jid, f"Trascrizione locale di {audio.name} (modello {whisper}) — richiede qualche minuto.")
        log(jid, "L'audio non lascia questo computer.")
        testo = V.trascrivi(str(audio), whisper)
        (d / "trascrizione.txt").write_text(testo, encoding="utf-8")
        log(jid, f"Trascritti {len(testo.split())} parole circa.")

    if not testo.strip():
        raise SystemExit("Nessun contenuto da elaborare: manca l'audio o il testo.")

    intestazione = [f"Azienda: {azienda}", f"Data dell'incontro: {data}"]
    if presenti:
        intestazione.append(f"Presenti: {presenti}")
    intestazione.append(
        "Origine del materiale: " + ("registrazione" if audio else "appunti o trascrizione")
    )

    log(jid, "Costruzione del verbale strutturato…")
    v = c.structure(
        c.client(),
        c.prompt("verbale"),
        "\n".join(intestazione) + f"\n\n--- MATERIALE ---\n\n{testo}",
        V.SCHEMA,
        effort=effort,
    )

    md = V.render(v)
    (d / "verbale.md").write_text(md, encoding="utf-8")
    (d / "processi.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        import build_docx

        build_docx.markdown(d / "verbale.md", d / "verbale.docx")
    except Exception as e:
        log(jid, f"DOCX non generato ({e}). Il Markdown c'è comunque.")

    if audio:
        # L'audio caricato può pesare centinaia di MB: la trascrizione è salvata,
        # l'originale resta dove l'utente ce l'ha già.
        shutil.rmtree(audio.parent, ignore_errors=True)

    for a in V.controlli(v):
        log(jid, "ATTENZIONE — " + a)
    log(jid, "Rileggilo cinque minuti prima di mandarlo.")
    concludi(jid, elenco_file(d))


def fai_dossier(jid, nome, url, materiale, effort):
    import _common as c
    import dossier as D

    d = cartella_job(jid)
    contesto = "\n".join(f"- {k}: {v}" for k, v in [("Nome", nome), ("Sito", url)] if v)
    cli = c.client()

    if url:
        log(jid, f"Ricerca su fonti pubbliche a partire da {url} — qualche minuto.")
        grezzo = c.research(
            cli,
            f"Prepara la ricerca per un primo incontro con questa azienda.\n\n{contesto}\n\n"
            "Parti dal sito e allarga alle altre fonti pubbliche. Cita l'URL di ogni cosa.",
            effort=effort,
        )
    else:
        log(jid, "Lettura del materiale caricato…")
        with cli.messages.stream(
            model=c.MODEL,
            max_tokens=32000,
            system=c.prompt("dossier"),
            output_config={"effort": effort},
            messages=[
                {
                    "role": "user",
                    "content": f"Usa SOLO il materiale allegato — quello che non c'è va in "
                    f"«non reperito».\n\n{contesto}\n\n--- MATERIALE ---\n\n{materiale}",
                }
            ],
        ) as s:
            r = s.get_final_message()
        c.check_refusal(r, "la lettura del materiale")
        grezzo = c.text_of(r)

    log(jid, "Strutturazione…")
    dati = c.structure(cli, D.STRUTTURA, grezzo, D.SCHEMA, effort=effort)
    md = D.render(dati, c.oggi())

    (d / "dossier.md").write_text(md, encoding="utf-8")
    (d / "dossier.json").write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "ricerca-grezza.md").write_text(grezzo, encoding="utf-8")

    try:
        import build_docx

        build_docx.markdown(d / "dossier.md", d / "dossier.docx")
    except Exception as e:
        log(jid, f"DOCX non generato ({e}).")

    senza = [f["fatto"] for f in dati["fatti"] if not f["url"].startswith("http")]
    for f in senza:
        log(jid, f"ATTENZIONE — fatto senza URL verificabile: {f}")
    log(jid, "È una bozza: va riletta e potata. Le ipotesi deboli si tolgono.")
    concludi(jid, elenco_file(d))


def fai_stampabili(jid):
    import build_docx

    d = cartella_job(jid)
    build_docx.scheda_processo(d / "scheda-processo-A4.docx")
    build_docx.canvas(d / "canvas-mappa-processi-A3.docx")
    log(jid, "Stampa la scheda A4 in 5-6 copie, una per processo.")
    log(jid, "Il canvas A3 serve solo se il cliente non sa da dove partire.")
    concludi(jid, elenco_file(d))


# --- HTTP -----------------------------------------------------------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # niente rumore in console

    def _invia(self, codice, corpo, tipo="application/json; charset=utf-8"):
        dati = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(codice)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)

    def _corpo(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        percorso = self.path.split("?")[0]

        if percorso in ("/", "/index.html"):
            return self._invia(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")

        if percorso == "/api/stato":
            return self._invia(200, {"chiave": applica_chiave(), "whisper": _whisper_disponibile()})

        if percorso.startswith("/api/job/"):
            jid = percorso.rsplit("/", 1)[-1]
            with _lock:
                j = jobs.get(jid)
            return self._invia(200, j) if j else self._invia(404, {"errore": "lavoro sconosciuto"})

        if percorso.startswith("/api/file/"):
            _, _, _, jid, nome = percorso.split("/", 4)
            f = (LAVORI / jid / pathlib.Path(nome).name).resolve()
            if not f.is_file() or LAVORI.resolve() not in f.parents:
                return self._invia(404, {"errore": "file non trovato"})
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
            self.send_header("Content-Length", str(f.stat().st_size))
            self.end_headers()
            self.wfile.write(f.read_bytes())
            return

        self._invia(404, {"errore": "non trovato"})

    def do_POST(self):
        percorso = self.path.split("?")[0]

        if percorso == "/api/chiave":
            dati = json.loads(self._corpo() or b"{}")
            cfg = leggi_config()
            cfg["api_key"] = dati.get("api_key", "").strip()
            salva_config(cfg)
            return self._invia(200, {"chiave": applica_chiave()})

        if percorso == "/api/carica":
            # File binario grezzo: il nome arriva nell'header, così non serve
            # gestire il multipart a mano.
            nome = pathlib.Path(self.headers.get("X-Filename", "file")).name
            d = pathlib.Path(tempfile.mkdtemp(prefix="move37-"))
            (d / nome).write_bytes(self._corpo())
            return self._invia(200, {"percorso": str(d / nome), "nome": nome})

        if percorso == "/api/stampabili":
            jid = nuovo_job("Stampabili")
            in_background(jid, lambda: fai_stampabili(jid))
            return self._invia(200, {"job": jid})

        dati = json.loads(self._corpo() or b"{}")

        if percorso == "/api/verbale":
            if not applica_chiave():
                return self._invia(400, {"errore": "Manca la chiave API: impostala in alto."})
            audio = dati.get("audio")
            jid = nuovo_job("Verbale")
            in_background(
                jid,
                lambda: fai_verbale(
                    jid,
                    dati.get("azienda", "").strip() or "Azienda",
                    dati.get("data", "").strip() or _oggi(),
                    dati.get("presenti", "").strip(),
                    dati.get("testo", ""),
                    pathlib.Path(audio) if audio else None,
                    dati.get("effort", "high"),
                    dati.get("whisper", "medium"),
                ),
            )
            return self._invia(200, {"job": jid})

        if percorso == "/api/dossier":
            if not applica_chiave():
                return self._invia(400, {"errore": "Manca la chiave API: impostala in alto."})
            jid = nuovo_job("Dossier")
            in_background(
                jid,
                lambda: fai_dossier(
                    jid,
                    dati.get("nome", "").strip(),
                    dati.get("url", "").strip(),
                    dati.get("materiale", ""),
                    dati.get("effort", "high"),
                ),
            )
            return self._invia(200, {"job": jid})

        self._invia(404, {"errore": "non trovato"})


def _oggi():
    import _common as c

    return c.oggi()


def _whisper_disponibile():
    try:
        import faster_whisper  # noqa: F401

        return bool(shutil.which("ffmpeg"))
    except ImportError:
        return False


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    LAVORI.mkdir(parents=True, exist_ok=True)
    applica_chiave()
    indirizzo = f"http://127.0.0.1:{PORTA}"

    print(f"\n  Move 37 — in ascolto su {indirizzo}")
    print("  Solo su questo computer: non è raggiungibile dalla rete.")
    if not _whisper_disponibile():
        print("\n  Trascrizione automatica non disponibile (manca faster-whisper o ffmpeg).")
        print("  Puoi comunque incollare appunti o una trascrizione già pronta.")
    print("\n  Per chiudere: Ctrl-C in questa finestra.\n")

    threading.Timer(1.0, lambda: webbrowser.open(indirizzo)).start()
    try:
        with Server(("127.0.0.1", PORTA), Handler) as srv:
            srv.serve_forever()
    except KeyboardInterrupt:
        print("  Chiuso.")
    except OSError as e:
        sys.exit(
            f"\n  Impossibile aprire la porta {PORTA}: {e}\n"
            f"  Probabilmente Move 37 è già avviato in un'altra finestra.\n"
        )


if __name__ == "__main__":
    main()
