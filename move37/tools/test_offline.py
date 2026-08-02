#!/usr/bin/env python3
"""Verifica offline dei tool Move 37: schemi, rendering, controlli.

    python test_offline.py

Copre tutto tranne la chiamata al modello, quindi gira senza credenziali API.
Serve a intercettare le tre regressioni che contano davvero:

  · uno schema che gli structured outputs rifiuterebbero;
  · un verbale in cui la nostra lettura sconfina nel resoconto;
  · un controllo di qualità che smette di scattare.
"""

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import _common as c
import dossier
import verbale

errori = []


def valida_schema(nome, s, percorso="root"):
    """Le regole degli structured outputs: `additionalProperties: false` su ogni
    oggetto, e `required` che elenca esattamente le properties."""
    if s.get("type") == "object":
        if s.get("additionalProperties") is not False:
            errori.append(f"{nome}:{percorso} manca additionalProperties:false")
        props, req = set(s.get("properties", {})), set(s.get("required", []))
        if props != req:
            errori.append(f"{nome}:{percorso} required≠properties (manca {props - req})")
        for k, v in s.get("properties", {}).items():
            valida_schema(nome, v, f"{percorso}.{k}")
    elif s.get("type") == "array":
        valida_schema(nome, s.get("items", {}), f"{percorso}[]")


NR = verbale.NON_RILEVATO

DOSSIER = {
    "azienda": "Metallurgica Prova Srl",
    "profilo": "Carpenteria su commessa, 34 addetti, ISO 9001.",
    "lessico": ["commessa", "bolla", "rapportino"],
    "fatti": [
        {"fatto": "34 addetti da bilancio 2024", "fonte": "Registro Imprese", "url": "https://esempio.it/a"},
        {"fatto": "Cercano un impiegato ufficio tecnico", "fonte": "Annuncio", "url": "https://esempio.it/b"},
        {"fatto": "Dato senza fonte valida", "fonte": "ignota", "url": "n/d"},
    ],
    "non_reperito": ["Fatturato 2025"],
    "ipotesi": [
        {"ipotesi": "Preventivazione lenta", "indizio": "L'annuncio cita «gestione commesse e offerte»"}
    ],
    "domande": ["Chi fa i preventivi oggi?"],
    "demo": [{"titolo": "Requisiti da capitolato", "materiale_necessario": "un capitolato cliente vero"}],
}

# Tre difetti piantati di proposito: nessun «cosa non faremmo», molti campi non
# rilevati con una sola domanda, e un processo senza citazioni.
VERBALE = {
    "azienda": "Metallurgica Prova Srl",
    "data": "2026-08-05",
    "presenti": ["Titolare", "Resp. produzione"],
    "processi": [
        {
            "nome": "preventivazione",
            "citazioni": ["ci mettiamo tre giorni a fare un preventivo che poi il cliente manco legge"],
            "volume": "circa 40 al mese",
            "chi_e_quanto": "Mario, 2 ore l'uno",
            "dati": "Excel sul suo desktop",
            "quando_va_storto": "se ne accorgono dal cliente",
            "chi_si_lamenta": "il cliente",
            "gia_provato": NR,
            "decide_si_oppone": "decide il titolare",
            "lead_time": "3 giorni",
            "touch_time": "2 ore",
        },
        {
            "nome": "registrazione qualità",
            "citazioni": [],
            "volume": NR,
            "chi_e_quanto": NR,
            "dati": "moduli cartacei",
            "quando_va_storto": NR,
            "chi_si_lamenta": "il capo",
            "gia_provato": NR,
            "decide_si_oppone": NR,
            "lead_time": NR,
            "touch_time": NR,
        },
    ],
    "cosa_ci_serve": ["Quante non conformità l'anno?"],
    "lettura": {
        "da_dove_partire": "preventivazione",
        "perche": "i dati esistono già e il processo è stabile.",
        "perche_non_il_piu_urgente": "la qualità è più grave, ma i dati sono su carta.",
        "ordine": [
            {"processo": "preventivazione", "ore_mese": "fra 50 e 70", "fattibilita": "alta", "note": "—"}
        ],
    },
    "roadmap": [{"tappa": "Assessment", "cosa_si_vede": "mappa e business case"}],
    "cosa_non_faremmo": [],
    "prossimo_passo": {"azione": "Proposta di assessment", "data": "12 agosto"},
}


def main():
    valida_schema("dossier", dossier.SCHEMA)
    valida_schema("verbale", verbale.SCHEMA)
    print("1. Schemi JSON:", "OK" if not errori else "PROBLEMI")
    for e in errori:
        print("   ·", e)

    md = dossier.render(DOSSIER, "2026-08-05")
    assert "serve a me, non al cliente" in md, "manca l'avvertenza sull'uso del dossier"
    assert "*commessa*" in md, "il lessico del cliente non compare"
    assert "https://esempio.it/a" in md, "URL delle fonti perso"
    print(f"2. Rendering dossier: OK ({len(md.splitlines())} righe)")

    md_v = verbale.render(VERBALE)
    i1, i3 = md_v.index("## 1."), md_v.index("## 3.")
    assert "«ci mettiamo tre giorni" in md_v, "citazione testuale persa"
    assert "preventivazione" in md_v[i1:i3], "il nome del cliente non è nel resoconto"
    assert "Questa sezione è nostra" in md_v[i3:], "manca la separazione della nostra lettura"
    assert "da_dove_partire" not in md_v, "chiave grezza finita nel documento"
    print(f"3. Rendering verbale: OK ({len(md_v.splitlines())} righe, sezioni 1 e 3 separate)")

    avvisi = verbale.controlli(VERBALE)
    attesi = ["cosa non faremmo", "non rilevato", "citazione"]
    mancanti = [a for a in attesi if not any(a in w.lower() for w in avvisi)]
    assert not mancanti, f"controlli non scattati: {mancanti}"
    print(f"4. Controlli: OK — {len(avvisi)}/3 difetti rilevati")
    for w in avvisi:
        print("   ⚠", w)

    with tempfile.TemporaryDirectory() as d:
        c.scrivi(d, "dossier.md", md)
        c.scrivi(d, "verbale.md", md_v)
        c.scrivi(d, "processi.json", json.dumps(VERBALE, ensure_ascii=False, indent=2))
        n = len(list(pathlib.Path(d).iterdir()))
    assert c.slug("Metallurgica Prova S.r.l.") == "metallurgica-prova-s-r-l"
    print(f"5. Scrittura e slug: OK ({n} file)")

    if errori:
        sys.exit(1)
    print("\nTutto verde. Resta da provare con credenziali API la chiamata al modello.")


if __name__ == "__main__":
    main()
