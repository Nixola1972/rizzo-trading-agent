#!/usr/bin/env python3
"""Genera la bozza di dossier pre-incontro Move 37.

    python dossier.py --url https://esempio.it --nome "Esempio Srl"
    python dossier.py --from-files ./pagine-salvate --nome "Esempio Srl"

Va lanciato **in locale**: gli ambienti remoti hanno policy di rete che bloccano
i siti cliente. La modalità --from-files non è un ripiego — molti siti aziendali
rifiutano i crawler, e salvare cinque pagine a mano è spesso più veloce.

L'output è una bozza, non un dossier. Va riletto e potato: il modello tende a
essere generoso con le ipotesi, e un'ipotesi debole è peggio di nessuna ipotesi.

Ricorda a cosa serve: NON si presenta al cliente in apertura. Serve a fare
domande di secondo livello invece di chiedere «di cosa vi occupate».
"""

import argparse
import json
import sys

import _common as c

SCHEMA = {
    "type": "object",
    "properties": {
        "azienda": {"type": "string"},
        "profilo": {
            "type": "string",
            "description": "Tre-quattro righe: cosa fanno, per chi, con che dimensione. Nel loro lessico.",
        },
        "lessico": {
            "type": "array",
            "description": "I termini che usano loro e che vanno riusati in riunione e nel verbale.",
            "items": {"type": "string"},
        },
        "fatti": {
            "type": "array",
            "description": "Massimo cinque. Ognuno con URL sorgente. Nessuna eccezione.",
            "items": {
                "type": "object",
                "properties": {
                    "fatto": {"type": "string"},
                    "fonte": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["fatto", "fonte", "url"],
                "additionalProperties": False,
            },
        },
        "non_reperito": {
            "type": "array",
            "description": "Cosa si è cercato senza trovarlo. Serve a sapere cosa chiedere.",
            "items": {"type": "string"},
        },
        "ipotesi": {
            "type": "array",
            "description": "Ipotesi di attrito, ognuna con l'indizio concreto da cui nasce.",
            "items": {
                "type": "object",
                "properties": {
                    "ipotesi": {"type": "string"},
                    "indizio": {"type": "string"},
                },
                "required": ["ipotesi", "indizio"],
                "additionalProperties": False,
            },
        },
        "domande": {
            "type": "array",
            "description": "Domande a cui solo loro possono rispondere.",
            "items": {"type": "string"},
        },
        "demo": {
            "type": "array",
            "description": "Cose fattibili dal vivo in dieci minuti sul loro materiale.",
            "items": {
                "type": "object",
                "properties": {
                    "titolo": {"type": "string"},
                    "materiale_necessario": {"type": "string"},
                },
                "required": ["titolo", "materiale_necessario"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "azienda",
        "profilo",
        "lessico",
        "fatti",
        "non_reperito",
        "ipotesi",
        "domande",
        "demo",
    ],
    "additionalProperties": False,
}

STRUTTURA = """Riorganizza la ricerca qui sotto nel formato richiesto.

Regole invariabili:
- Ogni fatto ha un URL. Se un dato non ha fonte, non è un fatto: va in `non_reperito`.
- Non inventare nulla che non sia nel testo. In particolare nessun numero.
- Le ipotesi restano ipotesi: ognuna con il suo indizio verificabile. Se l'indizio è
  debole, ometti l'ipotesi.
- Nel campo `lessico` metti i termini dell'azienda, non i tuoi sinonimi.
- Nessun giudizio sull'organizzazione o sul ritardo digitale dell'azienda."""


def render(d, data):
    r = [
        f"# Dossier pre-incontro — {d['azienda']}",
        "",
        f"*Preparato il {data} · Fonti con URL: {len(d['fatti'])}*",
        "",
        "> **Questo documento serve a me, non al cliente.** Non si presenta in apertura:",
        "> impone la mia cornice prima che lui abbia parlato. Una frase da dieci secondi",
        "> («ho guardato il sito prima di venire, ma parta lei»), poi resta in cartella.",
        "",
        "## Chi sono",
        "",
        d["profilo"],
        "",
    ]

    if d["lessico"]:
        r += [
            "**Le loro parole** (da riusare in riunione e nel verbale): "
            + ", ".join(f"*{t}*" for t in d["lessico"]),
            "",
        ]

    r += ["## Cinque fatti verificati", ""]
    for i, f in enumerate(d["fatti"], 1):
        r.append(f"{i}. {f['fatto']}  \n   — {f['fonte']}: {f['url']}")
    r.append("")

    if d["non_reperito"]:
        r += ["**Non reperito** (cercato, non trovato → da chiedere):", ""]
        r += [f"- {x}" for x in d["non_reperito"]]
        r.append("")

    r += [
        "## Ipotesi di attrito",
        "",
        "> ⚠️ **Sono ipotesi, non conclusioni.** Presentate come conclusioni sono un errore",
        "> che il cliente perdona una volta sola.",
        "",
    ]
    for i, h in enumerate(d["ipotesi"], 1):
        r.append(f"{i}. **{h['ipotesi']}**  \n   Perché lo penso: {h['indizio']}")
    r.append("")

    r += ["## Domande a cui solo loro possono rispondere", ""]
    r += [f"{i}. {q}" for i, q in enumerate(d["domande"], 1)]
    r.append("")

    r += ["## Idee di demo dal vivo", ""]
    for i, dm in enumerate(d["demo"], 1):
        r.append(f"{i}. **{dm['titolo']}**  \n   Serve avere in mano: {dm['materiale_necessario']}")
    r += [
        "",
        "---",
        "",
        "*Bozza generata automaticamente. Va riletta e potata prima dell'incontro:*",
        "*le ipotesi deboli si tolgono, e ogni numero senza fonte va verificato o cancellato.*",
    ]
    return "\n".join(r)


def main():
    ap = argparse.ArgumentParser(description="Dossier pre-incontro Move 37")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--url", help="Sito del cliente (richiede rete aperta: usare in locale)")
    src.add_argument("--from-files", metavar="DIR", help="Cartella con pagine già salvate")
    ap.add_argument("--nome", help="Ragione sociale, se nota")
    ap.add_argument("--piva", help="Partita IVA, se nota")
    ap.add_argument("--settore", help="Settore, se noto")
    ap.add_argument("--out", default="out", help="Cartella di output (default: out)")
    ap.add_argument("--model", default=c.MODEL)
    ap.add_argument(
        "--effort",
        default="high",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="Profondità del lavoro (default: high)",
    )
    a = ap.parse_args()

    cli = c.client()
    contesto = "\n".join(
        f"- {k}: {v}"
        for k, v in [
            ("Nome", a.nome),
            ("Sito", a.url),
            ("P.IVA", a.piva),
            ("Settore", a.settore),
        ]
        if v
    )

    if a.url:
        print(f"Ricerca su fonti pubbliche a partire da {a.url} …", file=sys.stderr)
        grezzo = c.research(
            cli,
            f"Prepara la ricerca per un primo incontro con questa azienda.\n\n{contesto}\n\n"
            "Parti dal sito e allarga alle altre fonti pubbliche indicate nelle istruzioni. "
            "Cita l'URL di ogni cosa che trovi.",
            model=a.model,
            effort=a.effort,
        )
    else:
        print(f"Lettura di {a.from_files} …", file=sys.stderr)
        materiale = c.leggi_cartella(a.from_files)
        with cli.messages.stream(
            model=a.model,
            max_tokens=32000,
            system=c.prompt("dossier"),
            output_config={"effort": a.effort},
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Prepara la ricerca per un primo incontro con questa azienda, "
                        f"usando SOLO il materiale allegato — non hai accesso alla rete, "
                        f"quindi ciò che non è nel materiale va in «non reperito».\n\n"
                        f"{contesto}\n\n--- MATERIALE ---\n\n{materiale}"
                    ),
                }
            ],
        ) as stream:
            resp = stream.get_final_message()
        c.check_refusal(resp, "la lettura del materiale")
        grezzo = c.text_of(resp)

    print("Strutturazione …", file=sys.stderr)
    dati = c.structure(cli, STRUTTURA, grezzo, SCHEMA, model=a.model, effort=a.effort)

    data = c.oggi()
    dest = f"{a.out}/{c.slug(a.nome or dati['azienda'])}"
    p_md = c.scrivi(dest, "dossier.md", render(dati, data))
    c.scrivi(dest, "dossier.json", json.dumps(dati, ensure_ascii=False, indent=2))
    c.scrivi(dest, "ricerca-grezza.md", grezzo)

    senza_url = [f["fatto"] for f in dati["fatti"] if not f["url"].startswith("http")]
    print(f"\n{p_md}", file=sys.stderr)
    if senza_url:
        print(
            f"\n⚠  {len(senza_url)} fatti senza URL valido — verificarli o toglierli:",
            file=sys.stderr,
        )
        for f in senza_url:
            print(f"   · {f}", file=sys.stderr)


if __name__ == "__main__":
    main()
