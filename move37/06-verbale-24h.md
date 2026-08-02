# Il verbale delle 24 ore

> Questo è il pezzo che regge tutto il metodo. Se salta questo, l'incontro è stato una chiacchierata.

## Perché conta più della demo

In riunione il cliente ha visto una persona preparata. Il giorno dopo vede **cosa quella persona riesce a produrre**, e in quanto tempo.

Un consulente tradizionale manda il verbale dopo una settimana, se lo manda. Noi lo mandiamo in due-quattro ore, completo di mappa dei processi, stime e priorità. Non serve spiegare cosa sappiamo fare: il documento **è** la spiegazione.

La riga di accompagnamento, una sola:

> «Questo documento è uscito dal nostro sistema in venti minuti dalla registrazione di stamattina. È esattamente il tipo di cosa che possiamo fare per voi.»

Niente di più. Se si aggiungono tre paragrafi di spiegazione, l'effetto svanisce.

## L'ordine è obbligatorio

**Prima i processi come li ha nominati lui, nelle sue parole e nel suo ordine. Poi, in una sezione separata e dichiarata come tale, la nostra lettura.**

Mai fondere le due cose. Se la nostra priorità arriva travestita da resoconto, il documento smette di essere un verbale e diventa una proposta commerciale — e perde in un colpo solo tutta la credibilità guadagnata in riunione.

La separazione va resa visibile anche graficamente: titolo di sezione esplicito, «La nostra lettura», e una riga che dice cosa cambia.

## Struttura

```markdown
# <Azienda> — Incontro del <data>
Presenti: <nomi e ruoli> · Durata: <h> · Verbale generato il <data> alle <ora>

## 1. Cosa ci siete detti
I processi nell'ordine in cui li avete nominati, con le vostre parole.

### 1.1 <Processo, nome loro>
> «<citazione testuale>»

| | |
|---|---|
| Volume | <n>/mese |
| Chi ci lavora | <chi>, <tempo> a volta |
| Dove stanno i dati | <sistema, formato> |
| Quando va storto | <cosa succede>, <frequenza> |
| Chi se ne lamenta | <chi> |
| Già provato | <cosa>, <esito> |
| Decide / si oppone | <chi> / <chi> |
| Lead time / lavoro vero | <x> / <y> |

<campi non emersi → «non rilevato»>

### 1.2 <Processo> …

## 2. Cosa ci serve da voi
I campi rimasti vuoti, come domande dirette.
- [ ] …

## 3. La nostra lettura
> Questa sezione è nostra: sono valutazioni, non cose che ci avete detto.

**Da dove partiremmo:** <processo> — perché <motivo>.
E perché **non** dal più urgente: <spiegazione onesta>.

| Processo | Ore/mese stimate | Fattibilità | Ordine |
|---|---|---|---|
| … | … | … | … |

Stime a partire dai numeri che ci avete dato voi, arrotondate per difetto.

## 4. Come procederemmo
90 giorni, tre tappe, con cosa si vede alla fine di ciascuna.

## 5. Cosa non faremmo
<Almeno una cosa vera che non conviene fare, e perché.>

## 6. Prossimo passo
<Azione> entro il <data>.
```

## La sezione 5 non è una formalità

**«Cosa non faremmo» va compilata sul serio, con una cosa che il cliente potrebbe volere.**

Dire «il chatbot sul sito non ve lo consiglio, avete quaranta visite al giorno e vi risolve niente» costa una riga e compra più fiducia di tutto il resto del documento. È il segnale che non stiamo vendendo tutto quello che possiamo vendere.

Se in un verbale la sezione 5 è vuota o generica, il verbale non è finito.

## Regole di generazione

**Niente numeri inventati.** Se un volume non è emerso, si scrive «non rilevato» e finisce nella sezione 2. Colmare i buchi a stima brucia in un secondo la fiducia costruita in tre ore — e il titolare se ne accorge, perché quei numeri li conosce.

**Le citazioni sono testuali.** Non si ripuliscono, non si mettono in italiano migliore. Quando il cliente rilegge le sue parole capisce di essere stato ascoltato.

**Il lessico è loro.** Commessa resta commessa. Se in azienda si dice «bolla», nel verbale c'è scritto bolla.

**Niente nomi di tecnologie**, salvo che li abbiano chiesti loro. Nessun modello, nessuna sigla, nessun fornitore.

## Generazione

```bash
# con registrazione
python tools/verbale.py --audio riunione.m4a --azienda "Esempio Srl" --data 2026-08-05

# senza consenso alla registrazione
python tools/verbale.py --appunti schede-fotografate.md --azienda "Esempio Srl"

# trascrizione già pronta
python tools/verbale.py --trascrizione riunione.txt --azienda "Esempio Srl"
```

Output: `verbale.md`, `processi.json` (i sette campi per processo, che alimentano lo scoring e poi l'assessment), e il DOCX brandizzato via `build_docx.py`.

**La trascrizione gira in locale**, con `faster-whisper`. Costa qualche minuto in più e vale molto: permette di dire in riunione «l'audio non esce dal mio computer» — e di dirlo essendo vero, il che è verificabile e quindi diverso da una rassicurazione.

## Prima di mandarlo

Cinque minuti di rilettura, sempre. La pipeline sbaglia in tre modi ricorrenti:

- **Traduce il lessico** in termini più «professionali» → ricontrollare i nomi dei processi
- **Riempie i buchi** con stime plausibili → cercare i numeri e verificare che ognuno sia stato detto
- **Sconfina** dalla sezione 1 alla 3, mettendo valutazioni nel resoconto → rileggere la sezione 1 chiedendosi «questo me l'hanno detto o l'ho pensato io?»

Il documento va firmato con nome e cognome, non con «il team». Il giorno dopo l'incontro il cliente si ricorda di una persona.
