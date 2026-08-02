# Scala di ingaggio e offerta

> I nomi dei gradini e i prezzi vanno riallineati al posizionamento pubblicato sul sito del progetto.

## I quattro gradini

**Non si salta mai un gradino.** Passare dall'incontro gratuito al progetto grosso è il modo più efficace di far morire una trattativa: chiede al cliente di fidarsi di qualcuno che ha visto una volta.

| # | Gradino | Durata | Cosa consegna |
|---|---|---|---|
| 1 | **Incontro esplorativo** | 90 min, gratuito | Il verbale delle 24 ore |
| 2 | **Assessment** | 2-3 settimane, prezzo fisso | Mappa processi, portafoglio opportunità prioritizzato, business case, architettura dati |
| 3 | **Pilota** | 4-6 settimane, prezzo fisso | Un solo caso, funzionante, con criterio di successo scritto prima |
| 4 | **Rollout / affiancamento** | continuativo | — |

**Al primo incontro si vende il gradino 2.** Non il 3, non il 4. L'assessment è abbastanza piccolo da essere deciso da una persona sola e abbastanza serio da meritare un contratto.

## La frase che vale più di tutta l'offerta

> «Se l'assessment dice che non conviene, ve lo diciamo e ci fermiamo.»

Va detta guardando in faccia, e va rispettata. È l'unica cosa che distingue davvero un consulente da un venditore, e i titolari di PMI la riconoscono al volo perché hanno già sentito la versione opposta molte volte.

Se non si è disposti a rispettarla, meglio non dirla.

## Perché l'assessment e non subito il pilota

Il pilota sembra più concreto, e il cliente spesso lo chiede. Farlo subito però significa scommettere sul processo giusto avendo passato novanta minuti in azienda.

L'assessment costa poco, riduce il rischio per entrambi e — soprattutto — **produce un documento che vale anche se ci si ferma lì**. Un cliente che paga un assessment e poi non prosegue resta comunque un cliente soddisfatto, e parla bene in giro.

C'è un caso in cui si salta al pilota: quando il processo è già chiarissimo, i dati esistono, e il cliente ha fretta per un motivo reale. Allora si va, ma con criterio di fallimento scritto.

## Bozza di offerta — Assessment

```
OGGETTO: Assessment AI — <Azienda>

CONTESTO
<Due righe, con le parole loro. Il processo che hanno nominato per primo.>

COSA FACCIAMO
1. Mappatura dei processi candidati       <n> incontri, <n> persone coinvolte
2. Analisi dei dati disponibili           accesso in sola lettura a <sistemi>
3. Business case per ogni opportunità     ore/mese, costo, tempi, rischi
4. Architettura tecnica e scelta modello  cosa sta dove, chi vede cosa
5. Roadmap 90 giorni                      con cosa si vede a ogni tappa

COSA CONSEGNIAMO
· Documento di assessment (<n> pagine)
· Portafoglio opportunità prioritizzato
· Business case per le prime tre
· Presentazione alla direzione (1 ora)

COSA CI SERVE DA VOI
· Un referente interno, <n> ore a settimana
· Accesso in sola lettura a <sistemi>
· <n> ore delle persone che fanno il lavoro    ← la voce più importante

TEMPI       <n> settimane dalla firma
IMPORTO     € <…> + IVA, fisso
            Scomputabile dal progetto successivo, se ci sarà.

SE NON CONVIENE
Se l'assessment conclude che non ci sono opportunità con ritorno
accettabile, ve lo diciamo e ci fermiamo. Il documento resta vostro.
```

Generazione: `python tools/build_docx.py --solo offerta --json offerta.json`.

## Note sulle voci

**«Le ore delle persone che fanno il lavoro» è la voce più importante dell'offerta**, e va difesa. Un assessment fatto parlando solo con la direzione produce un documento elegante e sbagliato: la direzione descrive il processo come dovrebbe essere.

**Lo scomputo dal progetto successivo** toglie l'obiezione «pago per una consulenza che poi mi rivendete». Costa poco e chiude una discussione.

**Prezzo fisso, mai a giornate.** A giornate il cliente compra tempo; a corpo compra un risultato. E il rischio di stima è nostro, che è giusto: siamo noi a saper stimare.

## Il pilota: cosa scrivere prima di iniziare

Un pilota senza criterio di fallimento scritto non finisce mai — si trascina, e intanto brucia la relazione.

```
CASO                  <processo, parole del cliente>
SUCCESSO SE           <metrica> passa da <oggi> a <obiettivo> entro <data>
FALLIMENTO SE         <metrica> resta sotto <soglia>
CHI MISURA            <nome>, con <metodo>
COSA SUCCEDE SE FALLISCE   Ci fermiamo. Vi lasciamo <cosa> e il perché non ha funzionato.
```

L'ultima riga è quella che fa firmare.

## Segnali di trattativa

| Segnale | Cosa significa |
|---|---|
| Chiede di parlare con chi fa il lavoro | Ottimo: sta valutando sul serio |
| Chiede referenze dello stesso settore | Normale. Se non ce ne sono, si dice e si offre un pilota più piccolo |
| «Ci mandi una proposta» senza aver mostrato niente | Quasi sempre un no gentile |
| Coinvolge l'IT alla seconda riunione | Molto buono: sta pensando a come farlo davvero |
| Chiede solo il prezzo, mai i tempi | Sta confrontando preventivi. Va spostato sul rischio, non sul costo |
| Chiede se si può finanziare | Interesse reale. Verificare gli incentivi **alla data**, mai a memoria (`08`) |
