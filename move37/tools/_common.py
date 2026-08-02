"""Utilità condivise dai tool Move 37."""

import os
import pathlib
import re
import sys

MODEL = "claude-opus-5"
PROMPTS = pathlib.Path(__file__).parent / "prompts"


def client():
    """Client Anthropic. Le credenziali arrivano dall'ambiente (ANTHROPIC_API_KEY
    o un profilo `ant auth login`) — il costruttore le risolve da solo."""
    try:
        import anthropic
    except ImportError:
        sys.exit("Manca il pacchetto `anthropic`: pip install -r requirements.txt")
    return anthropic.Anthropic()


def prompt(name):
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def text_of(response):
    return "\n".join(b.text for b in response.content if b.type == "text")


def check_refusal(response, cosa):
    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        categoria = getattr(detail, "category", None) or "non specificata"
        sys.exit(f"Richiesta rifiutata durante {cosa} (categoria: {categoria}).")


def slug(testo):
    s = re.sub(r"[^a-z0-9]+", "-", testo.lower()).strip("-")
    return s or "cliente"


def research(cli, istruzioni, model=MODEL, effort="high", max_tokens=32000, max_pause=6):
    """Un giro di ricerca con i tool server-side di web search e fetch.

    I server tool girano sull'infrastruttura Anthropic: non c'è niente da eseguire
    in locale. `stop_reason == "pause_turn"` significa che il ciclo server-side ha
    raggiunto il suo limite di iterazioni e va ripreso rimandando la conversazione.
    """
    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]
    messages = [{"role": "user", "content": istruzioni}]
    for _ in range(max_pause):
        with cli.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=prompt("dossier"),
            output_config={"effort": effort},
            tools=tools,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()
        check_refusal(response, "la ricerca")
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        return text_of(response)
    sys.exit("La ricerca non è arrivata a termine: troppe riprese consecutive.")


def structure(cli, system, contenuto, schema, model=MODEL, effort="high", max_tokens=16000):
    """Secondo passaggio: dal testo grezzo al JSON validato lato API."""
    with cli.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        output_config={
            "effort": effort,
            "format": {"type": "json_schema", "schema": schema},
        },
        messages=[{"role": "user", "content": contenuto}],
    ) as stream:
        response = stream.get_final_message()
    check_refusal(response, "la strutturazione")
    import json

    return json.loads(text_of(response))


def leggi_cartella(percorso):
    """Estrae testo da HTML, PDF e file di testo salvati a mano.

    Non è un ripiego: molti siti aziendali rifiutano i crawler, e salvare cinque
    pagine è spesso più veloce che combattere con un WAF.
    """
    base = pathlib.Path(percorso)
    if not base.is_dir():
        sys.exit(f"Non è una cartella: {percorso}")
    pezzi = []
    for f in sorted(base.rglob("*")):
        if not f.is_file():
            continue
        suf = f.suffix.lower()
        try:
            if suf in {".html", ".htm"}:
                pezzi.append(f"## {f.name}\n{_html_a_testo(f.read_text(encoding='utf-8', errors='replace'))}")
            elif suf == ".pdf":
                pezzi.append(f"## {f.name}\n{_pdf_a_testo(f)}")
            elif suf in {".txt", ".md"}:
                pezzi.append(f"## {f.name}\n{f.read_text(encoding='utf-8', errors='replace')}")
        except Exception as e:  # un file illeggibile non deve fermare tutto
            print(f"  [salto {f.name}: {e}]", file=sys.stderr)
    if not pezzi:
        sys.exit(f"Nessun file leggibile in {percorso} (attesi .html, .pdf, .txt, .md)")
    return "\n\n".join(pezzi)


def _html_a_testo(html):
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        sys.exit("Per leggere HTML serve beautifulsoup4: pip install -r requirements.txt")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "noscript"]):
        tag.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))


def _pdf_a_testo(percorso):
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("Per leggere PDF serve pypdf: pip install -r requirements.txt")
    return "\n".join(p.extract_text() or "" for p in PdfReader(str(percorso)).pages)


def scrivi(cartella, nome, contenuto):
    d = pathlib.Path(cartella)
    d.mkdir(parents=True, exist_ok=True)
    p = d / nome
    p.write_text(contenuto, encoding="utf-8")
    return p


def oggi():
    """La data arriva dall'ambiente se impostata, altrimenti dall'orologio."""
    import datetime

    forzata = os.environ.get("MOVE37_DATA")
    if forzata:
        return forzata
    return datetime.date.today().isoformat()
