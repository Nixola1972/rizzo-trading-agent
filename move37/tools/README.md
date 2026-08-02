# Tool Move 37

Tre script. Il primo prepara l'incontro, il secondo lo trasforma in un documento
il giorno stesso, il terzo produce i fogli da portare in azienda.

## Installazione

```bash
pip install -r move37/tools/requirements.txt
export ANTHROPIC_API_KEY=...          # oppure: ant auth login
```

Per `verbale.py --audio` serve anche **ffmpeg** installato nel sistema.

## `dossier.py` — prima dell'incontro

```bash
python dossier.py --url https://esempio.it --nome "Esempio Srl"
python dossier.py --from-files ./pagine-salvate --nome "Esempio Srl"
```

Output in `out/<slug>/`: `dossier.md`, `dossier.json`, `ricerca-grezza.md`.

**Va lanciato in locale.** Gli ambienti remoti hanno policy di rete che bloccano i
siti cliente; la ricerca via web fallirebbe prima di partire.

`--from-files` non è un ripiego: molti siti aziendali rifiutano i crawler, e salvare
cinque pagine a mano è spesso più veloce che combattere con un WAF. In quella
modalità lo script lavora **solo** sul materiale fornito e mette in «non reperito»
tutto ciò che non c'è.

L'output è una **bozza**. Va riletta e potata prima dell'incontro: il modello tende a
essere generoso con le ipotesi, e un'ipotesi debole è peggio di nessuna ipotesi. Lo
script segnala in coda ogni fatto rimasto senza URL valido.

## `verbale.py` — dopo l'incontro

```bash
python verbale.py --audio riunione.m4a --azienda "Esempio Srl"
python verbale.py --appunti schede.md  --azienda "Esempio Srl"   # registrazione negata
python verbale.py --trascrizione r.txt --azienda "Esempio Srl"
```

Con `--dossier out/esempio/dossier.json` il lessico raccolto prima dell'incontro
viene passato al modello, così i nomi dei processi restano quelli dell'azienda.

Output: `verbale.md` e `processi.json` (i sette campi per processo, che alimentano
lo scoring e poi l'assessment).

**La trascrizione gira in locale**, con `faster-whisper`. Costa qualche minuto in più
e vale molto: permette di dire in riunione «l'audio non esce dal mio computer» — e di
dirlo essendo vero, il che è verificabile e quindi diverso da una rassicurazione.

Modelli whisper: `--whisper small` è più veloce, `large-v3` più accurato sui dialetti
e sul rumore di fabbrica. Il default `medium` è un buon compromesso.

Lo script segnala tre cose in coda, che sono i tre modi in cui la pipeline sbaglia:
sezione «cosa non faremmo» vuota, campi non rilevati senza la corrispondente domanda,
e assenza di citazioni testuali.

## `build_docx.py` — i fogli da portare

```bash
python build_docx.py --tutti                      # scheda A4 + canvas A3
python build_docx.py --solo scheda-processo
python build_docx.py --md out/esempio/verbale.md  # documento brandizzato
```

I moduli in bianco (scheda processo, canvas) sono generati da zero e pensati per
essere riempiti a penna. I documenti (dossier, verbale, offerta) sono convertiti dal
Markdown prodotto dagli altri due script.

## Note tecniche

- Modello: `claude-opus-5`. Effort regolabile con `--effort` (default `high`).
- Su `claude-opus-5` il pensiero è attivo di default e `max_tokens` limita pensiero
  **più** risposta insieme — per questo gli script usano lo streaming con budget
  ampi invece di chiamate non-streaming.
- La ricerca usa i tool server-side `web_search` e `web_fetch`: girano
  sull'infrastruttura Anthropic, non c'è niente da eseguire in locale. Il ciclo
  gestisce `pause_turn`, che è il modo in cui il server segnala di aver raggiunto il
  limite di iterazioni e di poter riprendere.
- Le credenziali si risolvono dall'ambiente: `ANTHROPIC_API_KEY`, oppure un profilo
  creato con `ant auth login`. Nessuna chiave va scritta nei file.
- La data si può forzare con `MOVE37_DATA=2026-08-05` per rigenerare un documento
  vecchio senza che ci finisca la data di oggi.
