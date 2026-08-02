# Il metodo

> **Se il cliente ha già un'agenda, questo foglio resta in cartella.**

## La tesi: il metodo è la demo

Il primo incontro non deve **parlare** di AI. Deve **essere** fatto con l'AI, in modo che il cliente lo veda senza che glielo si spieghi.

Ogni oggetto che il cliente tocca è una prova: il modo in cui si fissa l'appuntamento, le domande che si fanno, la velocità con cui arriva il verbale. La prova più forte è proprio la **velocità** — consegnare in ore ciò che un consulente tradizionale consegna in settimane.

Nessuna slide con robot, cervelli luminosi o reti neurali blu. Quelle dicono l'esatto contrario di ciò che vogliamo dire: dicono «vendo tecnologia», mentre noi vogliamo dire «capisco il tuo lavoro».

Aggancio narrativo, trenta secondi, **solo se c'è spazio**: *Move 37* è la mossa che AlphaGo giocò contro Lee Sedol e che nessun umano avrebbe giocato — sembrava un errore, era la vittoria.

> «Non veniamo ad automatizzare quello che già sapete di dover automatizzare. Veniamo a cercare la vostra mossa 37.»

Se il cliente ha già la sua agenda, questo si salta: si racconta alla fine, o non si racconta affatto.

## Il vincolo che governa tutto: la struttura è una rete, non un copione

Il cliente spesso convoca **lui** l'incontro, per mostrare i suoi processi, e arriva con idee già formate: «voglio migliorare la gestione documentale», «la registrazione qualità», «la preventivazione». In quel caso presentarsi con un'agenda scandita e un dossier di ipotesi è il modo più rapido per sembrare un venditore col pacchetto pronto — e per sentirsi rispondere *«ma io l'avevo chiamata per tutt'altro»*.

Cinque regole che vengono prima di ogni altra cosa in questo kit:

1. **Il primo a parlare è il cliente.** Si apre con una domanda sola — «lei come se l'è immaginato questo incontro?» — e poi si tace davvero.
2. **Il dossier serve a me, non a lui.** Serve per fare domande migliori, non per essere presentato. Resta in cartella salvo che serva.
3. **Niente proposte prima di aver visto un caso reale.** Se dice «la preventivazione non funziona», la risposta giusta non è una soluzione: è «me ne faccia vedere uno vero, di quelli difficili».
4. **I processi che nomina lui sono l'ordine del giorno.** Non se ne cercano altri per far vedere che si è bravi. Il valore aggiunto sta nel dire *quale dei suoi* farei per primo e perché — e spesso non è quello che si aspetta.
5. La struttura del kit si usa **solo per la quota di incontro che il cliente lascia vuota**.

## Le cinque fasi

### Fase 0 — Dossier pre-incontro (T-7 → T-2)

Si lavora prima, senza chiedere niente al cliente. Fonti, template e — soprattutto — le regole su come **non** usarlo: `01-dossier-pre-incontro.md`.

Il vantaggio del dossier non è mostrarlo. È che avendolo fatto si fanno domande di secondo livello invece di chiedere «di cosa vi occupate».

### Fase 1 — Contatto leggero (T-3)

Cinque domande da novanta secondi se l'incontro l'abbiamo chiesto noi; **una sola domanda** se è stato il cliente a convocarci. Testi pronti in `02-questionario-90-secondi.md`.

### Fase 2 — L'incontro

Si sceglie la modalità nei primi cinque minuti, con una domanda aperta. Modalità A: il cliente guida, noi ascoltiamo e catturiamo. Modalità B: il cliente non sa da dove partire, e allora la struttura serve davvero. Tutto in `03-conduzione-incontro.md`, con la griglia di cattura in `03b-scheda-processo.md`.

### Fase 3 — Le ventiquattro ore (in realtà due-quattro)

Il verbale strutturato che arriva il giorno stesso, generato dalla registrazione. È il pezzo che regge tutto il metodo: `06-verbale-24h.md` e `tools/verbale.py`.

### Fase 4 — La scala di ingaggio

Quattro gradini, mai saltarne uno: `07-scala-ingaggio-offerta.md`. Al primo incontro si vende il secondo gradino, l'assessment. Mai il quarto.

## Con cosa si struttura, se l'agenda non si può imporre

**La struttura non sta nell'ordine del giorno: sta nel foglio di cattura, e soprattutto sta dopo l'incontro.**

Un ordine del giorno struttura il *tempo* — è mio, e collide col cliente. Una griglia di cattura struttura l'*informazione* — è invisibile, e si riempie in qualunque ordine il cliente decida di parlare.

Qui sta il punto AI-native più forte del metodo, più della demo: il consulente tradizionale **deve** dirigere la riunione, perché prende appunti a mano e non può permettersi il disordine. Con registrazione e trascrizione si può seguire il cliente ovunque vada, perché la struttura la impone dopo la pipeline, sul testo.

> Si rinuncia alla struttura in riunione *solo perché* la si recupera automaticamente dopo. È la ragione per cui il metodo non è imitabile da chi non usa l'AI.

| Strumento | A cosa serve | Quando |
|---|---|---|
| **Registrazione + trascrizione** | È la struttura vera: libera dall'obbligo di dirigere | Sempre, con consenso |
| **Scheda processo A4** — una per processo, campi in ordine sparso | Cattura senza dirigere. Discreta: dice «sto prendendo nota per bene», non «adesso comando io» | Modalità A |
| **SIPOC** | Inquadra un processo in una pagina con un linguaggio che in azienda ISO 9001 già conoscono | Post-incontro, o in riunione se sono loro a voler formalizzare |
| **Lead time vs touch time** | Il numero che sblocca i progetti | Post-incontro |
| **Matrice impatto/fattibilità** | Priorità fra i processi che ha nominato lui | Chiusura o verbale |
| **Canvas A3** | Invadente: occupa il tavolo e dichiara che comando io | Solo modalità B |

## I segnali che dicono «AI-native» meglio di un discorso

- **Aver lasciato parlare il cliente per primo** → il segnale più forte di tutti, e costa zero
- Domande di secondo livello dal primo minuto — frutto del dossier, non del dossier esibito → «ha studiato prima di venire»
- Una domanda sola invece di venti → «rispetta il mio tempo, e sa sintetizzare»
- Verbale in due ore invece di una settimana → «la velocità è il prodotto»
- Trascrizione fatta girare **in locale** → «i miei dati non sono usciti dalla stanza», e si può dimostrare
- Demo sul loro materiale invece che su una slide → «non è una vetrina»
- Una pagina «cosa NON facciamo» → «non è un venditore»

## Il rischio principale del kit è il kit stesso

Uno strumento ben fatto chiede di essere usato, e la tentazione di svolgere l'agenda per non sprecare la preparazione è più forte proprio nel momento in cui il cliente sta parlando.

Vale la pena rileggere la riga in cima a questo file prima di ogni incontro.
