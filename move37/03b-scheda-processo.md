# Scheda processo e tecniche di intervista

> **Se il cliente ha già un'agenda, questo foglio resta in cartella.**
> La scheda no: quella si usa proprio quando il cliente guida.

## La griglia a sette campi

Non è un questionario e non si mostra. Sono le sette cose da estrarre per **ogni processo che il cliente nomina**, chieste dentro il suo racconto, in qualunque ordine lui decida di parlare.

| # | Campo | Come si chiede, senza sembrare un interrogatorio |
|---|---|---|
| 1 | **Volume** | «Quante ne fate in un mese, più o meno?» |
| 2 | **Chi e quanto** | «Chi ci mette le mani? E quanto tempo va via ogni volta?» |
| 3 | **Dove stanno i dati** | «Queste informazioni dove sono adesso? Chi ce le mette?» |
| 4 | **Cosa succede quando va storto** | «E quando salta qualcosa, com'è che ve ne accorgete?» |
| 5 | **Chi si lamenta** | «Chi è che rompe di più su questa cosa? Il cliente, il capo, chi la fa?» |
| 6 | **Cosa hanno già provato** | «Avete già provato a sistemarlo? Com'è andata?» |
| 7 | **Chi decide, chi si oppone** | «Se domani si cambiasse, chi dovrebbe dire di sì? E chi storcerebbe il naso?» |

**Se al termine dell'incontro ho queste sette risposte per tre processi, l'incontro è riuscito** — indipendentemente da quanto della struttura del kit ho usato. Se ne ho quattordici su ventuno, va bene lo stesso: i buchi diventano la lista «cosa ci serve da voi» nel verbale.

### Perché proprio queste sette

- 1 e 2 danno il **business case**: volume × tempo × costo orario. Senza questi due non esiste una stima, e senza stima non esiste un progetto.
- 3 dice se il progetto è **fattibile**. Un processo perfetto da automatizzare i cui dati stanno su un quaderno non è automatizzabile quest'anno.
- 4 e 5 danno l'**urgenza**, che è cosa diversa dall'importanza. Si finanzia ciò che fa male, non ciò che conviene.
- 6 evita di riproporre una cosa già fallita, che è il modo più rapido di perdere credibilità.
- 7 dice se il progetto **sopravviverà**: chi si oppone, se non viene coinvolto, lo fa fallire in silenzio.

### Il campo 5 merita un'attenzione in più

Chi si lamenta cambia completamente il progetto:

| Si lamenta… | Significa |
|---|---|
| **Il cliente finale** | Massima urgenza, e il ROI è difendibile davanti a chiunque |
| **Il capo** | C'è budget, ma verificare che il problema esista davvero anche per chi lavora |
| **Chi esegue** | L'alleato migliore. E il progetto avrà adozione, che è il vero punto di caduta |
| **Nessuno** | Attenzione: forse non è un problema. Forse è solo il processo di cui si parla più volentieri |

## Le due tecniche che valgono più degli strumenti

### «Mi racconti l'ultima volta che è successo»

**Mai chiedere «come funziona di solito».** La risposta a quella domanda è il processo idealizzato: quello scritto nelle procedure, quello che si racconta all'auditor.

«L'ultima volta» tira fuori il processo reale — le eccezioni, i post-it sul monitor, il file Excel che qualcuno tiene sul desktop e che nessuno sa che esiste, la telefonata che sblocca sempre tutto.

**Il valore è tutto lì.** Il processo scritto nelle procedure non ha bisogno di noi: è già ordinato. È nello scarto fra procedura e realtà che stanno le ore perse.

Varianti utili:
- «Mi racconti l'ultimo che è andato storto.»
- «Mi fa vedere l'ultimo che avete fatto? Anche aprendolo adesso.»
- «Qual è stato il più difficile degli ultimi mesi?»

### «Me lo fa vedere mentre lo fa?»

Dieci minuti a guardare qualcuno lavorare valgono un'ora di descrizione. I venti clic inutili, il copia-incolla fra tre finestre, il file cercato per due minuti: **si vedono solo così**, perché chi li fa da anni non li vede più e non li racconta.

Se propongono il giro in azienda si accetta sempre, anche se allunga l'incontro. Se non lo propongono, si chiede.

## Scheda A4 da stampare

Una per processo. I campi si riempiono in ordine sparso, seguendo il cliente.

```
┌──────────────────────────────────────────────────────────┐
│ PROCESSO (parole del cliente): ......................... │
│ Azienda: ....................  Data: ........  Sched. n° │
├──────────────────────────────────────────────────────────┤
│ ① VOLUME            quante volte/mese ................   │
│ ② CHI E QUANTO      chi ..............................   │
│                     tempo per volta ..................   │
│ ③ DATI              dove stanno ......................   │
│                     formato/sistema ..................   │
│                     chi li inserisce .................   │
│ ④ QUANDO VA STORTO  cosa succede .....................   │
│                     ogni quanto ......................   │
│ ⑤ CHI SI LAMENTA    ☐ cliente ☐ capo ☐ chi esegue       │
│                     ☐ nessuno ← attenzione               │
│ ⑥ GIÀ PROVATO       cosa ............................    │
│                     com'è andata .....................   │
│ ⑦ DECIDE / SI OPPONE  decide .........................   │
│                       si oppone ......................   │
├──────────────────────────────────────────────────────────┤
│ LEAD TIME (dall'inizio alla fine) ....................   │
│ TOUCH TIME (lavoro vero) .............................   │
├──────────────────────────────────────────────────────────┤
│ CITAZIONI TESTUALI (parole sue, virgolettate)            │
│ « ...................................................... │
│ ...................................................... » │
├──────────────────────────────────────────────────────────┤
│ DA VEDERE / DA CHIEDERE DOPO                             │
│ ○ ..................................................     │
│ ○ ..................................................     │
└──────────────────────────────────────────────────────────┘
```

Versione stampabile: `python tools/build_docx.py --solo scheda-processo`.

### Il riquadro delle citazioni non è un vezzo

Le frasi testuali del cliente vanno nel verbale così come sono. Quando il titolare rilegge **le sue parole** dentro il nostro documento, capisce di essere stato ascoltato — e questo vale più di qualsiasi analisi che ci si possa mettere sotto.

Vale anche in senso pratico: sei mesi dopo, «ci mettiamo tre giorni a fare un preventivo che poi il cliente manco legge» è la riga che riapre il progetto.

## Dopo l'incontro

Le schede si fotografano subito, in macchina, prima di ripartire. Poi si danno in pasto a `tools/verbale.py` insieme alla trascrizione: i sette campi diventano `processi.json`, che alimenta lo scoring (`05-scoring-opportunita.md`).

**I campi rimasti vuoti si scrivono «non rilevato»**, e finiscono nella lista «cosa ci serve da voi». Non si colmano a stima: un numero inventato nel verbale brucia in un secondo la fiducia costruita in tre ore.
