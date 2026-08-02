# Dossier pre-incontro

> **Se il cliente ha già un'agenda, questo foglio resta in cartella.**

## Cos'è, e soprattutto cosa non è

Il dossier è **uno strumento mio, non un deliverable per il cliente**.

Non si apre l'incontro presentandolo. Presentarlo per primo impone la mia cornice prima che il cliente abbia parlato, e trasforma un ascolto in una dimostrazione di bravura. Il cliente passa l'ora a correggermi invece che a raccontarmi.

Il modo giusto di segnalarlo è una frase di dieci secondi, all'inizio:

> «Ho guardato il vostro sito e qualche fonte pubblica prima di venire, così non le faccio perdere tempo con le domande base. Ma parta lei: cosa voleva mostrarmi?»

Poi resta in cartella. Si tira fuori solo in due casi: se il cliente si aggancia a qualcosa che c'è dentro, oppure lo si allega al verbale del giorno dopo, dove non toglie spazio a nessuno.

**Il vantaggio non è mostrarlo. È che avendolo fatto si fanno domande di secondo livello** invece di chiedere «di cosa vi occupate» — e la differenza si sente al primo minuto.

## Le fonti, in ordine di resa

| Fonte | Cosa dice davvero | Tempo |
|---|---|---|
| Sito, cataloghi, PDF pubblici | Cosa vendono e a chi, con che linguaggio. Il lessico va copiato: parlare come loro vale metà del lavoro | 20' |
| **Annunci di lavoro attivi** | Il segnale più sottovalutato in assoluto. Chi cercano dice dove hanno colli di bottiglia e dove stanno crescendo. Un annuncio per «impiegato ufficio tecnico per gestione commesse» vale più di dieci pagine di sito | 15' |
| **Recensioni Google / Trustpilot / Indeed** | Le lamentele dei clienti dicono dove il processo si rompe. Le recensioni dei dipendenti dicono dove si lavora male, che spesso è la stessa cosa | 15' |
| Visura, bilanci depositati | Dimensione reale, numero di addetti, andamento. Serve a calibrare l'offerta, non a sfoggiarlo | 15' |
| LinkedIn azienda + dirigenti | Chi decide, chi ha già un'agenda digitale, chi è arrivato da poco (i nuovi arrivati vogliono cambiare qualcosa) | 15' |
| News, comunicati, fiere | Investimenti recenti e priorità dichiarate. Un capannone nuovo o una linea nuova significa processi in ridefinizione | 10' |
| Certificazioni ISO | Processi già documentati e già misurati: terreno fertile. Se hanno la 9001, esistono già procedure scritte e registrazioni — cioè dati | 5' |
| Concorrenti diretti | Cosa stanno già facendo, se qualcuno si muove. Leva competitiva, da usare con parsimonia | 15' |

Totale: **due ore circa**. Se ne serve di più, il dossier è troppo ambizioso.

## Template

```markdown
# Dossier pre-incontro — <Azienda>
Preparato il <data> · Fonti consultate: <n> · Tempo impiegato: <h>

## Chi sono
<Tre-quattro righe. Cosa fanno, per chi, con che dimensione.
Nel loro lessico, non nel mio.>

## Cinque fatti verificati
Ogni fatto ha una fonte e un link. Nessuna eccezione.

1. <fatto> — fonte: <url>
2. …

Non reperito: <elenco di ciò che si è cercato senza trovarlo.
Serve a me per sapere cosa chiedere, e va detto onestamente.>

## Ipotesi di attrito  ⚠ IPOTESI, NON CONCLUSIONI
1. <ipotesi> — perché lo penso: <indizio concreto e verificabile>
2. …

## Domande a cui solo loro possono rispondere
1. …

## Idee di demo su misura
Tre cose che potrei fare dal vivo in dieci minuti se mi danno il materiale.
1. …
```

## Regole di compilazione

**Nessun numero senza fonte.** Se il fatturato non si trova, si scrive «non reperito». Un numero stimato che finisce nel dossier e si rivela sbagliato brucia in tre secondi tutta la credibilità che il dossier doveva costruire.

**Le ipotesi si marcano come ipotesi.** Un'ipotesi presentata come conclusione è un errore che il cliente perdona una volta sola.

**Il lessico è loro.** Se chiamano «commessa» quello che altrove si chiama «ordine», nel dossier si scrive commessa. Vale anche in riunione, e vale doppio nel verbale.

**Niente giudizi sul loro sito, sulla loro organizzazione, sul loro ritardo digitale.** Anche se evidenti. Soprattutto se evidenti.

## Generazione automatica

`tools/dossier.py` costruisce la bozza a partire dall'URL. Va lanciato **in locale**: gli ambienti remoti hanno policy di rete che bloccano i siti cliente.

```bash
python tools/dossier.py --url https://esempio.it --nome "Esempio Srl"
python tools/dossier.py --from-files ./pagine-salvate   # se il sito blocca i crawler
```

La modalità `--from-files` non è un ripiego: molti siti aziendali rifiutano i crawler, e salvare a mano cinque pagine è spesso più veloce che combattere con Cloudflare.

**L'output è una bozza, non un dossier.** Va riletto e potato: il modello tende a essere generoso con le ipotesi, e le ipotesi deboli sono peggio di nessuna ipotesi.
