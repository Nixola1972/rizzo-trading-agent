# Canvas mappa processi — solo modalità B

> **Se il cliente ha già un'agenda, questo foglio resta in cartella.**
> Questo canvas più di ogni altra cosa: occupa il tavolo e dichiara che comando io.

## Quando si usa, e quando no

**Si usa** quando il cliente dice qualche versione di «vorremmo fare qualcosa con l'AI ma non sappiamo da dove partire». Lì la struttura è un servizio: dà una via d'ingresso a chi non ce l'ha.

**Non si usa** quando il cliente ha già una lista di processi in testa. In quel caso il canvas è un modo elegante per non ascoltarlo.

**Si abbandona a metà** se durante la mappatura il cliente si accende su un processo e comincia a raccontare. Il canvas ha già fatto il suo lavoro: ha sbloccato il racconto. Da lì si passa alle schede processo (`03b`).

## Il canvas

Un A3 orizzontale. Si compila da sinistra a destra seguendo il flusso del valore — **dal primo contatto del cliente al pagamento incassato** — perché è l'unico percorso che tutti in azienda riconoscono, indipendentemente dal reparto.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DAL PRIMO CONTATTO AL PAGAMENTO INCASSATO          Azienda: ......  Data:  │
├───────────┬───────────┬───────────┬───────────┬───────────┬─────────────────┤
│ ARRIVA LA │ FACCIAMO  │ IL CLIENTE│ SI        │ SI        │ SI INCASSA      │
│ RICHIESTA │ L'OFFERTA │ ACCETTA   │ PRODUCE / │ CONSEGNA  │                 │
│           │           │           │ ESEGUE    │           │                 │
├───────────┼───────────┼───────────┼───────────┼───────────┼─────────────────┤
│ chi       │           │           │           │           │                 │
├───────────┼───────────┼───────────┼───────────┼───────────┼─────────────────┤
│ quanto    │           │           │           │           │                 │
│ tempo     │           │           │           │           │                 │
├───────────┼───────────┼───────────┼───────────┼───────────┼─────────────────┤
│ quante    │           │           │           │           │                 │
│ volte/mese│           │           │           │           │                 │
├───────────┼───────────┼───────────┼───────────┼───────────┼─────────────────┤
│ dove sono │           │           │           │           │                 │
│ i dati    │           │           │           │           │                 │
├───────────┼───────────┼───────────┼───────────┼───────────┼─────────────────┤
│ cosa      │           │           │           │           │                 │
│ blocca ⚡ │           │           │           │           │                 │
└───────────┴───────────┴───────────┴───────────┴───────────┴─────────────────┘
   LEAD TIME TOTALE: ..........   di cui LAVORO VERO: ..........
```

Le colonne si rinominano seguendo il cliente. Se l'azienda non produce ma installa, la quarta colonna diventa «si installa». **Il canvas si adatta a loro, non viceversa.**

Versione stampabile: `python tools/build_docx.py --solo canvas`.

## Come si conduce

**Il pennarello va in mano a loro** ogni volta che è possibile. Chi scrive possiede il documento, e un documento di cui il cliente si sente proprietario non viene difeso: viene corretto, che è molto meglio.

**Si parte dalla fine.** «Quando incassate?» è una domanda a cui tutti sanno rispondere e che nessuno si aspetta. Poi si risale. Partire dall'inizio porta a descrizioni idealizzate; partire dalla fine porta ai ritardi veri.

**La riga ⚡ è la più importante.** «Cosa blocca» è dove stanno i progetti: attese, rilavorazioni, cose fatte due volte, informazioni che si cercano. Il resto del canvas serve a dare contesto a quella riga.

**Il totale in basso è il colpo di scena.** Sommando i tempi si arriva quasi sempre a qualcosa come: lead time undici giorni, lavoro vero tre ore. Quel confronto, scritto a pennarello sul tavolo dal cliente stesso, apre più progetti di qualsiasi presentazione. Vedi `05-scoring-opportunita.md`.

## Errori tipici

**Riempire il canvas al posto loro.** Se il consulente scrive tutto, alla fine il canvas è un'analisi del consulente, e verrà trattato come tale: con cortesia, e poi archiviato.

**Fermarsi al processo principale.** Spesso il dolore vero sta in un flusso laterale — resi, assistenza post-vendita, ricambi, contestazioni — che nessuno mappa perché «è un'eccezione». Se le eccezioni sono il 30% dei casi, non sono eccezioni.

**Accettare «dipende».** Alla domanda sui tempi, «dipende» è una risposta legittima e va scavata: «mi dica l'ultimo. Quanto ci è voluto?» Vedi la tecnica in `03b`.

**Non annotare i nomi dei sistemi.** «Sta sul gestionale» non basta: quale, di che anno, chi lo mantiene, si può interrogare. Questa riga decide se il progetto è fattibile in sei settimane o in sei mesi.
