# Scoring delle opportunità

> **Se il cliente ha già un'agenda, questo foglio resta in cartella.**
> Il contenuto però si usa sempre: in riunione a voce, o nel verbale.

## A cosa serve davvero

Non a trovare opportunità. **A metterle in ordine.**

Se il cliente ha nominato quattro processi, il valore che porto non è trovarne un quinto: è dire quale dei suoi quattro farei per primo, e perché. Quasi sempre la risposta lo sorprende — perché si tende a voler partire dal processo più visibile, quello di cui si lamenta il capo, mentre conviene partire da quello più fattibile, dove i dati esistono già.

## SIPOC — inquadrare un processo in una pagina

Da prendere in prestito, non da reinventare. In un'azienda con la ISO 9001 è un formato che **conoscono già**, e usarlo comunica competenza di processo invece che competenza di tecnologia — che è esattamente il posizionamento che vogliamo.

| | |
|---|---|
| **S** — Supplier | Chi fornisce l'input. Un reparto, il cliente stesso, un fornitore |
| **I** — Input | Cosa arriva. Una mail, un disegno, un capitolato, una telefonata |
| **P** — Process | I 4-6 passi principali. Non di più: se servono quindici passi, sono due processi |
| **O** — Output | Cosa esce. Un preventivo, un documento, una registrazione |
| **C** — Customer | Chi riceve l'output, interno o esterno |

Si compila **dopo** l'incontro, dalle schede processo — non in riunione, dove ruberebbe attenzione. Va nell'allegato del verbale.

Il valore diagnostico sta ai bordi: se **I** è una telefonata o una mail in prosa, c'è quasi sempre un progetto. Se **O** è un documento che qualcuno riscrive ogni volta da un modello, c'è sicuramente un progetto.

## Lead time vs touch time — il numero che sblocca

Il confronto più utile dell'intero metodo.

- **Lead time** — da quando parte a quando è finito, tempo di calendario, attese comprese
- **Touch time** — il tempo in cui qualcuno ci sta effettivamente lavorando

> «Il preventivo esce in cinque giorni, ma di lavoro vero sono quaranta minuti.»

Il rapporto tipico nelle PMI è fra 1:20 e 1:100. Detto al titolare, questo numero fa più effetto di qualsiasi stima di risparmio, per tre motivi: è **suo** (i dati li ha dati lui), è **verificabile** domani mattina, e sposta la conversazione dal costo del lavoro al tempo di risposta al cliente — che è il terreno dove l'AI conviene davvero.

**Attenzione a come si usa.** Non è una critica all'organizzazione. Si presenta come un'opportunità: «il grosso non è il lavoro, è l'attesa — e l'attesa si aggredisce molto più facilmente».

## La formula, tenuta volutamente grezza

```
ore risparmiate/mese  =  volume mensile × tempo per volta × quota automatizzabile
valore/anno           =  ore risparmiate/mese × 12 × costo orario pieno
```

Tre regole d'uso:

**I numeri li dice il cliente.** Volume, tempo e costo orario devono uscire dalla sua bocca, non da un benchmark. Un numero suo vale dieci volte un numero mio: sul mio discute, sul suo ragiona.

**La quota automatizzabile si tiene bassa.** 50-70% è realistico su un processo documentale; il 100% non esiste, perché resta sempre la revisione umana. Promettere il 90% al primo incontro significa perdere il pilota.

**Si arrotonda per difetto e si dichiara la banda.** «Fra le sessanta e le cento ore l'anno» è credibile; «87,5 ore» è una bugia con tre cifre decimali.

## La matrice

```
        alto │  ⓶ pianificare         │  ⓵ PARTIRE DA QUI
             │  (impatto grosso,      │  (impatto grosso,
   I         │   dati da costruire)   │   dati già pronti)
   M         │                        │
   P    ─────┼────────────────────────┼──────────────────────
   A         │  ⓸ lasciar perdere     │  ⓷ eventuale vetrina
   T         │                        │  (facile ma conta poco:
   T   basso │                        │   utile solo per
   O         │                        │   costruire fiducia)
             └────────────────────────┴──────────────────────
                    bassa          FATTIBILITÀ          alta
```

**Impatto** = ore/mese × costo orario, corretto per chi si lamenta (campo 5 della griglia). Un processo di cui si lamenta il cliente finale pesa più di uno di cui si lamenta solo il capo.

**Fattibilità** = quattro domande secche, dalle schede processo:

1. I dati esistono già in forma digitale? *(campo 3)*
2. Il processo è stabile o cambia ogni mese? *(campo 6)*
3. C'è un responsabile interno disposto a seguirlo? *(campo 7)*
4. Si può misurare se funziona?

Se la risposta a una qualsiasi è no, la fattibilità è bassa. Non è una media pesata: sono quattro condizioni.

## Come si presenta

**In riunione** (se c'è tempo): a voce, senza disegnare la matrice. «Dei quattro che mi ha detto, io partirei dalla preventivazione. Non perché sia il più grave — il più grave è la qualità — ma perché i dati ce li avete già e in sei settimane si vede se funziona.»

**Nel verbale**: la matrice disegnata, con i numeri suoi, nella sezione «la nostra lettura» — separata dal resoconto, mai fusa con esso (`06-verbale-24h.md`).

## Il quadrante ⓷ merita una nota

Un processo facile ma di basso impatto normalmente si scarta. C'è però un caso in cui conviene farlo per primo: **quando l'azienda non ha mai fatto nulla di simile e ha bisogno di vedere che funziona.**

Una vittoria piccola in tre settimane costruisce più fiducia di un progetto giusto che si vede fra sei mesi. Se si sceglie questa strada va detto apertamente — «questo lo facciamo per rompere il ghiaccio, il progetto vero è l'altro» — altrimenti sembra che non si sia capito dove stava il problema.
