# Move 37 — Kit di ingaggio cliente

Materiale operativo per il primo incontro con un'azienda: come prepararlo, come condurlo, cosa lasciare dopo.

**Non è una piattaforma.** Non c'è niente da installare in azienda, nessun server, nessun login, nessun abbonamento. Sono documenti da leggere e un'applicazione che gira sul tuo portatile.

---

## Come si usa, in pratica

### Per l'incontro ti basta la carta

Il metodo funziona con carta e penna. Prima di andare:

1. **Stampa la scheda processo A4** in 5-6 copie, una per processo
2. **Leggi `03-conduzione-incontro.md`** — venti minuti, è lo script della riunione
3. **Prepara il registratore** e la frase per chiedere il consenso

Basta questo. L'applicazione è un acceleratore, non un requisito.

### L'applicazione

Fa tre cose: prepara il dossier prima dell'incontro, produce il verbale dopo, e stampa i fogli.

- **Mac** → doppio clic su `avvia-mac.command`
- **Windows** → doppio clic su `avvia-windows.bat`

Si apre il browser e sei dentro. La prima volta impiega qualche minuto perché scarica quello che serve; dalle volte successive parte in pochi secondi.

Ti serve una **chiave API** da `console.anthropic.com`: si incolla una volta sola nel riquadro in alto e resta salvata sul tuo computer. Si paga a consumo, pochi centesimi a documento, senza abbonamento.

Per la trascrizione automatica dell'audio serve anche **ffmpeg** (`brew install ffmpeg` su Mac, `winget install ffmpeg` su Windows). Senza, l'app funziona lo stesso: incolli gli appunti invece di caricare la registrazione.

**Gira solo sul tuo computer.** Non è raggiungibile dalla rete, e la trascrizione avviene in locale: l'audio della riunione non lascia il portatile. È il motivo per cui puoi dirlo al cliente essendo vero.

Chi preferisce il terminale trova gli stessi tre strumenti in `tools/` — vedi `tools/README.md`.

---

## La regola che viene prima di tutte le altre

> **Se il cliente ha già un'agenda, il kit resta in cartella.**

Questa riga è in testa a ogni documento. Il materiale serve a non dimenticare niente, non a dirigere la riunione. Nel momento in cui per seguire il cliente bisogna abbandonare il kit, si abbandona il kit.

## Da dove si parte

| Se… | Leggi |
|---|---|
| È la prima volta che usi il kit | `00-metodo.md`, poi `03-conduzione-incontro.md` |
| Hai un incontro fra tre giorni | `01-dossier-pre-incontro.md` → `02-questionario-90-secondi.md` → `03b-scheda-processo.md` |
| Sei in macchina davanti all'azienda | `03-conduzione-incontro.md`, sezione «I primi cinque minuti» |
| L'incontro è finito | `06-verbale-24h.md`, e apri l'applicazione |
| Devi mandare l'offerta | `07-scala-ingaggio-offerta.md` |

## Indice

| File | Cosa contiene |
|---|---|
| `00-metodo.md` | La tesi, le cinque fasi, i segnali che dicono «AI-native» |
| `01-dossier-pre-incontro.md` | Ricerca preventiva: fonti, template, come **non** usarlo |
| `02-questionario-90-secondi.md` | Cinque domande, versione a una domanda, mail di invio |
| `03-conduzione-incontro.md` | Le due modalità, come si sceglie, cosa non fare mai |
| `03b-scheda-processo.md` | La griglia a sette campi e le due tecniche di intervista |
| `04-canvas-mappa-processi.md` | Canvas A3 — solo modalità B |
| `05-scoring-opportunita.md` | SIPOC, lead time vs touch time, matrice, formula ore/mese |
| `06-verbale-24h.md` | Il documento che arriva il giorno dopo |
| `07-scala-ingaggio-offerta.md` | I quattro gradini e la bozza di offerta assessment |
| `08-obiezioni.md` | Le sei obiezioni che arrivano sempre |
| `09-cosa-non-facciamo.md` | Una pagina di posizionamento da consegnare |
| `varianti-settore.md` | Manifattura, servizi professionali, distribuzione |
| `app/` | L'applicazione locale |
| `tools/` | Gli stessi strumenti da riga di comando |

## Prima di usarlo sul serio

Fai una **prova a vuoto**: registra dieci minuti di finta riunione, caricali nell'app e guarda cosa esce. Serve a due cose — verificare che tutto funzioni prima di averne bisogno davvero, e capire che qualità di verbale aspettarti.

Il test più importante del kit è però un altro: simulare un cliente che nei primi due minuti dice «guardi, io volevo mostrarle la nostra gestione documentale», e verificare che il materiale regga senza che tu debba imporre nessuna struttura. Se per seguirlo devi abbandonare il kit, il kit è sbagliato.

## Stato

Tono di voce e nomi dei servizi sono scritti in modo **neutro**: vanno riallineati al sito che espone il progetto Move 37. Punti da riallineare: la frase di apertura in `00-metodo.md`, i nomi dei gradini in `07-scala-ingaggio-offerta.md`, la pagina `09-cosa-non-facciamo.md`.

Riferimenti normativi e di finanza agevolata (AI Act, incentivi) sono **segnaposto espliciti**: vanno verificati alla data d'uso, mai citati a memoria.
