#!/usr/bin/env python3
"""Verbale post-incontro Move 37 — il pezzo che regge tutto il metodo.

    python verbale.py --audio riunione.m4a  --azienda "Esempio Srl"
    python verbale.py --trascrizione r.txt  --azienda "Esempio Srl"
    python verbale.py --appunti schede.md   --azienda "Esempio Srl"

La trascrizione gira **in locale** con faster-whisper. Costa qualche minuto in più
e vale molto: permette di dire in riunione «l'audio non esce dal mio computer» —
e di dirlo essendo vero, il che è verificabile e quindi diverso da una
rassicurazione.

La modalità --appunti esiste perché il consenso alla registrazione può essere
negato, e il metodo deve reggere lo stesso.
"""

import argparse
import json
import sys

import _common as c

NON_RILEVATO = "non rilevato"

_CAMPO = {"type": "string", "description": f"Se non è emerso in riunione: «{NON_RILEVATO}»."}

SCHEMA = {
    "type": "object",
    "properties": {
        "azienda": {"type": "string"},
        "data": {"type": "string"},
        "presenti": {"type": "array", "items": {"type": "string"}},
        "processi": {
            "type": "array",
            "description": "Nell'ordine in cui il cliente li ha nominati, con le sue parole.",
            "items": {
                "type": "object",
                "properties": {
                    "nome": {
                        "type": "string",
                        "description": "Il nome che usa il cliente. Mai tradotto o normalizzato.",
                    },
                    "citazioni": {
                        "type": "array",
                        "description": "Frasi testuali, non ripulite.",
                        "items": {"type": "string"},
                    },
                    "volume": _CAMPO,
                    "chi_e_quanto": _CAMPO,
                    "dati": _CAMPO,
                    "quando_va_storto": _CAMPO,
                    "chi_si_lamenta": _CAMPO,
                    "gia_provato": _CAMPO,
                    "decide_si_oppone": _CAMPO,
                    "lead_time": _CAMPO,
                    "touch_time": _CAMPO,
                },
                "required": [
                    "nome",
                    "citazioni",
                    "volume",
                    "chi_e_quanto",
                    "dati",
                    "quando_va_storto",
                    "chi_si_lamenta",
                    "gia_provato",
                    "decide_si_oppone",
                    "lead_time",
                    "touch_time",
                ],
                "additionalProperties": False,
            },
        },
        "cosa_ci_serve": {
            "type": "array",
            "description": "I campi non rilevati, riformulati come domande dirette.",
            "items": {"type": "string"},
        },
        "lettura": {
            "type": "object",
            "description": "Sezione nostra, separata dal resoconto. Mai fusa con esso.",
            "properties": {
                "da_dove_partire": {"type": "string"},
                "perche": {"type": "string"},
                "perche_non_il_piu_urgente": {"type": "string"},
                "ordine": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "processo": {"type": "string"},
                            "ore_mese": {
                                "type": "string",
                                "description": "Banda arrotondata per difetto, dai numeri del cliente.",
                            },
                            "fattibilita": {"type": "string"},
                            "note": {"type": "string"},
                        },
                        "required": ["processo", "ore_mese", "fattibilita", "note"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["da_dove_partire", "perche", "perche_non_il_piu_urgente", "ordine"],
            "additionalProperties": False,
        },
        "roadmap": {
            "type": "array",
            "description": "Novanta giorni, tre tappe, con cosa si vede alla fine di ciascuna.",
            "items": {
                "type": "object",
                "properties": {
                    "tappa": {"type": "string"},
                    "cosa_si_vede": {"type": "string"},
                },
                "required": ["tappa", "cosa_si_vede"],
                "additionalProperties": False,
            },
        },
        "cosa_non_faremmo": {
            "type": "array",
            "description": "Almeno una cosa vera che il cliente potrebbe volere. Mai vuota.",
            "items": {
                "type": "object",
                "properties": {
                    "cosa": {"type": "string"},
                    "perche": {"type": "string"},
                },
                "required": ["cosa", "perche"],
                "additionalProperties": False,
            },
        },
        "prossimo_passo": {
            "type": "object",
            "properties": {
                "azione": {"type": "string"},
                "data": {"type": "string"},
            },
            "required": ["azione", "data"],
            "additionalProperties": False,
        },
    },
    "required": [
        "azienda",
        "data",
        "presenti",
        "processi",
        "cosa_ci_serve",
        "lettura",
        "roadmap",
        "cosa_non_faremmo",
        "prossimo_passo",
    ],
    "additionalProperties": False,
}


def trascrivi(percorso, modello="medium"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit(
            "Per la trascrizione locale serve faster-whisper:\n"
            "  pip install -r requirements.txt\n"
            "In alternativa trascrivi altrove e usa --trascrizione."
        )
    print(f"Trascrizione locale con faster-whisper ({modello}) …", file=sys.stderr)
    m = WhisperModel(modello, device="auto", compute_type="int8")
    segmenti, _ = m.transcribe(percorso, language="it", vad_filter=True)
    return "\n".join(s.text.strip() for s in segmenti)


def render(v):
    r = [
        f"# {v['azienda']} — Incontro del {v['data']}",
        "",
        f"*Presenti: {', '.join(v['presenti']) if v['presenti'] else 'non rilevato'}*",
        "",
        "## 1. Cosa ci siete detti",
        "",
        "*I processi nell'ordine in cui li avete nominati, con le vostre parole.*",
        "",
    ]

    etichette = [
        ("volume", "Volume"),
        ("chi_e_quanto", "Chi ci lavora"),
        ("dati", "Dove stanno i dati"),
        ("quando_va_storto", "Quando va storto"),
        ("chi_si_lamenta", "Chi se ne lamenta"),
        ("gia_provato", "Già provato"),
        ("decide_si_oppone", "Decide / si oppone"),
        ("lead_time", "Lead time"),
        ("touch_time", "Lavoro vero"),
    ]

    for i, p in enumerate(v["processi"], 1):
        r += [f"### 1.{i} {p['nome']}", ""]
        for q in p["citazioni"]:
            r += [f"> «{q}»", ""]
        r += ["| | |", "|---|---|"]
        r += [f"| {lab} | {p[k]} |" for k, lab in etichette]
        r.append("")

    if v["cosa_ci_serve"]:
        r += ["## 2. Cosa ci serve da voi", ""]
        r += [f"- [ ] {x}" for x in v["cosa_ci_serve"]]
        r.append("")

    lt = v["lettura"]
    r += [
        "## 3. La nostra lettura",
        "",
        "> Questa sezione è nostra: sono valutazioni, non cose che ci avete detto.",
        "",
        f"**Da dove partiremmo:** {lt['da_dove_partire']}",
        "",
        lt["perche"],
        "",
        f"**Perché non dal più urgente:** {lt['perche_non_il_piu_urgente']}",
        "",
        "| Processo | Ore/mese stimate | Fattibilità | Note |",
        "|---|---|---|---|",
    ]
    r += [
        f"| {o['processo']} | {o['ore_mese']} | {o['fattibilita']} | {o['note']} |"
        for o in lt["ordine"]
    ]
    r += [
        "",
        "*Stime a partire dai numeri che ci avete dato voi, arrotondate per difetto.*",
        "",
        "## 4. Come procederemmo",
        "",
    ]
    for i, t in enumerate(v["roadmap"], 1):
        r.append(f"{i}. **{t['tappa']}** — alla fine si vede: {t['cosa_si_vede']}")

    r += ["", "## 5. Cosa non faremmo", ""]
    for x in v["cosa_non_faremmo"]:
        r.append(f"- **{x['cosa']}** — {x['perche']}")

    r += [
        "",
        "## 6. Prossimo passo",
        "",
        f"{v['prossimo_passo']['azione']} — entro il **{v['prossimo_passo']['data']}**.",
    ]
    return "\n".join(r)


def controlli(v):
    """I tre modi in cui la pipeline sbaglia più spesso."""
    avvisi = []
    if not v["cosa_non_faremmo"]:
        avvisi.append("Sezione «cosa non faremmo» vuota: il verbale non è finito.")
    vuoti = sum(
        1
        for p in v["processi"]
        for k, x in p.items()
        if isinstance(x, str) and x.strip().lower() == NON_RILEVATO
    )
    if vuoti and len(v["cosa_ci_serve"]) < vuoti:
        avvisi.append(
            f"{vuoti} campi «non rilevato» ma solo {len(v['cosa_ci_serve'])} domande "
            "in «cosa ci serve da voi»: controllare che non siano stati colmati a stima."
        )
    muti = [p["nome"] for p in v["processi"] if not p["citazioni"]]
    if muti:
        avvisi.append(
            "Nessuna citazione testuale per: "
            + ", ".join(muti)
            + ". Un processo che nessuno ha citato è un processo che non è stato esplorato."
        )
    return avvisi


def main():
    ap = argparse.ArgumentParser(description="Verbale post-incontro Move 37")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--audio", help="Registrazione (trascritta in locale)")
    src.add_argument("--trascrizione", help="Trascrizione già pronta")
    src.add_argument("--appunti", help="Solo appunti — se la registrazione è stata negata")
    ap.add_argument("--azienda", required=True)
    ap.add_argument("--data", default=None, help="Data dell'incontro (default: oggi)")
    ap.add_argument("--presenti", default="", help="Nomi e ruoli, separati da virgola")
    ap.add_argument("--dossier", help="dossier.json del pre-incontro, come contesto")
    ap.add_argument("--out", default="out")
    ap.add_argument("--model", default=c.MODEL)
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--whisper", default="medium", help="Modello faster-whisper (default: medium)")
    a = ap.parse_args()

    if a.audio:
        testo = trascrivi(a.audio, a.whisper)
        origine = "trascrizione della registrazione"
    elif a.trascrizione:
        testo = open(a.trascrizione, encoding="utf-8").read()
        origine = "trascrizione"
    else:
        testo = open(a.appunti, encoding="utf-8").read()
        origine = "appunti presi a mano (nessuna registrazione)"

    data = a.data or c.oggi()
    intestazione = [
        f"Azienda: {a.azienda}",
        f"Data dell'incontro: {data}",
        f"Origine del materiale: {origine}",
    ]
    if a.presenti:
        intestazione.append(f"Presenti: {a.presenti}")
    if a.dossier:
        d = json.load(open(a.dossier, encoding="utf-8"))
        if d.get("lessico"):
            intestazione.append("Lessico dell'azienda da rispettare: " + ", ".join(d["lessico"]))

    contenuto = "\n".join(intestazione) + f"\n\n--- MATERIALE ---\n\n{testo}"

    print("Costruzione del verbale …", file=sys.stderr)
    cli = c.client()
    v = c.structure(
        cli, c.prompt("verbale"), contenuto, SCHEMA, model=a.model, effort=a.effort
    )

    dest = f"{a.out}/{c.slug(a.azienda)}"
    p_md = c.scrivi(dest, "verbale.md", render(v))
    c.scrivi(dest, "processi.json", json.dumps(v, ensure_ascii=False, indent=2))
    if a.audio:
        c.scrivi(dest, "trascrizione.txt", testo)

    print(f"\n{p_md}", file=sys.stderr)
    print("  processi.json → alimenta lo scoring e poi l'assessment", file=sys.stderr)
    for w in controlli(v):
        print(f"\n⚠  {w}", file=sys.stderr)
    print(
        "\nRileggere cinque minuti prima di mandarlo: controllare che i nomi dei processi\n"
        "siano quelli del cliente, che ogni numero sia stato detto in riunione, e che nella\n"
        "sezione 1 non sia finita nessuna nostra valutazione.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
